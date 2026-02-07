from flask import Flask, request, jsonify
import json
import os
import subprocess
import sys
import mongo_client

app = Flask(__name__)

ZEPTO_DB = os.getenv("MONGO_DB", "snapit_zepto")
INSTAMART_DB = os.getenv("INSTAMART_DB", "snapit_instamart")

LAST_TERM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_search_term.txt')

# Simple CORS allow-all for local dev
@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    return resp

@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.get_json(silent=True) or {}
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
        resp = {
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


@app.route('/scrape/instamart', methods=['POST'])
def scrape_instamart():
    data = request.get_json(silent=True) or {}
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
        resp = {
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

        items = []
        for doc in cursor:
            doc['_id'] = str(doc.get('_id'))
            items.append(doc)

        # Fallback to local JSON if Mongo is empty or unreachable.
        if not items:
            data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_data.json')
            try:
                if os.path.exists(data_path):
                    with open(data_path, 'r', encoding='utf-8') as fh:
                        data = json.load(fh) or []
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

        items = []
        for doc in cursor:
            doc['_id'] = str(doc.get('_id'))
            items.append(doc)

        # Fallback to JSON if Mongo is empty or unreachable.
        if not items:
            data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_data.json')
            try:
                if os.path.exists(data_path):
                    with open(data_path, 'r', encoding='utf-8') as fh:
                        data = json.load(fh) or []
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
        items = []
        for doc in cursor:
            doc['_id'] = str(doc.get('_id'))
            items.append(doc)

        # Fallback to JSON if Mongo is empty
        if not items:
            data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_data.json')
            try:
                if os.path.exists(data_path):
                    with open(data_path, 'r', encoding='utf-8') as fh:
                        items = json.load(fh) or []
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
        items = []
        for doc in cursor:
            doc['_id'] = str(doc.get('_id'))
            items.append(doc)

        if not items:
            data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_data.json')
            try:
                if os.path.exists(data_path):
                    with open(data_path, 'r', encoding='utf-8') as fh:
                        data = json.load(fh) or []
                    items = [row for row in data if (row.get('platform') or '').lower().startswith('insta')]
            except Exception:
                items = []

        return jsonify({"items": items, "last_term": last_term}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
