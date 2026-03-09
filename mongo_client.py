import os
from typing import Any, Dict, Iterable, List, Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

# Configure via environment variables (defaults to local Mongo)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
# Default DB for Zepto; other sources should pass db_name explicitly (e.g., blinkit, instamart)
MONGO_DB = os.getenv("MONGO_DB", "snapit_zepto")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "prices")

# Cache clients per URI so different sources can use separate DBs/URIs
_clients: Dict[str, MongoClient[Any]] = {}
# Track indexes per uri.db.collection
_indexes_created: Dict[str, bool] = {}


def normalize_collection_name(name: Optional[str]) -> str:
    """Normalize user-provided term to a safe Mongo collection name."""
    if not name:
        return MONGO_COLLECTION
    cleaned = name.strip().lower().replace(" ", "_")
    return cleaned or MONGO_COLLECTION


def _get_client_for_uri(uri: Optional[str]) -> MongoClient[Any]:
    target_uri = uri or MONGO_URI
    if not target_uri:
        raise RuntimeError("MONGO_URI is not set. Please export your MongoDB connection string.")
    if target_uri not in _clients:
        _clients[target_uri] = MongoClient(target_uri)
    return _clients[target_uri]


def get_collection(
    name: Optional[str] = None,
    db_name: Optional[str] = None,
    uri: Optional[str] = None,
) -> Collection[Dict[str, Any]]:
    """Return a collection; db_name defaults to env MONGO_DB; uri can override MONGO_URI."""
    client: MongoClient[Any] = _get_client_for_uri(uri)
    db: Database[Any] = client[db_name or MONGO_DB]
    collection_name = normalize_collection_name(name)
    return db[collection_name]


def ensure_indexes(
    col: Collection[Dict[str, Any]],
    collection_name: Optional[str] = None,
    db_name: Optional[str] = None,
    uri: Optional[str] = None,
) -> None:
    name = normalize_collection_name(collection_name)
    key = f"{uri or MONGO_URI}.{db_name or MONGO_DB}.{name}"
    if _indexes_created.get(key):
        return
    col.create_index("product_name")
    col.create_index("search_term")
    col.create_index("location")
    _indexes_created[key] = True


def save_records(
    records: Iterable[Dict[str, Any]],
    collection_name: Optional[str] = None,
    db_name: Optional[str] = None,
    uri: Optional[str] = None,
) -> int:
    """Insert a list of dicts into the given collection and db."""
    materialized: List[Dict[str, Any]] = [dict(rec) for rec in records]
    if not materialized:
        return 0
    col = get_collection(collection_name, db_name=db_name, uri=uri)
    ensure_indexes(col, collection_name, db_name=db_name, uri=uri)
    # Insert copies so the original records are not mutated with Mongo _id fields
    result = col.insert_many(materialized)
    return len(result.inserted_ids)


if __name__ == "__main__":
    # Example usage: set env vars, then run this file to test the connection
    try:
        inserted = save_records([{"ping": "ok"}])
        print(f"Inserted {inserted} test record(s) into {MONGO_DB}.{MONGO_COLLECTION}")
    except Exception as exc:
        print(f"Mongo test failed: {exc}")
