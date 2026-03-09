from flask import Flask, request, jsonify, Response
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import mongo_client
from typing import Any, Dict, Mapping, Optional, cast

JsonDict = Dict[str, Any]
SellerContact = Dict[str, Optional[str]]


def _now() -> datetime:
    return datetime.now(timezone.utc)

app = Flask(__name__)

ZEPTO_DB = os.getenv("MONGO_DB", "snapit_zepto")
INSTAMART_DB = os.getenv("INSTAMART_DB", "snapit_instamart")
AUTH_DB = os.getenv("AUTH_DB", "snapit_auth")
AUTH_COLLECTION = os.getenv("AUTH_COLLECTION", "users")
SELLER_DB = os.getenv("SELLER_DB", "snapit_sellers")
SELLER_COLLECTION = os.getenv("SELLER_COLLECTION", "sellers")
SELLER_PRODUCTS_COLLECTION = os.getenv("SELLER_PRODUCTS_COLLECTION", "seller_products")
SELLER_FEEDBACK_COLLECTION = os.getenv("SELLER_FEEDBACK_COLLECTION", "seller_feedback")
SELLER_NOTICES_COLLECTION = os.getenv("SELLER_NOTICES_COLLECTION", "seller_notices")
SELLER_HISTORY_COLLECTION = os.getenv("SELLER_HISTORY_COLLECTION", "seller_history")

LAST_TERM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_search_term.txt')

def _auth_collection(role: str = "customer"):
    target_db = SELLER_DB if "seller" in role else AUTH_DB
    target_col = SELLER_COLLECTION if "seller" in role else AUTH_COLLECTION
    col = mongo_client.get_collection(target_col, db_name=target_db)
    try:
        col.create_index("email", unique=True)
    except Exception:
        pass
    return col

def _serialize_user(user_doc: Optional[Mapping[str, Any]]) -> Optional[JsonDict]:
    if not user_doc:
        return None
    created_at: Optional[datetime | str] = user_doc.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return {
        "id": str(user_doc.get("_id")),
        "name": user_doc.get("name", ""),
        "email": user_doc.get("email", ""),
        "created_at": created_at,
        "role": user_doc.get("role", "customer"),
        "sellerDetails": user_doc.get("sellerDetails"),
    }


def _get_json_body() -> JsonDict:
    data = request.get_json(silent=True)
    return cast(JsonDict, data) if isinstance(data, dict) else {}


def _seller_collection(name: str):
    col = mongo_client.get_collection(name, db_name=SELLER_DB)
    try:
        col.create_index("seller_id")
    except Exception:
        pass
    return col


def _seller_history_collection():
    col = mongo_client.get_collection(SELLER_HISTORY_COLLECTION, db_name=SELLER_DB)
    try:
        col.create_index("seller_id")
        col.create_index("created_at")
    except Exception:
        pass
    return col


def _log_history(seller_oid: ObjectId, action: str, payload: Mapping[str, Any]) -> None:
    try:
        col = _seller_history_collection()
        col.insert_one({
            "seller_id": seller_oid,
            "action": action,
            "payload": dict(payload),
            "created_at": _now(),
        })
    except Exception:
        pass


def _get_seller_contact(seller_oid: ObjectId) -> SellerContact:
    """Fetch seller contact fields for UI (whatsapp/phone)"""
    sellers = mongo_client.get_collection(SELLER_COLLECTION, db_name=SELLER_DB)
    seller_doc = sellers.find_one({"_id": seller_oid})
    raw_details = seller_doc.get("sellerDetails") if seller_doc else None
    details: Mapping[str, Any] = cast(JsonDict, raw_details) if isinstance(raw_details, dict) else {}
    return {
        "whatsapp": details.get("whatsapp") or details.get("phone"),
        "phone": details.get("phone"),
        "email": seller_doc.get("email") if seller_doc else None,
        "name": seller_doc.get("name") if seller_doc else None,
    }


def _parse_object_id(value: Optional[str]):
    if not value:
        return None
    try:
        return ObjectId(value)
    except Exception:
        return None

# Simple CORS allow-all for local dev
@app.after_request
def add_cors_headers(resp: Response) -> Response:
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    return resp

@app.route('/scrape', methods=['POST'])
def scrape():
    data = _get_json_body()
    term = (data.get('product') or '').strip()
    if not term:
        return jsonify({"error": "product is required"}), 400

    env = os.environ.copy()
    env['SEARCH_TERMS'] = term

    try:
        result = subprocess.run(
            [sys.executable, 'scraped.py'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            errors='ignore',
        )
        resp: JsonDict = {
            "status": "ok" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stderr_tail": result.stderr.splitlines()[-10:] if result.stderr else [],
            "output_file": env.get('OUTPUT_FILE', 'scraped_data.json'),
            "term": term,
        }

        # Persist last searched term so the UI can fetch latest without retyping.
        try:
            with open(LAST_TERM_FILE, 'w', encoding='utf-8') as fh:
                fh.write(term)
        except Exception:
            pass
        return jsonify(resp), (200 if result.returncode == 0 else 500)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "scrape timed out"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/auth/signup', methods=['POST'])
def auth_signup():
    data = _get_json_body()
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    role = (data.get('role') or 'customer').strip()
    seller_details = data.get('sellerDetails') if isinstance(data.get('sellerDetails'), dict) else None

    if not name or not email or not password:
        return jsonify({"error": "name, email, and password are required"}), 400

    col = _auth_collection(role)
    existing = col.find_one({"email": email})
    if existing:
        return jsonify({"error": "email already registered"}), 409

    user_doc: JsonDict = {
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": _now(),
        "role": role
    }
    if seller_details:
        user_doc["sellerDetails"] = seller_details
    col.insert_one(user_doc)
    return jsonify({"user": _serialize_user(user_doc)}), 201


@app.route('/auth/login', methods=['POST'])
def auth_login():
    data = _get_json_body()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    role = (data.get('role') or '').strip()

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    search_roles = [role] if role else ["customer", "seller_offline", "seller", "seller_online"]
    user_doc = None
    for r in search_roles:
        col = _auth_collection(r)
        candidate = col.find_one({"email": email})
        if candidate and check_password_hash(candidate.get("password_hash", ""), password):
            user_doc = candidate
            break

    if not user_doc:
        return jsonify({"error": "invalid email or password"}), 401

    return jsonify({"user": _serialize_user(user_doc)}), 200


@app.route('/seller/products', methods=['POST'])
def seller_products_create():
    payload = _get_json_body()
    seller_id_raw = (payload.get('seller_id') or '').strip()
    seller_oid = _parse_object_id(seller_id_raw)
    if not seller_oid:
        return jsonify({"error": "seller_id is required"}), 400

    name = (payload.get('name') or '').strip()
    price = payload.get('price')
    stock = payload.get('stock')
    description = (payload.get('description') or '').strip()
    expiry_date = (payload.get('expiry_date') or '').strip()
    quality_condition = (payload.get('quality_condition') or '').strip()
    category = (payload.get('category') or '').strip()
    status = (payload.get('status') or 'Live').strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    doc: JsonDict = {
        "seller_id": seller_oid,
        "name": name,
        "price": price,
        "stock": stock,
        "description": description,
        "expiry_date": expiry_date,
        "quality_condition": quality_condition,
        "category": category,
        "status": status or "Live",
        "created_at": _now(),
        "updated_at": _now(),
    }
    col = _seller_collection(SELLER_PRODUCTS_COLLECTION)
    result = col.insert_one(doc)
    doc['_id'] = str(result.inserted_id)
    doc['seller_id'] = str(seller_oid)
    created_at_val = doc.get('created_at')
    updated_at_val = doc.get('updated_at')
    if isinstance(created_at_val, datetime):
        doc['created_at'] = created_at_val.isoformat()
    if isinstance(updated_at_val, datetime):
        doc['updated_at'] = updated_at_val.isoformat()
    _log_history(seller_oid, "product_create", {"product_id": str(result.inserted_id), "name": name})
    return jsonify({"product": doc}), 201


@app.route('/seller/products', methods=['GET'])
def seller_products_list():
    seller_id_raw = (request.args.get('seller_id') or '').strip()
    seller_oid = _parse_object_id(seller_id_raw)
    if not seller_oid:
        return jsonify({"error": "seller_id is required"}), 400
    include_contact = (request.args.get('include_contact') or '').strip() in {"1", "true", "yes"}
    col = _seller_collection(SELLER_PRODUCTS_COLLECTION)
    cursor = col.find({"seller_id": seller_oid}).sort("_id", -1).limit(200)
    items: list[JsonDict] = []
    for doc in cursor:
        doc['_id'] = str(doc.get('_id'))
        doc['seller_id'] = str(doc.get('seller_id'))
        created_at = doc.get('created_at')
        updated_at = doc.get('updated_at')
        if isinstance(created_at, datetime):
            doc['created_at'] = created_at.isoformat()
        if isinstance(updated_at, datetime):
            doc['updated_at'] = updated_at.isoformat()
        if include_contact:
            doc['seller_contact'] = _get_seller_contact(seller_oid)
        items.append(doc)
    return jsonify({"items": items}), 200


@app.route('/seller/feedback', methods=['POST'])
def seller_feedback_create():
    payload = _get_json_body()
    seller_id_raw = (payload.get('seller_id') or '').strip()
    seller_oid = _parse_object_id(seller_id_raw)
    if not seller_oid:
        return jsonify({"error": "seller_id is required"}), 400

    message = (payload.get('message') or '').strip()
    rating = payload.get('rating')
    customer_email = (payload.get('customer_email') or '').strip().lower() or None
    if not message:
        return jsonify({"error": "message is required"}), 400

    doc: JsonDict = {
        "seller_id": seller_oid,
        "message": message,
        "rating": rating,
        "customer_email": customer_email,
        "created_at": _now(),
    }
    col = _seller_collection(SELLER_FEEDBACK_COLLECTION)
    result = col.insert_one(doc)
    doc['_id'] = str(result.inserted_id)
    doc['seller_id'] = str(seller_oid)
    created_at_val = doc.get('created_at')
    if isinstance(created_at_val, datetime):
        doc['created_at'] = created_at_val.isoformat()
    return jsonify({"feedback": doc}), 201


@app.route('/seller/feedback', methods=['GET'])
def seller_feedback_list():
    seller_id_raw = (request.args.get('seller_id') or '').strip()
    seller_oid = _parse_object_id(seller_id_raw)
    if not seller_oid:
        return jsonify({"error": "seller_id is required"}), 400
    col = _seller_collection(SELLER_FEEDBACK_COLLECTION)
    cursor = col.find({"seller_id": seller_oid}).sort("_id", -1).limit(200)
    items: list[JsonDict] = []
    for doc in cursor:
        doc['_id'] = str(doc.get('_id'))
        doc['seller_id'] = str(doc.get('seller_id'))
        created_at = doc.get('created_at')
        if isinstance(created_at, datetime):
            doc['created_at'] = created_at.isoformat()
        items.append(doc)
    return jsonify({"items": items}), 200


@app.route('/seller/notices', methods=['POST'])
def seller_notices_create():
    payload = _get_json_body()
    seller_id_raw = (payload.get('seller_id') or '').strip()
    seller_oid = _parse_object_id(seller_id_raw)
    if not seller_oid:
        return jsonify({"error": "seller_id is required"}), 400
    title = (payload.get('title') or '').strip()
    message = (payload.get('message') or '').strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    doc: JsonDict = {
        "seller_id": seller_oid,
        "title": title,
        "message": message,
        "created_at": _now(),
    }
    col = _seller_collection(SELLER_NOTICES_COLLECTION)
    res = col.insert_one(doc)
    doc['_id'] = str(res.inserted_id)
    doc['seller_id'] = str(seller_oid)
    created_at_val = doc.get('created_at')
    if isinstance(created_at_val, datetime):
        doc['created_at'] = created_at_val.isoformat()
    _log_history(seller_oid, "notice_create", {"notice_id": str(res.inserted_id), "title": title})
    return jsonify({"notice": doc}), 201


@app.route('/seller/notices', methods=['GET'])
def seller_notices_list():
    seller_id_raw = (request.args.get('seller_id') or '').strip()
    seller_oid = _parse_object_id(seller_id_raw)
    if not seller_oid:
        return jsonify({"error": "seller_id is required"}), 400
    col = _seller_collection(SELLER_NOTICES_COLLECTION)
    cursor = col.find({"seller_id": seller_oid}).sort("_id", -1).limit(100)
    items: list[JsonDict] = []
    for doc in cursor:
        doc['_id'] = str(doc.get('_id'))
        doc['seller_id'] = str(doc.get('seller_id'))
        created_at = doc.get('created_at')
        if isinstance(created_at, datetime):
            doc['created_at'] = created_at.isoformat()
        items.append(doc)
    return jsonify({"items": items}), 200


@app.route('/seller/profile/update', methods=['POST'])
def seller_profile_update():
    payload = _get_json_body()
    seller_id_raw = (payload.get('seller_id') or '').strip()
    seller_oid = _parse_object_id(seller_id_raw)
    if not seller_oid:
        return jsonify({"error": "seller_id is required"}), 400

    seller_details_payload = payload.get('sellerDetails')
    updates: Dict[str, Any] = cast(Dict[str, Any], seller_details_payload) if isinstance(seller_details_payload, dict) else {}
    if not updates:
        return jsonify({"error": "sellerDetails required"}), 400

    col = mongo_client.get_collection(SELLER_COLLECTION, db_name=SELLER_DB)
    result = col.update_one({"_id": seller_oid}, {"$set": {"sellerDetails": updates}})
    if result.matched_count == 0:
        return jsonify({"error": "seller not found"}), 404
    _log_history(seller_oid, "profile_update", {"fields": list(updates.keys())})
    return jsonify({"status": "ok"}), 200


@app.route('/seller/history', methods=['GET'])
def seller_history_list():
    seller_id_raw = (request.args.get('seller_id') or '').strip()
    seller_oid = _parse_object_id(seller_id_raw)
    if not seller_oid:
        return jsonify({"error": "seller_id is required"}), 400
    col = _seller_history_collection()
    cursor = col.find({"seller_id": seller_oid}).sort("created_at", -1).limit(200)
    items: list[JsonDict] = []
    for doc in cursor:
        doc['_id'] = str(doc.get('_id'))
        doc['seller_id'] = str(doc.get('seller_id'))
        created_at = doc.get('created_at')
        if isinstance(created_at, datetime):
            doc['created_at'] = created_at.isoformat()
        items.append(doc)
    return jsonify({"items": items}), 200


@app.route('/seller/product/<product_id>', methods=['GET'])
def seller_product_detail(product_id: str):
    product_oid = _parse_object_id(product_id)
    if not product_oid:
        return jsonify({"error": "invalid product_id"}), 400
    col = _seller_collection(SELLER_PRODUCTS_COLLECTION)
    doc = col.find_one({"_id": product_oid})
    if not doc:
        return jsonify({"error": "not found"}), 404
    doc['_id'] = str(doc.get('_id'))
    seller_oid = doc.get('seller_id')
    doc['seller_id'] = str(seller_oid) if seller_oid else None
    created_at = doc.get('created_at')
    updated_at = doc.get('updated_at')
    if isinstance(created_at, datetime):
        doc['created_at'] = created_at.isoformat()
    if isinstance(updated_at, datetime):
        doc['updated_at'] = updated_at.isoformat()
    if seller_oid:
        doc['seller_contact'] = _get_seller_contact(seller_oid)
    return jsonify({"product": doc}), 200


@app.route('/seller/products/<product_id>', methods=['PATCH'])
def seller_products_update(product_id: str):
    product_oid = _parse_object_id(product_id)
    if not product_oid:
        return jsonify({"error": "invalid product_id"}), 400
    payload = _get_json_body()
    seller_id_raw = (payload.get('seller_id') or '').strip()
    seller_oid = _parse_object_id(seller_id_raw)
    if not seller_oid:
        return jsonify({"error": "seller_id is required"}), 400

    updates: Dict[str, Any] = {}
    for field in ["name", "price", "stock", "description", "expiry_date", "quality_condition", "category", "status"]:
        if field in payload:
            updates[field] = payload[field]
    if not updates:
        return jsonify({"error": "no fields to update"}), 400
    updates["updated_at"] = _now()

    col = _seller_collection(SELLER_PRODUCTS_COLLECTION)
    result = col.update_one({"_id": product_oid, "seller_id": seller_oid}, {"$set": updates})
    if result.matched_count == 0:
        return jsonify({"error": "not found"}), 404
    _log_history(seller_oid, "product_update", {"product_id": str(product_oid), "fields": list(updates.keys())})
    return jsonify({"status": "ok"}), 200


@app.route('/scrape/instamart', methods=['POST'])
def scrape_instamart():
    data = _get_json_body()
    term = (data.get('product') or '').strip()
    if not term:
        return jsonify({"error": "product is required"}), 400

    env = os.environ.copy()
    env['SEARCH_TERMS'] = term

    try:
        result = subprocess.run(
            [sys.executable, 'scraped_instamart.py'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            errors='ignore',
        )
        resp: JsonDict = {
            "status": "ok" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stderr_tail": result.stderr.splitlines()[-10:] if result.stderr else [],
            "output_file": env.get('OUTPUT_FILE', 'scraped_data.json'),
            "term": term,
        }

        try:
            with open(LAST_TERM_FILE, 'w', encoding='utf-8') as fh:
                fh.write(term)
        except Exception:
            pass
        return jsonify(resp), (200 if result.returncode == 0 else 500)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "scrape timed out"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/results', methods=['GET'])
def results():
    term = (request.args.get('term') or '').strip()
    if not term:
        return jsonify({"error": "term is required"}), 400

    try:
        col = mongo_client.get_collection(term, db_name=ZEPTO_DB)
        mongo_client.ensure_indexes(col, term, db_name=ZEPTO_DB)

        # Use case-insensitive partial match within the term-specific collection.
        regex = {"$regex": term, "$options": "i"}
        cursor = col.find({"search_term": regex}).sort("_id", -1).limit(100)

        items: list[JsonDict] = []
        for doc in cursor:
            doc['_id'] = str(doc.get('_id'))
            items.append(doc)

        # Fallback to local JSON if Mongo is empty or unreachable.
        if not items:
            data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_data.json')
            try:
                if os.path.exists(data_path):
                    with open(data_path, 'r', encoding='utf-8') as fh:
                        data = cast(list[JsonDict], json.load(fh) or [])
                    for row in data:
                        if term.lower() in (row.get('search_term', '').lower()):
                            # Normalize _id for JSON compatibility
                            if '_id' in row and not isinstance(row['_id'], str):
                                row['_id'] = str(row['_id'])
                            items.append(row)
            except Exception:
                # If the fallback fails, continue with whatever we have (likely empty).
                pass

        return jsonify({"items": items}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/results/instamart', methods=['GET'])
def results_instamart():
    term = (request.args.get('term') or '').strip()
    if not term:
        return jsonify({"error": "term is required"}), 400

    try:
        collection_name = term
        col = mongo_client.get_collection(collection_name, db_name=INSTAMART_DB)
        mongo_client.ensure_indexes(col, collection_name, db_name=INSTAMART_DB)

        regex = {"$regex": term, "$options": "i"}
        cursor = col.find({"search_term": regex}).sort("_id", -1).limit(100)

        items: list[JsonDict] = []
        for doc in cursor:
            doc['_id'] = str(doc.get('_id'))
            items.append(doc)

        # Fallback to JSON if Mongo is empty or unreachable.
        if not items:
            data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_data.json')
            try:
                if os.path.exists(data_path):
                    with open(data_path, 'r', encoding='utf-8') as fh:
                        data = cast(list[JsonDict], json.load(fh) or [])
                    for row in data:
                        if term.lower() in (row.get('search_term', '').lower()) and (row.get('platform') or '').lower().startswith('insta'):
                            if '_id' in row and not isinstance(row['_id'], str):
                                row['_id'] = str(row['_id'])
                            items.append(row)
            except Exception:
                pass

        return jsonify({"items": items}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/latest', methods=['GET'])
def latest():
    """Return the most recent scraped items without needing a search term."""
    try:
        # Attempt to read last term for UX context
        last_term = None
        if os.path.exists(LAST_TERM_FILE):
            try:
                with open(LAST_TERM_FILE, 'r', encoding='utf-8') as fh:
                    last_term = fh.read().strip() or None
            except Exception:
                pass

        # Decide which collection to read: last term if available, else default
        col = mongo_client.get_collection(last_term, db_name=ZEPTO_DB)
        mongo_client.ensure_indexes(col, last_term, db_name=ZEPTO_DB)

        cursor = col.find().sort("_id", -1).limit(100)
        items: list[JsonDict] = []
        for doc in cursor:
            doc['_id'] = str(doc.get('_id'))
            items.append(doc)

        # Fallback to JSON if Mongo is empty
        if not items:
            data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_data.json')
            try:
                if os.path.exists(data_path):
                    with open(data_path, 'r', encoding='utf-8') as fh:
                        items = cast(list[JsonDict], json.load(fh) or [])
            except Exception:
                items = []

        return jsonify({"items": items, "last_term": last_term}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/latest/instamart', methods=['GET'])
def latest_instamart():
    """Return latest Instamart scraped items."""
    try:
        last_term = None
        if os.path.exists(LAST_TERM_FILE):
            try:
                with open(LAST_TERM_FILE, 'r', encoding='utf-8') as fh:
                    last_term = fh.read().strip() or None
            except Exception:
                pass

        collection_name = last_term
        col = mongo_client.get_collection(collection_name, db_name=INSTAMART_DB)
        mongo_client.ensure_indexes(col, collection_name, db_name=INSTAMART_DB)

        cursor = col.find().sort("_id", -1).limit(100)
        items: list[JsonDict] = []
        for doc in cursor:
            doc['_id'] = str(doc.get('_id'))
            items.append(doc)

        if not items:
            data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_data.json')
            try:
                if os.path.exists(data_path):
                    with open(data_path, 'r', encoding='utf-8') as fh:
                        data = cast(list[JsonDict], json.load(fh) or [])
                    items = [row for row in data if (row.get('platform') or '').lower().startswith('insta')]
            except Exception:
                items = []

        return jsonify({"items": items, "last_term": last_term}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
