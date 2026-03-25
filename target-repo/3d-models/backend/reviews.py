import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict

REVIEWS_DB = os.path.join(os.path.dirname(__file__), "reviews.db")

def init_reviews_db():
    """Initialize the reviews database schema."""
    conn = sqlite3.connect(REVIEWS_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(model_id, user_id)
        )
    """)
    
    conn.commit()
    conn.close()

def submit_review(model_id: str, user_id: str, rating: int, comment: str = "") -> Dict:
    """
    Submit or update a review for a model.
    Returns the review details.
    """
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be between 1 and 5")
    
    if not model_id or not user_id:
        raise ValueError("model_id and user_id are required")
    
    conn = sqlite3.connect(REVIEWS_DB)
    cursor = conn.cursor()
    
    comment = (comment or "").strip()
    now = datetime.utcnow().isoformat()
    
    cursor.execute("""
        INSERT OR REPLACE INTO reviews (model_id, user_id, rating, comment, created_at, updated_at)
        VALUES (?, ?, ?, ?, 
                COALESCE((SELECT created_at FROM reviews WHERE model_id = ? AND user_id = ?), ?),
                ?)
    """, (model_id, user_id, rating, comment, model_id, user_id, now, now))
    
    conn.commit()
    
    cursor.execute("""
        SELECT id, model_id, user_id, rating, comment, created_at, updated_at
        FROM reviews
        WHERE model_id = ? AND user_id = ?
    """, (model_id, user_id))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row[0],
            "model_id": row[1],
            "user_id": row[2],
            "rating": row[3],
            "comment": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }
    
    return {}

def get_reviews(model_id: str, limit: int = 50) -> List[Dict]:
    """
    Fetch all reviews for a model.
    Returns list of reviews sorted by creation date (newest first).
    """
    if not model_id:
        return []
    
    conn = sqlite3.connect(REVIEWS_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, model_id, user_id, rating, comment, created_at, updated_at
        FROM reviews
        WHERE model_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (model_id, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    reviews = []
    for row in rows:
        reviews.append({
            "id": row[0],
            "model_id": row[1],
            "user_id": row[2],
            "rating": row[3],
            "comment": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        })
    
    return reviews

def get_review_summary(model_id: str) -> Dict:
    """
    Get aggregate statistics (average rating, total count, distribution).
    """
    if not model_id:
        return {"avg_rating": 0, "total_reviews": 0, "distribution": {}}
    
    conn = sqlite3.connect(REVIEWS_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            AVG(rating) as avg_rating,
            COUNT(*) as total_reviews,
            SUM(CASE WHEN rating = 5 THEN 1 ELSE 0 END) as count_5,
            SUM(CASE WHEN rating = 4 THEN 1 ELSE 0 END) as count_4,
            SUM(CASE WHEN rating = 3 THEN 1 ELSE 0 END) as count_3,
            SUM(CASE WHEN rating = 2 THEN 1 ELSE 0 END) as count_2,
            SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as count_1
        FROM reviews
        WHERE model_id = ?
    """, (model_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row or row[1] == 0:
        return {
            "model_id": model_id,
            "avg_rating": 0,
            "total_reviews": 0,
            "distribution": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
        }
    
    return {
        "model_id": model_id,
        "avg_rating": round(row[0] or 0, 1),
        "total_reviews": row[1],
        "distribution": {
            "5": row[2] or 0,
            "4": row[3] or 0,
            "3": row[4] or 0,
            "2": row[5] or 0,
            "1": row[6] or 0,
        }
    }

def get_user_review(model_id: str, user_id: str) -> Optional[Dict]:
    """
    Get the current user's review for a specific model.
    """
    if not model_id or not user_id:
        return None
    
    conn = sqlite3.connect(REVIEWS_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, model_id, user_id, rating, comment, created_at, updated_at
        FROM reviews
        WHERE model_id = ? AND user_id = ?
    """, (model_id, user_id))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "id": row[0],
        "model_id": row[1],
        "user_id": row[2],
        "rating": row[3],
        "comment": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }

# Initialize DB on module import
init_reviews_db()
