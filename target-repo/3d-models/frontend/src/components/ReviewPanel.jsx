import { useState, useEffect } from 'react';
import { Star, Send, AlertCircle } from 'lucide-react';

export default function ReviewPanel({ modelId, modelTitle, onReviewSubmitted }) {
  const [reviews, setReviews] = useState([]);
  const [summary, setSummary] = useState(null);
  const [userReview, setUserReview] = useState(null);
  const [rating, setRating] = useState(0);
  const [hoverRating, setHoverRating] = useState(0);
  const [comment, setComment] = useState('');
  const [userId, setUserId] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const BACKEND_URL = 'http://127.0.0.1:8000';

  // Get or create anonymous user ID
  useEffect(() => {
    let storedUserId = localStorage.getItem('user_id');
    if (!storedUserId) {
      storedUserId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem('user_id', storedUserId);
    }
    setUserId(storedUserId);
  }, []);

  // Fetch reviews and summary when model changes
  useEffect(() => {
    if (!modelId || !userId) return;
    fetchReviews();
  }, [modelId, userId]);

  const fetchReviews = async () => {
    if (!modelId) return;
    
    setLoading(true);
    try {
      const [reviewsRes, userReviewRes] = await Promise.all([
        fetch(`${BACKEND_URL}/api/reviews/${encodeURIComponent(modelId)}`),
        fetch(`${BACKEND_URL}/api/reviews/${encodeURIComponent(modelId)}/user/${encodeURIComponent(userId)}`)
      ]);

      if (reviewsRes.ok) {
        const data = await reviewsRes.json();
        setSummary(data.summary);
        setReviews(data.reviews || []);
      }

      if (userReviewRes.ok) {
        const data = await userReviewRes.json();
        if (data.review) {
          setUserReview(data.review);
          setRating(data.review.rating);
          setComment(data.review.comment || '');
        }
      }
    } catch (err) {
      setError('Failed to load reviews');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitReview = async () => {
    if (!rating) {
      setError('Please select a rating');
      return;
    }

    if (!comment.trim() && !userReview) {
      setError('Please add a comment or update your existing review');
      return;
    }

    setSubmitting(true);
    setError('');
    setSuccess('');

    try {
      const res = await fetch(`${BACKEND_URL}/api/reviews/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_id: modelId,
          user_id: userId,
          rating,
          comment: comment.trim()
        })
      });

      if (!res.ok) {
        throw new Error('Failed to submit review');
      }

      const data = await res.json();
      setSuccess('Review submitted successfully!');
      setUserReview(data.review);

      // Trigger callback to re-fetch and re-sort results
      if (onReviewSubmitted) {
        onReviewSubmitted();
      }

      // Refresh reviews list
      setTimeout(() => fetchReviews(), 500);
    } catch (err) {
      setError(err.message || 'Failed to submit review');
    } finally {
      setSubmitting(false);
    }
  };

  const StarRating = ({ value, onHover, onLeave, onClick }) => {
    return (
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            onClick={() => onClick?.(star)}
            onMouseEnter={() => onHover?.(star)}
            onMouseLeave={onLeave}
            className="transition-transform hover:scale-110"
          >
            <Star
              size={24}
              className={
                (hoverRating || value) >= star
                  ? 'fill-yellow-400 text-yellow-400'
                  : 'text-slate-600'
              }
            />
          </button>
        ))}
      </div>
    );
  };

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  if (loading) {
    return (
      <div className="bg-slate-900/50 border border-slate-800/50 rounded-2xl p-4 shadow-xl backdrop-blur-sm">
        <div className="text-center text-slate-400">Loading reviews...</div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/50 border border-slate-800/50 rounded-2xl p-4 shadow-xl backdrop-blur-sm h-full flex flex-col overflow-hidden">
      {/* Header with Summary */}
      <div className="border-b border-slate-800/50 pb-3 mb-3">
        <h3 className="text-sm font-semibold text-slate-100 mb-2">Reviews & Ratings</h3>
        
        {summary && summary.total_reviews > 0 ? (
          <div className="flex items-start gap-4">
            <div>
              <div className="text-2xl font-bold text-yellow-400">
                {summary.avg_rating}
              </div>
              <div className="text-xs text-slate-400">
                {summary.total_reviews} {summary.total_reviews === 1 ? 'review' : 'reviews'}
              </div>
            </div>
            
            <div className="flex-1 space-y-1">
              {[5, 4, 3, 2, 1].map((stars) => (
                <div key={stars} className="flex items-center gap-2 text-[10px]">
                  <span className="text-slate-400 w-8">{stars}★</span>
                  <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-yellow-500 transition-all"
                      style={{
                        width: `${summary.total_reviews > 0 ? (summary.distribution[stars.toString()] / summary.total_reviews) * 100 : 0}%`
                      }}
                    />
                  </div>
                  <span className="text-slate-500 w-6 text-right">
                    {summary.distribution[stars.toString()]}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-xs text-slate-400">No reviews yet. Be the first!</p>
        )}
      </div>

      {/* Review Submission Form */}
      <div className="bg-slate-800/30 rounded-lg p-3 mb-3 border border-slate-700/50">
        <div className="mb-2">
          <label className="text-xs font-semibold text-slate-200 block mb-2">
            {userReview ? 'Update Your Review' : 'Leave a Review'}
          </label>
          <StarRating
            value={rating}
            onHover={setHoverRating}
            onLeave={() => setHoverRating(0)}
            onClick={setRating}
          />
        </div>

        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Share your thoughts about this model..."
          className="w-full bg-slate-900/60 border border-slate-700 rounded text-xs text-slate-100 p-2 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500 mb-2 resize-none"
          rows={3}
          disabled={submitting}
        />

        {error && (
          <div className="flex gap-2 items-start text-xs text-red-400 mb-2 p-2 bg-red-500/10 rounded border border-red-500/30">
            <AlertCircle size={14} className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="text-xs text-green-400 mb-2 p-2 bg-green-500/10 rounded border border-green-500/30">
            {success}
          </div>
        )}

        <button
          onClick={handleSubmitReview}
          disabled={submitting || !rating}
          className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium transition-colors"
        >
          <Send size={12} />
          {submitting ? 'Submitting...' : userReview ? 'Update Review' : 'Submit Review'}
        </button>
      </div>

      {/* Reviews List */}
      <div className="overflow-y-auto flex-1 pr-2 space-y-2 custom-scrollbar">
        {reviews.length === 0 ? (
          <p className="text-xs text-slate-400 text-center py-4">
            No reviews yet. Share your experience!
          </p>
        ) : (
          reviews.map((review) => (
            <div
              key={review.id}
              className={`p-2.5 rounded border text-xs ${
                review.user_id === userId
                  ? 'bg-blue-900/20 border-blue-500/40'
                  : 'bg-slate-800/30 border-slate-700/50'
              }`}
            >
              <div className="flex items-start justify-between mb-1">
                <div className="flex gap-1">
                  {[...Array(5)].map((_, i) => (
                    <Star
                      key={i}
                      size={12}
                      className={
                        i < review.rating
                          ? 'fill-yellow-400 text-yellow-400'
                          : 'text-slate-600'
                      }
                    />
                  ))}
                </div>
                <div className="text-[10px] text-slate-500">
                  {formatDate(review.created_at)}
                </div>
              </div>

              {review.comment && (
                <p className="text-slate-200 mb-1 line-clamp-2">{review.comment}</p>
              )}

              <div className="text-[10px] text-slate-400">
                {review.user_id === userId ? (
                  <span className="text-blue-400 font-medium">Your review</span>
                ) : (
                  <span>Anonymous User</span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
