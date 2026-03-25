import os
import chromadb
import json
import time

class QueryCache:
    def __init__(self, db_path=None, ttl_seconds=None):
        base_dir = os.path.dirname(__file__)
        resolved_path = db_path or os.path.join(base_dir, "chroma_db_final")
        raw_ttl = ttl_seconds if ttl_seconds is not None else os.getenv("CACHE_TTL_SECONDS", "21600")
        try:
            self.ttl_seconds = int(raw_ttl)
        except Exception:
            self.ttl_seconds = 21600

        if self.ttl_seconds <= 0:
            self.ttl_seconds = None

        self.client = chromadb.PersistentClient(path=resolved_path)
        # Create or get the collection for storing model query responses
        self.collection = self.client.get_or_create_collection(
            name="3d_model_cache"
        )
        
    def get_cached_results(self, query: str):
        # We search for the exact query or very similar
        # For a simple cache, we can just use the query as the ID if we want exact matches,
        # but Chroma allows semantic search too. Let's do a simple text query for exact match first.
        try:
            results = self.collection.get(ids=[query.lower()])
            if results and results.get("metadatas") and len(results["metadatas"]) > 0:
                metadata = results["metadatas"][0] or {}
                raw_data = metadata.get("response_json")
                cached_at = metadata.get("cached_at")

                if self.ttl_seconds and cached_at is not None:
                    age = time.time() - float(cached_at)
                    if age > self.ttl_seconds:
                        try:
                            self.collection.delete(ids=[query.lower()])
                        except Exception:
                            pass
                        return None

                if raw_data:
                    return json.loads(raw_data)
        except Exception as e:
            print(f"Cache miss or error: {e}")
        return None

    def cache_results(self, query: str, data: list):
        try:
            self.collection.upsert(
                documents=[query],
                metadatas=[{"response_json": json.dumps(data), "cached_at": time.time()}],
                ids=[query.lower()]
            )
        except Exception as e:
            print(f"Failed to cache results: {e}")

    def clear_cache(self, query: str | None = None):
        try:
            if query:
                self.collection.delete(ids=[query.lower()])
                return 1

            ids_payload = self.collection.get(include=[])
            ids = ids_payload.get("ids", []) if isinstance(ids_payload, dict) else []
            if not ids:
                return 0

            self.collection.delete(ids=ids)
            return len(ids)
        except Exception as e:
            print(f"Failed to clear cache: {e}")
            return 0
