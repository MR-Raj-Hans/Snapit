from flask import Flask, request, jsonify
import json
import os
import subprocess
import sys
import mongo_client

app = Flask(__name__)

INSTAMART_DB = os.getenv("INSTAMART_DB", "snapit_instamart")
INSTAMART_URI = os.getenv("INSTAMART_MONGO_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017"))
LAST_TERM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_search_term_instamart.txt')
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_instamart.json')

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
    env['OUTPUT_FILE'] = os.path.basename(DATA_FILE)

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

def _results_core(term: str):
    if not term:
        return jsonify({"error": "term is required"}), 400
    collection_name = f"instamart_{term}"
    try:
        col = mongo_client.get_collection(collection_name, db_name=INSTAMART_DB, uri=INSTAMART_URI)
        mongo_client.ensure_indexes(col, collection_name, db_name=INSTAMART_DB, uri=INSTAMART_URI)
        cursor = col.find({"search_term": {"$regex": term, "$options": "i"}}).sort("_id", -1).limit(100)
        items = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]
        if not items and os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as fh:
                data = json.load(fh) or []
            for row in data:
                if term.lower() in (row.get('search_term', '').lower()) and (row.get('platform') or '').lower().startswith('insta'):
                    if '_id' in row and not isinstance(row['_id'], str):
                        row['_id'] = str(row['_id'])
                    items.append(row)
        return jsonify({"items": items}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/results', methods=['GET'])
@app.route('/results/instamart', methods=['GET'])
def results():
    term = (request.args.get('term') or '').strip()
    return _results_core(term)

@app.route('/latest', methods=['GET'])
@app.route('/latest/instamart', methods=['GET'])
def latest():
    try:
        last_term = None
        if os.path.exists(LAST_TERM_FILE):
            try:
                with open(LAST_TERM_FILE, 'r', encoding='utf-8') as fh:
                    last_term = fh.read().strip() or None
            except Exception:
                pass

        collection_name = f"instamart_{last_term}" if last_term else last_term
        col = mongo_client.get_collection(collection_name, db_name=INSTAMART_DB, uri=INSTAMART_URI)
        mongo_client.ensure_indexes(col, collection_name, db_name=INSTAMART_DB, uri=INSTAMART_URI)
        cursor = col.find().sort("_id", -1).limit(100)
        items = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]
        if not items and os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as fh:
                items = json.load(fh) or []
        return jsonify({"items": items, "last_term": last_term}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
