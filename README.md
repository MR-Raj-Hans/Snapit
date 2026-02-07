# SnapIt Zepto + Blinkit Scraper/Viewer

End-to-end setup to scrape products from Zepto and Blinkit, store them in MongoDB (with JSON fallback), and view merged results on a local product page. Includes auto-retry search UX and both Flask backends.

## What’s in this repo
- `scraped.py` — Zepto scraper (headless Chrome via undetected-chromedriver) writing to MongoDB (db `snapit_zepto`, collection per search term) and `scraped_data.json` fallback.
- `scraped_blinkit.py` — Blinkit scraper writing to MongoDB (db `snapit_blinkit`, collection per term prefixed with `blinkit_`) and `scraped_blinkit.json` fallback.
- `server.py` — Flask API for Zepto: `/scrape`, `/results`, `/latest`.
- `server_blinkit.py` — Flask API for Blinkit: `/scrape`, `/results`, `/latest`.
- `htmlfile/product.html` + `product.js` — Frontend that searches both backends, auto-retries, and renders merged results.
- `mongo_client.py` — Mongo helpers (per-collection indexes, connection handling).
- `requirements.txt` — Pinned Python deps.

## Requirements
- Python 3.10+ (venv recommended)
- Google Chrome installed (undetected-chromedriver will download a matching driver)
- MongoDB (local default `mongodb://localhost:27017`; overridable via env vars)

### Quick Mongo primer (local)
- Install MongoDB Community and start the `mongod` service (default port 27017).
- Collections are created on first insert; no manual table creation is required. If you want to pre-create:
	- Open a shell: `mongosh`
	- Select DBs: `use snapit_zepto` and `use snapit_blinkit`
	- Optionally create term collections: `db.createCollection("banana")`, `db.createCollection("blinkit_banana")`
- Default DB/collections used:
	- Zepto: DB `snapit_zepto`, collection per term (e.g., `banana`).
	- Blinkit: DB `snapit_blinkit`, collection per term with prefix `blinkit_<term>` (e.g., `blinkit_banana`).

## Install deps
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Environment variables (optional)
- `MONGO_URI` — default Mongo connection (used by Zepto unless overridden)
- `BLINKIT_MONGO_URI` — Blinkit Mongo override (else falls back to `MONGO_URI`)
- `MONGO_DB` — Zepto DB name (default `snapit_zepto`)
- `BLINKIT_DB` — Blinkit DB name (default `snapit_blinkit`)
- `OUTPUT_FILE` — Zepto JSON fallback path (default `scraped_data.json`)
- `BLINKIT_MAX_RESULTS` — cap Blinkit items (default 12)
- `ZEPTO_MAX_RESULTS` — cap Zepto items (default 12)
- `HEADLESS` — set to `0` to see browser UI (Blinkit scraper)
- `BLINKIT_LAT` / `BLINKIT_LNG` — fake geo for Blinkit (defaults to Bangalore coords)

## Running the backends
Use the venv Python for both:
```bash
# Terminal 1 (Zepto API on 5000)
.\.venv\Scripts\activate
python server.py

# Terminal 2 (Blinkit API on 5001)
.\.venv\Scripts\activate
python server_blinkit.py
```

## Using the frontend (product page)
Open `htmlfile/product.html` in a browser (file:// is fine). The page:
- Calls Zepto `/results` and Blinkit `/results` on Enter.
- Auto-retries the same search term up to 3 times, 20s apart, without clearing the search box.
- Renders whichever source returns (Zepto or Blinkit) and prioritizes the current term at the top.
- “Load Latest” pulls `/latest` from both servers.

## Triggering scrapes
### From the product page
- Type a term, press Enter. The page first tries existing DB data; if empty, it triggers both scrapes, then auto-retries fetch/scrape as above.

### Direct API calls
- Zepto scrape: `POST http://localhost:5000/scrape` with JSON `{ "product": "banana" }`
- Blinkit scrape: `POST http://localhost:5001/scrape` with JSON `{ "product": "banana" }`
- Zepto results: `GET http://localhost:5000/results?term=banana`
- Blinkit results: `GET http://localhost:5001/results?term=banana`
- Zepto latest: `GET http://localhost:5000/latest`
- Blinkit latest: `GET http://localhost:5001/latest`

## Data model and Mongo
- Zepto DB: `snapit_zepto` (default). Collection per term (e.g., `banana`). Fields: `search_term`, `product_name`, `price`, `quantity`, `platform`, `location`, `url`, `image_url`, `raw_text`.
- Blinkit DB: `snapit_blinkit` (default). Collections named `blinkit_<term>` (e.g., `blinkit_banana`). Same fields as above (no image_url currently). JSON fallbacks: `scraped_data.json`, `scraped_blinkit.json`.
- Indexes on `product_name`, `search_term`, `location` are created automatically per collection.

## Linking to a different Mongo
Set `MONGO_URI` (and optionally `BLINKIT_MONGO_URI`) before running servers or scrapers, e.g.:
```bash
$env:MONGO_URI = "mongodb://user:pass@host:27017/dbname"
python server.py
```

## Frontend behavior details
- Single Enter starts the flow and leaves the term in the box; auto-retries happen in the background.
- Groups by `product_name` and shows platform badges (Z for Zepto, B for Blinkit).
- Opens product URL in a new tab when a price row is clicked (if URL is present).

## Troubleshooting
- Ensure Chrome is installed; if the driver download stalls, re-run the scraper. You can set `HEADLESS=0` to watch the browser.
- Blinkit naming: data is stored in `blinkit_<term>` (e.g., `blinkit_atta`). The API now falls back to that name if a plain term collection is empty.
- Blinkit `/latest` JSON errors: fixed by guarding bad/empty `scraped_blinkit.json`; if corrupted, delete the file and restart `server_blinkit.py`.
- Zepto empty results for some terms: scraper now waits longer, scrolls, and captures up to 12 items (`ZEPTO_MAX_RESULTS`). If still empty, rerun with HEADLESS=0 to inspect selectors.
- Servers must run with the venv Python (`.venv\Scripts\python.exe`) on ports 5000 (Zepto) and 5001 (Blinkit). Restart after code changes.
- If no results appear: verify both servers are up; check Mongo collections (`banana`, `blinkit_banana`, etc.); trigger a fresh scrape via API or the product page.
- Network/port conflicts: ensure nothing else is bound to 5000/5001.
- Slow sites: the product page auto-retries the same term 3 times, 20s apart, without clearing the search box; you only press Enter once.

## Quick start checklist
1) Create/activate venv, `pip install -r requirements.txt`.
2) Start `server.py` (5000) and `server_blinkit.py` (5001) with venv Python.
3) Open `htmlfile/product.html` and search a term. Wait for auto-retries if needed.
4) Verify data in Mongo (`snapit_zepto` / `snapit_blinkit`) or JSON fallbacks.
