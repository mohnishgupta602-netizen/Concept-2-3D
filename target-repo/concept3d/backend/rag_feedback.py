"""
RAG-based Feedback System for Recursive Training

This module implements Retrieval-Augmented Generation for user feedback
to improve search results through historical pattern learning.
"""

import os
import time
import hashlib
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher

# Import Gemini for embeddings if available
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

# Import database functions
from database import get_db, get_concept_quality_score


class RAGFeedbackStore:
    """Store and retrieve feedback using RAG principles."""
    
    def __init__(self):
        self.db = get_db()
        self._embedding_cache = {}
        
    def _get_gemini_embedding(self, text: str) -> List[float]:
        """Get embedding from Gemini API."""
        if not GEMINI_AVAILABLE:
            return self._simple_embedding(text)
        
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return self._simple_embedding(text)
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-embedding-exp-03-07')
            result = genai.embed_content(model="models/embedding-001", content=text)
            return result['embedding']
        except Exception as e:
            print(f"[RAG] Gemini embedding failed: {e}")
            return self._simple_embedding(text)
    
    def _simple_embedding(self, text: str) -> List[float]:
        """Simple character-based embedding fallback."""
        # Create a simple 128-dim embedding based on character frequencies
        text = text.lower()
        embedding = [0.0] * 128
        for char in text:
            idx = ord(char) % 128
            embedding[idx] += 1.0
        # Normalize
        total = sum(embedding) or 1.0
        return [v / total for v in embedding]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    def _text_similarity(self, concept1: str, concept2: str) -> float:
        """Calculate text similarity using SequenceMatcher."""
        return SequenceMatcher(None, concept1.lower(), concept2.lower()).ratio()
    
    def store_feedback_with_embedding(
        self,
        concept: str,
        model_id: str,
        model_source: str,
        rating: float,
        user_feedback: str = "",
        search_params: Optional[Dict] = None
    ) -> bool:
        """
        Store user feedback with concept embedding for RAG retrieval.
        
        Args:
            concept: The search concept (e.g., "red vintage chair")
            model_id: Unique identifier for the model
            model_source: Source of the model (blenderkit, sketchfab, etc.)
            rating: User rating (1.0 - 5.0)
            user_feedback: Optional text feedback/comment
            search_params: Search parameters used (threshold, sources, etc.)
        """
        if self.db is None:
            return False
        
        try:
            # Get embedding for the concept
            embedding = self._get_gemini_embedding(concept)
            
            collection = self.db["rag_feedback"]
            
            # Create feedback document
            feedback_doc = {
                "concept": concept,
                "concept_embedding": embedding,
                "model_id": model_id,
                "model_source": model_source,
                "rating": rating,
                "user_feedback": user_feedback,
                "search_params": search_params or {},
                "timestamp": int(time.time()),
                "quality_score": self._calculate_quality_score(rating, user_feedback),
                "retrieval_count": 0  # Track how often this is retrieved
            }
            
            # Store in database
            collection.insert_one(feedback_doc)
            
            # Also update concept-performance index
            self._update_concept_performance(concept, model_source, rating)
            
            print(f"[RAG] Stored feedback for '{concept}' -> {model_source}/{model_id}: {rating} stars")
            return True
            
        except Exception as e:
            print(f"[RAG] Failed to store feedback: {e}")
            return False
    
    def _calculate_quality_score(self, rating: float, feedback: str) -> float:
        """Calculate overall quality score combining rating and feedback sentiment."""
        base_score = (rating - 1) / 4.0  # Normalize 1-5 to 0-1
        
        # Boost for detailed feedback
        if len(feedback) > 20:
            base_score += 0.1
        
        # Boost for keywords indicating success
        positive_keywords = ['perfect', 'exactly', 'great', 'excellent', 'love', 'perfect']
        if any(kw in feedback.lower() for kw in positive_keywords):
            base_score += 0.15
        
        return min(1.0, base_score)
    
    def _update_concept_performance(self, concept: str, source: str, rating: float):
        """Update per-concept source performance metrics."""
        try:
            collection = self.db["source_performance"]
            
            # Find existing or create new
            doc = collection.find_one({"concept": concept, "source": source})
            
            if doc:
                # Update rolling average
                total_ratings = doc.get("total_ratings", 0) + 1
                sum_ratings = doc.get("sum_ratings", 0) + rating
                
                collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "total_ratings": total_ratings,
                        "sum_ratings": sum_ratings,
                        "avg_rating": sum_ratings / total_ratings,
                        "last_updated": int(time.time())
                    }}
                )
            else:
                collection.insert_one({
                    "concept": concept,
                    "source": source,
                    "total_ratings": 1,
                    "sum_ratings": rating,
                    "avg_rating": rating,
                    "last_updated": int(time.time())
                })
        except Exception as e:
            print(f"[RAG] Failed to update concept performance: {e}")
    
    def retrieve_similar_feedback(
        self,
        concept: str,
        min_rating: float = 3.0,
        top_k: int = 5,
        similarity_threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Retrieve similar historical feedback using RAG.
        
        Args:
            concept: The search concept to find similar feedback for
            min_rating: Minimum rating to consider (3.0 = good+ ratings)
            top_k: Number of similar feedback items to retrieve
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of similar feedback documents with similarity scores
        """
        if self.db is None:
            return []
        
        try:
            # Get embedding for query concept
            query_embedding = self._get_gemini_embedding(concept)
            
            collection = self.db["rag_feedback"]
            
            # Get all feedback with good ratings
            good_feedback = list(collection.find({
                "rating": {"$gte": min_rating}
            }).limit(100))
            
            # Calculate similarity scores
            scored_feedback = []
            for feedback in good_feedback:
                # Combine embedding similarity and text similarity
                emb_sim = self._cosine_similarity(
                    query_embedding,
                    feedback.get("concept_embedding", [])
                )
                text_sim = self._text_similarity(concept, feedback.get("concept", ""))
                
                # Weighted combination
                combined_sim = (emb_sim * 0.7) + (text_sim * 0.3)
                
                if combined_sim >= similarity_threshold:
                    scored_feedback.append({
                        **feedback,
                        "similarity_score": combined_sim
                    })
            
            # Sort by similarity score
            scored_feedback.sort(key=lambda x: x["similarity_score"], reverse=True)
            
            # Return top_k
            results = scored_feedback[:top_k]
            
            # Update retrieval counts
            for item in results:
                collection.update_one(
                    {"_id": item["_id"]},
                    {"$inc": {"retrieval_count": 1}}
                )
            
            return results
            
        except Exception as e:
            print(f"[RAG] Failed to retrieve feedback: {e}")
            return []
    
    def get_source_recommendations(self, concept: str) -> Dict[str, float]:
        """
        Get source recommendations based on RAG feedback.
        
        Returns a score for each source (blenderkit, sketchfab, etc.)
        indicating likelihood of finding good results.
        """
        similar_feedback = self.retrieve_similar_feedback(concept, min_rating=3.5, top_k=20)
        
        if not similar_feedback:
            # No data - use defaults
            return {
                "blenderkit": 0.8,  # Always prioritize
                "sketchfab": 0.6,
                "poly_archive": 0.4,
                "poly_pizza": 0.4
            }
        
        # Aggregate scores by source
        source_scores = {}
        source_counts = {}
        
        for feedback in similar_feedback:
            source = feedback.get("model_source", "unknown")
            rating = feedback.get("rating", 3.0)
            sim_score = feedback.get("similarity_score", 0.5)
            
            # Weight by similarity
            weighted_rating = rating * sim_score
            
            if source not in source_scores:
                source_scores[source] = 0
                source_counts[source] = 0
            
            source_scores[source] += weighted_rating
            source_counts[source] += 1
        
        # Calculate average weighted scores
        recommendations = {}
        for source in source_scores:
            avg_score = source_scores[source] / source_counts[source]
            # Normalize to 0-1 range (rating 1-5 -> score 0.2-1.0)
            recommendations[source] = min(1.0, avg_score / 5.0)
        
        # Ensure all sources have a score
        for source in ["blenderkit", "sketchfab", "poly_archive", "poly_pizza"]:
            if source not in recommendations:
                recommendations[source] = 0.3  # Default low confidence
        
        return recommendations
    
    def get_search_enhancement(self, concept: str) -> Dict[str, Any]:
        """
        Get search enhancements based on RAG feedback analysis.
        
        Returns:
            - recommended_sources: List of sources to prioritize
            - avoid_models: List of model_ids that performed poorly
            - suggested_threshold: Adjusted confidence threshold
            - related_concepts: Similar successful search concepts
        """
        similar_feedback = self.retrieve_similar_feedback(concept, min_rating=3.0, top_k=10)
        poor_feedback = self.retrieve_similar_feedback(concept, min_rating=1.0, top_k=5)
        
        # Filter poor feedback (ratings < 2.5)
        poor_feedback = [f for f in poor_feedback if f.get("rating", 5) < 2.5]
        
        enhancement = {
            "recommended_sources": [],
            "avoid_models": [],
            "suggested_threshold": None,
            "related_concepts": [],
            "source_bias_adjustments": {}
        }
        
        if similar_feedback:
            # Get source recommendations
            source_recs = self.get_source_recommendations(concept)
            enhancement["recommended_sources"] = sorted(
                source_recs.keys(),
                key=lambda x: source_recs[x],
                reverse=True
            )
            enhancement["source_bias_adjustments"] = source_recs
            
            # Collect related concepts
            related = set()
            for fb in similar_feedback[:5]:
                related.add(fb.get("concept", ""))
            enhancement["related_concepts"] = list(related)
        
        if poor_feedback:
            # Collect models to avoid
            avoid = set()
            for fb in poor_feedback:
                avoid.add(fb.get("model_id", ""))
            enhancement["avoid_models"] = list(avoid)
        
        return enhancement


# Global instance
_rag_store = None

def get_rag_store() -> RAGFeedbackStore:
    """Get or create RAG feedback store singleton."""
    global _rag_store
    if _rag_store is None:
        _rag_store = RAGFeedbackStore()
    return _rag_store


def submit_rag_feedback(
    concept: str,
    model_id: str,
    model_source: str,
    rating: float,
    user_feedback: str = "",
    search_params: Optional[Dict] = None
) -> bool:
    """Convenience function to submit feedback to RAG store."""
    store = get_rag_store()
    return store.store_feedback_with_embedding(
        concept, model_id, model_source, rating, user_feedback, search_params
    )


def get_rag_search_enhancement(concept: str) -> Dict[str, Any]:
    """Convenience function to get RAG-based search enhancement."""
    store = get_rag_store()
    return store.get_search_enhancement(concept)


def get_rag_source_recommendations(concept: str) -> Dict[str, float]:
    """Get source recommendations based on RAG feedback."""
    store = get_rag_store()
    return store.get_source_recommendations(concept)
