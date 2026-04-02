from flask import Flask, Response, request, jsonify
import os
import subprocess
import sys
import mongo_client
from typing import Any, Dict, List, Optional, Protocol, cast
from pymongo.collection import Collection
from pymongo.cursor import Cursor

app = Flask(__name__)

BLINKIT_DB = os.getenv("BLINKIT_DB", "snapit_blinkit")
BLINKIT_URI = os.getenv("BLINKIT_MONGO_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017"))
LAST_TERM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_search_term_blinkit.txt')
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_blinkit.json')

class _EnsureIndexes(Protocol):
    def __call__(
        self,
        col: Collection[Any],
        collection_name: Optional[str] = None,
        db_name: Optional[str] = None,
        uri: Optional[str] = None,
    ) -> None: ...

ENSURE_INDEXES: _EnsureIndexes = cast(_EnsureIndexes, mongo_client.ensure_indexes)

@app.after_request
def add_cors_headers(resp: Response) -> Response:
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    return resp

@app.route('/scrape', methods=['POST'])
def scrape():
    data: Dict[str, Any] = cast(Dict[str, Any], request.get_json(silent=True) or {})
    term: str = str(data.get('product') or '').strip()
    if not term:
        return jsonify({"error": "product is required"}), 400

    env = os.environ.copy()
    env['SEARCH_TERMS'] = term
    env['OUTPUT_FILE'] = os.path.basename(DATA_FILE)

    try:
        result = subprocess.run(
            [sys.executable, 'scraped_blinkit.py'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            errors='ignore',
        )
        resp: Dict[str, Any] = {
            "status": "ok" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stderr_tail": result.stderr.splitlines()[-10:] if result.stderr else [],
            "output_file": os.path.basename(DATA_FILE),
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
        primary_col: Collection[Dict[str, Any]] = mongo_client.get_collection(term, db_name=BLINKIT_DB, uri=BLINKIT_URI)
        ENSURE_INDEXES(primary_col, term, BLINKIT_DB, BLINKIT_URI)
        cursor: Cursor[Dict[str, Any]] = primary_col.find({"search_term": {"$regex": term, "$options": "i"}}).sort("_id", -1).limit(100)
        items: List[Dict[str, Any]] = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]

        if not items:
            alt_name = f"blinkit_{term}"
            alt_col: Collection[Dict[str, Any]] = mongo_client.get_collection(alt_name, db_name=BLINKIT_DB, uri=BLINKIT_URI)
            ENSURE_INDEXES(alt_col, alt_name, BLINKIT_DB, BLINKIT_URI)
            cursor = alt_col.find({"search_term": {"$regex": term, "$options": "i"}}).sort("_id", -1).limit(100)
            items = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]
        return jsonify({"items": items}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/latest', methods=['GET'])
def latest():
    try:
        last_term: Optional[str] = None
        if os.path.exists(LAST_TERM_FILE):
            try:
                with open(LAST_TERM_FILE, 'r', encoding='utf-8') as fh:
                    last_term = fh.read().strip() or None
            except Exception:
                pass

        col: Collection[Dict[str, Any]] = mongo_client.get_collection(last_term, db_name=BLINKIT_DB, uri=BLINKIT_URI)
        ENSURE_INDEXES(col, last_term, BLINKIT_DB, BLINKIT_URI)
        cursor = col.find().sort("_id", -1).limit(100)
        items: List[Dict[str, Any]] = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]

        if not items and last_term:
            alt_name = f"blinkit_{last_term}"
            alt_col: Collection[Dict[str, Any]] = mongo_client.get_collection(alt_name, db_name=BLINKIT_DB, uri=BLINKIT_URI)
            ENSURE_INDEXES(alt_col, alt_name, BLINKIT_DB, BLINKIT_URI)
            cursor = alt_col.find().sort("_id", -1).limit(100)
            items = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]
        return jsonify({"items": items, "last_term": last_term}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
