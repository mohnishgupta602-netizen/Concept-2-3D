import os
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
