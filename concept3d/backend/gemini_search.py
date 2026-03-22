"""
Gemini-powered search enhancement module for Concept3D.
Uses Google's Gemini API to improve search query understanding,
candidate ranking, and semantic similarity scoring.
"""

import os
import json
import time
import requests
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Rate limiting: track last request time
_last_request_time = 0
MIN_REQUEST_INTERVAL = 1.0  # seconds between requests (60 req/min max)


def _gemini_request(prompt: str, temperature: float = 0.2, max_tokens: int = 1024, max_retries: int = 3) -> Optional[str]:
    """Make a request to Gemini API with rate limiting and retry logic."""
    global _last_request_time
    
    if not GEMINI_API_KEY:
        print("[Gemini] No API key configured")
        return None
    
    # Rate limiting: ensure minimum interval between requests
    elapsed = time.time() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    
    url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent"
    headers = {
        "Content-Type": "application/json",
    }
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "topP": 0.8,
            "topK": 40,
        }
    }
    
    for attempt in range(max_retries):
        try:
            _last_request_time = time.time()
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                params={"key": GEMINI_API_KEY},
                timeout=30
            )
            
            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                retry_delay = (2 ** attempt) + 1  # 1, 3, 7 seconds
                print(f"[Gemini] Rate limited (429), retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                continue
            
            response.raise_for_status()
            data = response.json()
            
            # Extract text from response
            candidates = data.get("candidates", [])
            if not candidates:
                return None
            
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                return None
            
            return parts[0].get("text", "").strip()
        except Exception as e:
            if attempt < max_retries - 1:
                retry_delay = (2 ** attempt) + 1
                print(f"[Gemini] Request failed, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
            else:
                print(f"[Gemini] Request failed after {max_retries} attempts: {e}")
                return None
    
    return None


def enhance_search_query(concept: str) -> dict:
    """
    Use Gemini to enhance the user's search query.
    Returns expanded keywords, categories, and alternative terms.
    """
    prompt = f"""Given the search concept "{concept}", provide a JSON object with:
1. "expanded_terms": List of 5-10 related keywords/synonyms for better 3D model search
2. "categories": List of likely 3D model categories (e.g., "character", "vehicle", "architecture", "nature", "furniture")
3. "style_hints": List of style descriptors (e.g., "low-poly", "realistic", "stylized", "cartoon")
4. "specificity": "high" if the concept is very specific, "medium" if general, "low" if vague

Respond ONLY with valid JSON, no markdown formatting."""
    
    result = _gemini_request(prompt, temperature=0.3, max_tokens=512)
    if not result:
        return _fallback_enhancement(concept)
    
    try:
        # Clean up response (remove markdown if present)
        cleaned = result.replace("```json", "").replace("```", "").strip()
        enhanced = json.loads(cleaned)
        return enhanced
    except json.JSONDecodeError:
        print(f"[Gemini] Failed to parse enhancement response: {result}")
        return _fallback_enhancement(concept)


def _fallback_enhancement(concept: str) -> dict:
    """Fallback enhancement when Gemini is unavailable."""
    return {
        "expanded_terms": [concept],
        "categories": [],
        "style_hints": [],
        "specificity": "medium"
    }


def calculate_semantic_similarity(concept: str, candidate_name: str, candidate_desc: str) -> float:
    """
    Use Gemini to calculate semantic similarity between concept and candidate.
    Returns a score from 0.0 to 1.0.
    NOTE: This makes an API call - use sparingly for top candidates only.
    """
    prompt = f"""Rate how well this 3D model matches the search concept.

Search Concept: "{concept}"
Model Name: "{candidate_name}"
Model Description: "{candidate_desc[:200]}"

On a scale of 0 to 100, where:
- 0-20: Completely unrelated
- 21-40: Weakly related
- 41-60: Moderately related  
- 61-80: Strongly related
- 81-100: Perfect match

Respond with ONLY a number (0-100), no explanation."""
    
    result = _gemini_request(prompt, temperature=0.1, max_tokens=10)
    if not result:
        return -1.0  # Signal to use fallback scoring
    
    try:
        # Extract number from response
        score_text = ''.join(c for c in result if c.isdigit())
        if score_text:
            score = int(score_text)
            return min(100, max(0, score)) / 100.0
    except (ValueError, IndexError):
        pass
    
    return -1.0


def rank_candidates(concept: str, candidates: list) -> list:
    """
    Use Gemini to intelligently rank 3D model candidates.
    Returns candidates sorted by relevance (most relevant first).
    """
    if not candidates or not GEMINI_API_KEY:
        return candidates
    
    # Limit to top 15 candidates to avoid token limits
    top_candidates = candidates[:15]
    
    # Build candidate list for prompt
    candidate_list = []
    for i, c in enumerate(top_candidates):
        candidate_list.append(
            f"{i+1}. {c.name} - {c.description[:100]}... (source: {c.source}, tags: {', '.join(c.tags[:5])})"
        )
    
    prompt = f"""Given the search concept "{concept}", rank these 3D models by relevance.
Most relevant should be ranked #1.

Models:
{chr(10).join(candidate_list)}

Respond with ONLY a JSON array of the model numbers in ranked order (most relevant first).
Example: [3, 1, 5, 2, 4]

JSON response:"""
    
    result = _gemini_request(prompt, temperature=0.2, max_tokens=256)
    if not result:
        return candidates
    
    try:
        # Clean up response
        cleaned = result.replace("```json", "").replace("```", "").strip()
        ranking = json.loads(cleaned)
        
        if isinstance(ranking, list) and len(ranking) > 0:
            # Reorder candidates based on ranking
            reordered = []
            used_indices = set()
            
            for rank in ranking:
                try:
                    idx = int(rank) - 1  # Convert from 1-based to 0-based
                    if 0 <= idx < len(top_candidates) and idx not in used_indices:
                        reordered.append(top_candidates[idx])
                        used_indices.add(idx)
                except (ValueError, IndexError):
                    continue
            
            # Add any remaining candidates that weren't ranked
            for i, c in enumerate(top_candidates):
                if i not in used_indices:
                    reordered.append(c)
            
            # Add remaining candidates that weren't in top 15
            return reordered + candidates[15:]
    except json.JSONDecodeError:
        print(f"[Gemini] Failed to parse ranking response: {result}")
    
    return candidates


def generate_search_queries(concept: str, enhancement: dict) -> dict:
    """
    Generate optimized search queries for each 3D model source.
    """
    queries = {
        "blenderkit": concept,
        "sketchfab": concept,
        "poly_pizza": concept,
    }
    
    # Add expanded terms for broader search if specificity is low
    expanded_terms = enhancement.get("expanded_terms", [])
    if expanded_terms and len(expanded_terms) > 1:
        # Use expanded terms for sources that support complex queries
        queries["blenderkit"] = f"{concept} {' '.join(expanded_terms[:3])}"
        queries["sketchfab"] = concept  # Keep simple for Sketchfab
    
    return queries


# Cache for enhancement results to avoid repeated API calls
_enhancement_cache = {}
_similarity_cache = {}


def get_enhanced_query(concept: str) -> dict:
    """Get cached or new enhanced query."""
    cache_key = concept.lower().strip()
    if cache_key not in _enhancement_cache:
        _enhancement_cache[cache_key] = enhance_search_query(concept)
    return _enhancement_cache[cache_key]


def get_cached_similarity(concept: str, candidate_id: str) -> Optional[float]:
    """Get cached similarity score."""
    cache_key = f"{concept.lower().strip()}::{candidate_id}"
    return _similarity_cache.get(cache_key)


def set_cached_similarity(concept: str, candidate_id: str, score: float):
    """Cache similarity score."""
    cache_key = f"{concept.lower().strip()}::{candidate_id}"
    _similarity_cache[cache_key] = score
