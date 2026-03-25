import os
import time
from pymongo import MongoClient

def get_db():
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
    try:
        # 2000 ms timeout to fail fast if no local db is running
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
        # Test connection
        client.admin.command('ping')
        return client["concept3d"]
    except Exception as e:
        print("MongoDB connection not available, proceeding without caching:", e)
        return None


def save_search_result(concept, model_name, description, similarity_score, source):
    db = get_db()
    if db is not None:
        try:
            collection = db["searches"]
            collection.insert_one({
                "concept": concept,
                "model_name": model_name,
                "description": description,
                "similarity_score": similarity_score,
                "source": source
            })
        except Exception as e:
            print("Failed to save search result:", e)

# --- New: Model part labeling ---
def save_part_labels(model_id, part_labels):
    db = get_db()
    if db is not None:
        try:
            collection = db["part_labels"]
            collection.update_one(
                {"model_id": model_id},
                {"$set": {"part_labels": part_labels}},
                upsert=True
            )
        except Exception as e:
            print("Failed to save part labels:", e)

def get_part_labels(model_id):
    db = get_db()
    if db is not None:
        try:
            collection = db["part_labels"]
            doc = collection.find_one({"model_id": model_id})
            return doc["part_labels"] if doc else None
        except Exception as e:
            print("Failed to get part labels:", e)
    return None

# --- New: User feedback ---
def submit_feedback(model_id, user_id, rating, comment=None):
    """Submit user feedback with 0.5 increment rating enforcement."""
    db = get_db()
    if db is not None:
        try:
            # Enforce 0.5 increment ratings
            rating = max(1.0, min(5.0, round(rating * 2) / 2))
            
            collection = db["feedback"]
            feedback = {
                "model_id": model_id,
                "user_id": user_id,
                "rating": rating,
                "comment": comment,
                "timestamp": int(time.time())
            }
            collection.insert_one(feedback)
            
            # Check if model should be cached based on rating
            avg_rating, count = get_average_rating(model_id)
            if avg_rating >= 3.5 and count >= 3:
                set_model_cached(model_id, True)
                print(f"[Cache] Model {model_id} cached due to high rating ({avg_rating:.1f})")
            
        except Exception as e:
            print("Failed to submit feedback:", e)

def get_feedback(model_id):
    db = get_db()
    if db is not None:
        try:
            collection = db["feedback"]
            return list(collection.find({"model_id": model_id}))
        except Exception as e:
            print("Failed to get feedback:", e)
    return []

def get_average_rating(model_id):
    db = get_db()
    if db is not None:
        try:
            collection = db["feedback"]
            pipeline = [
                {"$match": {"model_id": model_id}},
                {"$group": {"_id": "$model_id", "avg_rating": {"$avg": "$rating"}, "count": {"$sum": 1}}}
            ]
            result = list(collection.aggregate(pipeline))
            if result:
                return result[0]["avg_rating"], result[0]["count"]
        except Exception as e:
            print("Failed to get average rating:", e)
    return 0.0, 0

# --- New: Model cache status ---
def set_model_cached(model_id, cached=True):
    db = get_db()
    if db is not None:
        try:
            collection = db["model_cache"]
            collection.update_one(
                {"model_id": model_id},
                {"$set": {"cached": cached, "updated": int(time.time())}},
                upsert=True
            )
        except Exception as e:
            print("Failed to set model cache status:", e)

def is_model_cached(model_id):
    db = get_db()
    if db is not None:
        try:
            collection = db["model_cache"]
            doc = collection.find_one({"model_id": model_id})
            return bool(doc and doc.get("cached"))
        except Exception as e:
            print("Failed to get model cache status:", e)
    return False


# --- New: Training feedback for model improvement ---
def add_training_feedback(concept, model_id, model_source, rating, user_feedback=""):
    """Store training data for recursive model improvement."""
    db = get_db()
    if db is not None:
        try:
            collection = db["training_data"]
            training_entry = {
                "concept": concept,
                "model_id": model_id,
                "model_source": model_source,
                "rating": rating,
                "user_feedback": user_feedback,
                "timestamp": int(time.time()),
                "processed": False  # Flag for batch training
            }
            collection.insert_one(training_entry)
            
            # Update concept quality metrics
            _update_concept_metrics(concept, rating)
            
        except Exception as e:
            print("Failed to add training feedback:", e)


def _update_concept_metrics(concept, rating):
    """Update quality metrics for a concept to improve future searches."""
    db = get_db()
    if db is not None:
        try:
            collection = db["concept_metrics"]
            
            # Get current metrics
            doc = collection.find_one({"concept": concept})
            if doc:
                total_ratings = doc.get("total_ratings", 0) + 1
                sum_ratings = doc.get("sum_ratings", 0) + rating
                avg_rating = sum_ratings / total_ratings
                
                collection.update_one(
                    {"concept": concept},
                    {"$set": {
                        "total_ratings": total_ratings,
                        "sum_ratings": sum_ratings,
                        "avg_rating": avg_rating,
                        "last_updated": int(time.time())
                    }}
                )
            else:
                collection.insert_one({
                    "concept": concept,
                    "total_ratings": 1,
                    "sum_ratings": rating,
                    "avg_rating": rating,
                    "last_updated": int(time.time())
                })
        except Exception as e:
            print("Failed to update concept metrics:", e)


def get_concept_quality_score(concept):
    """Get historical quality score for a concept (0-1 scale)."""
    db = get_db()
    if db is not None:
        try:
            collection = db["concept_metrics"]
            doc = collection.find_one({"concept": concept})
            if doc and doc.get("total_ratings", 0) >= 3:
                # Normalize 1-5 rating to 0-1
                return (doc["avg_rating"] - 1) / 4.0
        except Exception as e:
            print("Failed to get concept quality:", e)
    return 0.5  # Default neutral score


def get_training_batch(limit=100):
    """Get unprocessed training data for model improvement."""
    db = get_db()
    if db is not None:
        try:
            collection = db["training_data"]
            batch = list(collection.find({"processed": False}).limit(limit))
            return batch
        except Exception as e:
            print("Failed to get training batch:", e)
    return []


def mark_training_processed(entry_ids):
    """Mark training entries as processed."""
    db = get_db()
    if db is not None:
        try:
            collection = db["training_data"]
            from bson.objectid import ObjectId

            if not isinstance(entry_ids, list):
                entry_ids = [entry_ids]

            normalized_ids = []
            for oid in entry_ids:
                if oid is None:
                    continue
                if isinstance(oid, ObjectId):
                    normalized_ids.append(oid)
                else:
                    normalized_ids.append(ObjectId(str(oid)))

            if not normalized_ids:
                return

            collection.update_many(
                {"_id": {"$in": normalized_ids}},
                {"$set": {"processed": True, "processed_at": int(time.time())}}
            )
        except Exception as e:
            print("Failed to mark training processed:", e)
