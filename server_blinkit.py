from flask import Flask, request, jsonify
import json
import os
import subprocess
import sys
import mongo_client

app = Flask(__name__)

BLINKIT_DB = os.getenv("BLINKIT_DB", "snapit_blinkit")
BLINKIT_URI = os.getenv("BLINKIT_MONGO_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017"))
LAST_TERM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_search_term_blinkit.txt')
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scraped_blinkit.json')

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
            [sys.executable, 'scraped_blinkit.py'],
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

@app.route('/results', methods=['GET'])
def results():
    term = (request.args.get('term') or '').strip()
    if not term:
        return jsonify({"error": "term is required"}), 400
    try:
        primary_col = mongo_client.get_collection(term, db_name=BLINKIT_DB, uri=BLINKIT_URI)
        mongo_client.ensure_indexes(primary_col, term, db_name=BLINKIT_DB, uri=BLINKIT_URI)
        cursor = primary_col.find({"search_term": {"$regex": term, "$options": "i"}}).sort("_id", -1).limit(100)
        items = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]

        if not items:
            alt_name = f"blinkit_{term}"
            alt_col = mongo_client.get_collection(alt_name, db_name=BLINKIT_DB, uri=BLINKIT_URI)
            mongo_client.ensure_indexes(alt_col, alt_name, db_name=BLINKIT_DB, uri=BLINKIT_URI)
            cursor = alt_col.find({"search_term": {"$regex": term, "$options": "i"}}).sort("_id", -1).limit(100)
            items = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]
        if not items and os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as fh:
                    data = json.load(fh) or []
            except Exception:
                data = []
            for row in data:
                if term.lower() in (row.get('search_term', '').lower()) and (row.get('platform') or '').lower().startswith('blink'):
                    if '_id' in row and not isinstance(row['_id'], str):
                        row['_id'] = str(row['_id'])
                    items.append(row)
        return jsonify({"items": items}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/latest', methods=['GET'])
def latest():
    try:
        last_term = None
        if os.path.exists(LAST_TERM_FILE):
            try:
                with open(LAST_TERM_FILE, 'r', encoding='utf-8') as fh:
                    last_term = fh.read().strip() or None
            except Exception:
                pass

        col = mongo_client.get_collection(last_term, db_name=BLINKIT_DB, uri=BLINKIT_URI)
        mongo_client.ensure_indexes(col, last_term, db_name=BLINKIT_DB, uri=BLINKIT_URI)
        cursor = col.find().sort("_id", -1).limit(100)
        items = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]

        if not items and last_term:
            alt_name = f"blinkit_{last_term}"
            alt_col = mongo_client.get_collection(alt_name, db_name=BLINKIT_DB, uri=BLINKIT_URI)
            mongo_client.ensure_indexes(alt_col, alt_name, db_name=BLINKIT_DB, uri=BLINKIT_URI)
            cursor = alt_col.find().sort("_id", -1).limit(100)
            items = [{**doc, '_id': str(doc.get('_id'))} for doc in cursor]
        if not items and os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as fh:
                    items = json.load(fh) or []
            except Exception:
                items = []
        return jsonify({"items": items, "last_term": last_term}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
