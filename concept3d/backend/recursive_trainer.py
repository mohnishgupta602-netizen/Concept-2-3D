"""
Recursive Training Loop for Continuous Model Improvement

This module implements a feedback-driven training system that:
1. Periodically analyzes user feedback patterns
2. Adjusts search parameters based on historical performance
3. Updates confidence thresholds dynamically
4. Generates training reports
"""

import os
import time
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from database import get_db, get_training_batch, mark_training_processed
from rag_feedback import get_rag_store


@dataclass
class TrainingMetrics:
    """Metrics for a training cycle."""
    cycle_id: str
    timestamp: int
    total_feedback: int
    avg_rating: float
    source_performance: Dict[str, float]
    concept_performance: Dict[str, float]
    threshold_recommendation: float


class RecursiveTrainer:
    """
    Recursive training system that learns from user feedback
to continuously improve search quality.
    """
    
    def __init__(self):
        self.db = get_db()
        self.rag_store = get_rag_store()
        self.training_interval_hours = int(os.getenv("TRAINING_INTERVAL_HOURS", "24"))
        self.min_feedback_for_training = int(os.getenv("MIN_FEEDBACK_FOR_TRAINING", "10"))
        self.running = False
        self.thread = None
        self.last_training_time = 0
        
    def start_background_training(self):
        """Start the recursive training loop in a background thread."""
        if self.running:
            print("[RecursiveTrainer] Training loop already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._training_loop, daemon=True)
        self.thread.start()
        print("[RecursiveTrainer] Background training loop started")
        
    def stop_background_training(self):
        """Stop the recursive training loop."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[RecursiveTrainer] Training loop stopped")
        
    def _training_loop(self):
        """Main training loop that runs periodically."""
        while self.running:
            try:
                current_time = int(time.time())
                hours_since_last = (current_time - self.last_training_time) / 3600
                
                if hours_since_last >= self.training_interval_hours:
                    print(f"[RecursiveTrainer] Starting training cycle after {hours_since_last:.1f} hours")
                    self.run_training_cycle()
                    self.last_training_time = current_time
                
                # Sleep for 1 hour between checks
                time.sleep(3600)
            except Exception as e:
                print(f"[RecursiveTrainer] Error in training loop: {e}")
                time.sleep(3600)  # Sleep and retry
    
    def run_training_cycle(self) -> TrainingMetrics:
        """
        Run a single training cycle analyzing feedback and updating parameters.
        
        Returns:
            TrainingMetrics from this cycle
        """
        print("[RecursiveTrainer] ===== Starting Training Cycle =====")
        
        cycle_id = f"cycle_{int(time.time())}"
        timestamp = int(time.time())
        
        # Get unprocessed training data
        training_data = get_training_batch(batch_size=100)
        
        if len(training_data) < self.min_feedback_for_training:
            print(f"[RecursiveTrainer] Insufficient data: {len(training_data)} < {self.min_feedback_for_training}")
            return TrainingMetrics(
                cycle_id=cycle_id,
                timestamp=timestamp,
                total_feedback=len(training_data),
                avg_rating=0.0,
                source_performance={},
                concept_performance={},
                threshold_recommendation=0.4
            )
        
        # Analyze source performance
        source_stats = self._analyze_source_performance(training_data)
        
        # Analyze concept performance
        concept_stats = self._analyze_concept_performance(training_data)
        
        # Calculate average rating
        avg_rating = sum(item.get("rating", 3) for item in training_data) / len(training_data)
        
        # Generate threshold recommendation
        threshold_rec = self._recommend_threshold(training_data, avg_rating)
        
        # Update system parameters
        self._update_search_parameters(source_stats, threshold_rec)
        
        # Mark training data as processed
        for item in training_data:
            mark_training_processed(item.get("_id"))
        
        # Generate and store report
        metrics = TrainingMetrics(
            cycle_id=cycle_id,
            timestamp=timestamp,
            total_feedback=len(training_data),
            avg_rating=avg_rating,
            source_performance=source_stats,
            concept_performance=concept_stats,
            threshold_recommendation=threshold_rec
        )
        
        self._store_training_report(metrics)
        
        print(f"[RecursiveTrainer] ===== Cycle Complete =====")
        print(f"  - Processed: {metrics.total_feedback} feedback items")
        print(f"  - Avg Rating: {metrics.avg_rating:.2f}")
        print(f"  - Recommended Threshold: {metrics.threshold_recommendation:.2f}")
        print(f"  - Source Performance: {metrics.source_performance}")
        
        return metrics
    
    def _analyze_source_performance(self, training_data: List[Dict]) -> Dict[str, float]:
        """Analyze performance by source."""
        source_ratings = {}
        source_counts = {}
        
        for item in training_data:
            source = item.get("model_source", "unknown")
            rating = item.get("rating", 3)
            
            if source not in source_ratings:
                source_ratings[source] = 0
                source_counts[source] = 0
            
            source_ratings[source] += rating
            source_counts[source] += 1
        
        # Calculate averages
        source_performance = {}
        for source in source_ratings:
            avg = source_ratings[source] / source_counts[source]
            # Normalize to 0-1 scale
            source_performance[source] = (avg - 1) / 4.0
        
        return source_performance
    
    def _analyze_concept_performance(self, training_data: List[Dict]) -> Dict[str, float]:
        """Analyze performance by concept."""
        concept_ratings = {}
        concept_counts = {}
        
        for item in training_data:
            concept = item.get("concept", "unknown")
            rating = item.get("rating", 3)
            
            if concept not in concept_ratings:
                concept_ratings[concept] = 0
                concept_counts[concept] = 0
            
            concept_ratings[concept] += rating
            concept_counts[concept] += 1
        
        # Only include concepts with enough samples
        concept_performance = {}
        for concept, total in concept_ratings.items():
            if concept_counts[concept] >= 3:  # Min 3 samples
                avg = total / concept_counts[concept]
                concept_performance[concept] = (avg - 1) / 4.0
        
        return concept_performance
    
    def _recommend_threshold(self, training_data: List[Dict], avg_rating: float) -> float:
        """Recommend confidence threshold based on feedback."""
        # If average rating is low, lower the threshold to cast a wider net
        # If average rating is high, raise the threshold for quality
        
        base_threshold = float(os.getenv("MODEL_CONFIDENCE_THRESHOLD", "0.40"))
        
        if avg_rating >= 4.0:
            # High quality - can afford to be more selective
            return min(0.6, base_threshold + 0.1)
        elif avg_rating >= 3.0:
            # Medium quality - maintain current threshold
            return base_threshold
        else:
            # Low quality - cast wider net
            return max(0.3, base_threshold - 0.1)
    
    def _update_search_parameters(
        self,
        source_performance: Dict[str, float],
        threshold_recommendation: float
    ):
        """Update search parameters based on analysis."""
        try:
            # Store recommendations in database for retrieval
            if self.db is None:
                return
            
            collection = self.db["training_config"]
            
            # Update or insert config
            collection.update_one(
                {"config_type": "search_parameters"},
                {
                    "$set": {
                        "source_performance": source_performance,
                        "recommended_threshold": threshold_recommendation,
                        "last_updated": int(time.time())
                    }
                },
                upsert=True
            )
            
            # Update source bias adjustments in RAG store
            for source, score in source_performance.items():
                collection.update_one(
                    {"config_type": "source_bias", "source": source},
                    {
                        "$set": {
                            "bias_score": (score - 0.5) * 0.2,  # -0.1 to +0.1
                            "last_updated": int(time.time())
                        }
                    },
                    upsert=True
                )
            
            print(f"[RecursiveTrainer] Updated search parameters")
            
        except Exception as e:
            print(f"[RecursiveTrainer] Failed to update parameters: {e}")
    
    def _store_training_report(self, metrics: TrainingMetrics):
        """Store training report in database."""
        try:
            if self.db is None:
                return
            
            collection = self.db["training_reports"]
            
            report = {
                "cycle_id": metrics.cycle_id,
                "timestamp": metrics.timestamp,
                "total_feedback": metrics.total_feedback,
                "avg_rating": metrics.avg_rating,
                "source_performance": metrics.source_performance,
                "concept_performance": metrics.concept_performance,
                "threshold_recommendation": metrics.threshold_recommendation,
                "created_at": datetime.now().isoformat()
            }
            
            collection.insert_one(report)
            
        except Exception as e:
            print(f"[RecursiveTrainer] Failed to store report: {e}")
    
    def get_latest_config(self) -> Dict[str, Any]:
        """Get the latest training-based configuration."""
        try:
            if self.db is None:
                return {}
            
            collection = self.db["training_config"]
            config = collection.find_one({"config_type": "search_parameters"})
            
            if config:
                return {
                    "source_performance": config.get("source_performance", {}),
                    "recommended_threshold": config.get("recommended_threshold", 0.4),
                    "last_updated": config.get("last_updated", 0)
                }
            
            return {}
            
        except Exception as e:
            print(f"[RecursiveTrainer] Failed to get config: {e}")
            return {}
    
    def get_training_history(self, limit: int = 10) -> List[Dict]:
        """Get recent training reports."""
        try:
            if self.db is None:
                return []
            
            collection = self.db["training_reports"]
            reports = list(collection.find().sort("timestamp", -1).limit(limit))
            
            return [
                {
                    "cycle_id": r.get("cycle_id"),
                    "timestamp": r.get("timestamp"),
                    "total_feedback": r.get("total_feedback"),
                    "avg_rating": r.get("avg_rating"),
                    "threshold_recommendation": r.get("threshold_recommendation")
                }
                for r in reports
            ]
            
        except Exception as e:
            print(f"[RecursiveTrainer] Failed to get history: {e}")
            return []


# Global instance
_recursive_trainer = None

def get_recursive_trainer() -> RecursiveTrainer:
    """Get or create recursive trainer singleton."""
    global _recursive_trainer
    if _recursive_trainer is None:
        _recursive_trainer = RecursiveTrainer()
    return _recursive_trainer


def start_recursive_training():
    """Start the background recursive training loop."""
    trainer = get_recursive_trainer()
    trainer.start_background_training()


def stop_recursive_training():
    """Stop the background recursive training loop."""
    trainer = get_recursive_trainer()
    trainer.stop_background_training()


def run_manual_training_cycle() -> TrainingMetrics:
    """Manually trigger a training cycle."""
    trainer = get_recursive_trainer()
    return trainer.run_training_cycle()


def get_training_status() -> Dict[str, Any]:
    """Get current training system status."""
    trainer = get_recursive_trainer()
    
    return {
        "running": trainer.running,
        "last_training": trainer.last_training_time,
        "interval_hours": trainer.training_interval_hours,
        "min_feedback_required": trainer.min_feedback_for_training,
        "latest_config": trainer.get_latest_config(),
        "recent_reports": trainer.get_training_history(5)
    }
