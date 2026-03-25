
import hashlib
import json
import os
import re
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


import requests
from generative_stack import generate_ml_glb
from sketchfab_scraper import scrape_sketchfab_model, download_from_api
from rag_feedback import get_rag_search_enhancement, get_rag_source_recommendations
from gemini_search import (
    get_enhanced_query,
    calculate_semantic_similarity,
    rank_candidates,
    generate_search_queries,
    get_cached_similarity,
    set_cached_similarity,
)

try:
    import trimesh
except Exception:
    trimesh = None


STOPWORDS = {
    "a", "an", "the", "of", "for", "to", "in", "on", "with", "and", "or", "by", "is", "are",
    "was", "were", "be", "this", "that", "it", "about", "into", "from"
}

# Descriptor tokens are usually adjectives/modifiers; remaining tokens are treated as intent anchors.
DESCRIPTOR_TOKENS = {
    "red", "blue", "green", "yellow", "black", "white", "brown", "silver", "gold",
    "small", "large", "big", "tiny", "mini", "huge", "modern", "old", "ancient",
    "wood", "wooden", "metal", "metallic", "stone", "brick", "plastic", "glass",
    "futuristic", "vintage", "classic", "realistic", "cartoon", "stylized",
}

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.5

BLENDERKIT_API_KEY = os.getenv("BLENDERKIT_API_KEY", "").strip()
SKETCHFAB_API_TOKEN = os.getenv("SKETCHFAB_API_TOKEN", "").strip()
POLY_ARCHIVE_FEED_URL = os.getenv("POLY_ARCHIVE_FEED_URL", "").strip()

# Limit how many Sketchfab API calls we make per single hybrid pipeline run
SKETCHFAB_API_MAX_CALLS = int(os.getenv("SKETCHFAB_API_MAX_CALLS", "3"))

# Lowered from 0.40 to 0.25 to accept more candidates before falling back to ML generation
MIN_CONFIDENCE = float(os.getenv("MODEL_CONFIDENCE_THRESHOLD", "0.25"))

# Keep expensive local ML generation disabled by default for faster, reliable fallback responses.
ENABLE_ML_FALLBACK = os.getenv("ENABLE_ML_FALLBACK", "false").strip().lower() in {"1", "true", "yes", "on"}

@dataclass
class Candidate:
    source: str
    source_id: str
    name: str
    description: str
    tags: list[str]
    category: str
    format_type: str
    rating: float
    downloads: int
    detail: dict[str, Any]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _tokenize(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", _normalize_text(value)) if token]


def _keywords(value: str) -> list[str]:
    tokens = _tokenize(value)
    filtered = [token for token in tokens if token not in STOPWORDS]
    return filtered or tokens


def _required_concept_tokens(concept: str) -> list[str]:
    """Return intent-anchor tokens that must appear in candidate metadata for multi-word concepts."""
    tokens = _keywords(concept)
    if len(tokens) <= 1:
        return []

    anchors = [token for token in tokens if token not in DESCRIPTOR_TOKENS]
    if anchors:
        return anchors

    # Fallback: if all tokens are descriptors, use the last keyword as weak anchor.
    return [tokens[-1]] if tokens else []


def _candidate_matches_required_tokens(concept: str, candidate: Candidate) -> bool:
    required = _required_concept_tokens(concept)
    if not required:
        return True

    searchable = _normalize_text(
        " ".join([
            candidate.name or "",
            candidate.description or "",
            " ".join(candidate.tags or []),
            candidate.category or "",
        ])
    )
    return all(token in searchable for token in required)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _request_json_with_retry(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> dict[str, Any]:
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            last_error = error
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
    if last_error:
        raise last_error
    return {}


def _download_binary_with_retry(url: str, headers: dict[str, str] | None = None, timeout: int = 60) -> bytes:
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.content
        except requests.RequestException as error:
            last_error = error
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
    if last_error:
        raise last_error
    raise RuntimeError("Download failed")


def _extract_tags_from_blenderkit(raw_tags: list[Any]) -> list[str]:
    tags: list[str] = []
    for tag in raw_tags or []:
        if isinstance(tag, str):
            tags.append(tag)
        elif isinstance(tag, dict) and tag.get("name"):
            tags.append(str(tag.get("name")))
    return tags


def _blenderkit_candidates(concept: str) -> list[Candidate]:
    if not BLENDERKIT_API_KEY:
        return []

    headers = {
        "Authorization": f"Bearer {BLENDERKIT_API_KEY}",
        "Content-Type": "application/json",
    }

    query_encoded = urllib.parse.quote(f"{concept}+is_free:true")
    search_url = f"https://www.blenderkit.com/api/v1/search/?query={query_encoded}&asset_type=model"

    try:
        data = _request_json_with_retry(search_url, headers=headers, timeout=30)
    except Exception:
        return []

    candidates: list[Candidate] = []
    for result in data.get("results", []):
        files = result.get("files", [])
        best_file = None
        priority = {"gltf": 2, "gltf_godot": 1}
        best_priority = -1
        for fileinfo in files:
            file_type = fileinfo.get("fileType", "")
            p = priority.get(file_type, 0)
            if p > best_priority:
                best_priority = p
                best_file = fileinfo

        if not best_file:
            continue

        # Determine actual format type from selected file
        selected_type = best_file.get("fileType", "")
        actual_format = "glb" if selected_type in ("glb", "gltf") else selected_type if selected_type else "unknown"

        candidates.append(
            Candidate(
                source="blenderkit",
                source_id=str(result.get("id", "")),
                name=str(result.get("name", "")),
                description=str(result.get("description", "")),
                tags=_extract_tags_from_blenderkit(result.get("tags", [])),
                category=str(result.get("category", "")),
                format_type=actual_format,
                rating=_safe_float(result.get("score", 0.0)),
                downloads=_safe_int(result.get("downloads", 0)),
                detail={
                    "download_file_id": best_file.get("id"),
                    "raw": result,
                },
            )
        )

    return candidates


def _sketchfab_candidates(concept: str) -> list[Candidate]:
    # kept for backward compatibility when no api_state is provided
    return _sketchfab_candidates_with_state(concept, None)


def _sketchfab_candidates_with_state(concept: str, api_state: dict | None) -> list[Candidate]:
    headers: dict[str, str] = {}
    if SKETCHFAB_API_TOKEN:
        headers["Authorization"] = f"Token {SKETCHFAB_API_TOKEN}"

    query_encoded = urllib.parse.quote(concept)
    search_url = (
        "https://api.sketchfab.com/v3/search"
        f"?type=models&q={query_encoded}&downloadable=true&count=24"
    )

    # Respect API quota if provided (do not call Sketchfab more than allowed)
    if api_state is not None:
        if api_state.get("remaining", 0) <= 0:
            print("Sketchfab API quota exhausted for this run; skipping sketchfab search")
            return []
        # consume one API call for the search request
        api_state["remaining"] -= 1

    try:
        data = _request_json_with_retry(search_url, headers=headers or None, timeout=25)
    except Exception:
        return []

    candidates: list[Candidate] = []
    for result in data.get("results", []):
        uid = str(result.get("uid", ""))
        if not uid:
            continue

        tags = [str(tag.get("name", "")) for tag in result.get("tags", []) if tag.get("name")]
        categories = result.get("categories", [])
        category = ""
        if categories and isinstance(categories, list):
            category = str(categories[0].get("name", ""))

        candidates.append(
            Candidate(
                source="sketchfab",
                source_id=uid,
                name=str(result.get("name", "")),
                description=str(result.get("description", "")),
                tags=tags,
                category=category,
                format_type="glb",
                rating=_safe_float(result.get("likeCount", 0.0)) / 100.0,
                downloads=_safe_int(result.get("viewCount", 0)),
                detail={"raw": result},
            )
        )

    return candidates


def _poly_archive_candidates(concept: str) -> list[Candidate]:
    if not POLY_ARCHIVE_FEED_URL:
        return []

    try:
        data = _request_json_with_retry(POLY_ARCHIVE_FEED_URL, timeout=20)
    except Exception:
        return []

    records = data if isinstance(data, list) else data.get("items", [])
    candidates: list[Candidate] = []

    for item in records:
        if not isinstance(item, dict):
            continue
        if _normalize_text(item.get("format", "glb")) not in {"glb", "gltf", "glb2"}:
            continue

        source_id = str(item.get("id") or item.get("uid") or "")
        if not source_id:
            source_id = hashlib.sha1(json.dumps(item, sort_keys=True).encode("utf-8")).hexdigest()[:16]

        tags = item.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        candidates.append(
            Candidate(
                source="poly_archive",
                source_id=source_id,
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                tags=[str(tag) for tag in tags],
                category=str(item.get("category", "")),
                format_type="glb",
                rating=_safe_float(item.get("rating", 0.0)),
                downloads=_safe_int(item.get("downloads", 0)),
                detail={"url": item.get("url"), "raw": item},
            )
        )

    return candidates


def poly_pizza_candidates(concept: str) -> list[Candidate]:
    """Query Poly Pizza search API, using POLY_PIZZA_API_KEY if present."""
    POLY_PIZZA_API_KEY = os.getenv("POLY_PIZZA_API_KEY", "").strip()
    url = f"https://api.poly.pizza/v1/search/?query={urllib.parse.quote(concept)}"
    headers = {"x-api-key": POLY_PIZZA_API_KEY} if POLY_PIZZA_API_KEY else None
    try:
        data = _request_json_with_retry(url, headers=headers, timeout=20)
    except Exception:
        return []

    candidates: list[Candidate] = []
    for result in (data or {}).get("results", []):
        for fmt in result.get("formats", []):
            ftype = str(fmt.get("formatType", "")).lower()
            root_url = str(fmt.get("root", {}).get("url", ""))
            # accept several GLTF/GLB formatType variants and any .glb root URL
            if ("gltf" in ftype or "glb" in ftype) and root_url.endswith(".glb"):
                candidates.append(
                    Candidate(
                        source="poly_pizza",
                        source_id=str(result.get("title", "")),
                        name=str(result.get("title", "")),
                        description=f"By {result.get('author', '')}",
                        tags=[],
                        category="",
                        format_type="glb",
                        rating=0.0,
                        downloads=0,
                        detail={"url": fmt["root"]["url"], "author": result.get("author", "")},
                    )
                )
    return candidates


def _semantic_similarity(concept: str, text: str) -> float:
    c = _normalize_text(concept)
    t = _normalize_text(text)
    if not c or not t:
        return 0.0
    return SequenceMatcher(None, c, t).ratio()


def _token_overlap(concept_tokens: list[str], text_tokens: list[str]) -> float:
    """
    Calculate token overlap with stricter penalties for partial matches.
    For multi-word concepts, requires high coverage for a good score.
    """
    if not concept_tokens or not text_tokens:
        return 0.0
    
    cset = set(concept_tokens)
    tset = set(text_tokens)
    intersection = cset.intersection(tset)
    
    if not intersection:
        return 0.0
    
    # For multi-word concepts, require at least 75% of words to match
    if len(cset) > 1:
        coverage = len(intersection) / len(cset)
        if coverage >= 0.75:
            return coverage * 0.8  # Good coverage
        elif coverage >= 0.5:
            return coverage * 0.3  # Partial coverage, heavily penalized
        else:
            return 0.0  # Poor coverage, no score
    else:
        # Single word concept
        return len(intersection) / max(1, len(cset))


def _phrase_match(concept: str, text: str) -> float:
    """
    Strict phrase matching for multi-word concepts.
    For 'Solar System', both 'solar' AND 'system' must be present.
    """
    concept_normalized = _normalize_text(concept)
    text_normalized = _normalize_text(text)
    if not concept_normalized or not text_normalized:
        return 0.0
    
    # Full phrase match = highest score
    if concept_normalized in text_normalized:
        return 1.0
    
    # For multi-word concepts, require ALL keywords to be present
    concept_keywords = _keywords(concept)
    if len(concept_keywords) > 1:
        # Multi-word concept: all keywords must be in text
        all_present = all(keyword in text_normalized for keyword in concept_keywords)
        if all_present:
            return 0.6  # Good match but not exact phrase
        else:
            # Only partial match - heavily penalized
            present_count = sum(1 for k in concept_keywords if k in text_normalized)
            # Only give small credit if most words match
            if present_count >= len(concept_keywords) * 0.75:
                return 0.15
            else:
                return 0.0  # Missing key words
    else:
        # Single word concept: simple presence check
        return 0.35 if concept_keywords and concept_keywords[0] in text_normalized else 0.0


def _quality_signal(candidate: Candidate) -> float:
    rating = max(0.0, min(candidate.rating, 1.0))
    popularity = min(candidate.downloads, 50000) / 50000.0
    # Higher source bias for BlenderKit to prioritize it over Sketchfab
    source_bias = 0.25 if candidate.source == "blenderkit" else 0.08 if candidate.source == "sketchfab" else 0.04
    return min(1.0, (rating * 0.50) + (popularity * 0.25) + source_bias)


def _composite_score(concept: str, candidate: Candidate, use_gemini: bool = True) -> float:
    meta_blob = " ".join(
        part for part in [candidate.name, candidate.description, " ".join(candidate.tags), candidate.category] if part
    )
    concept_tokens = _keywords(concept)
    text_tokens = _keywords(meta_blob)

    # Try Gemini-powered semantic similarity first
    gemini_semantic = -1.0
    if use_gemini:
        cached = get_cached_similarity(concept, candidate.source_id)
        if cached is not None:
            gemini_semantic = cached
        else:
            gemini_semantic = calculate_semantic_similarity(concept, candidate.name, candidate.description)
            if gemini_semantic >= 0:
                set_cached_similarity(concept, candidate.source_id, gemini_semantic)
    
    # Use Gemini score if available (scale 0-1), otherwise fall back to SequenceMatcher
    if gemini_semantic >= 0:
        semantic = gemini_semantic
    else:
        semantic = _semantic_similarity(concept, meta_blob)
    
    overlap = _token_overlap(concept_tokens, text_tokens)
    phrase = _phrase_match(concept, meta_blob)
    quality = _quality_signal(candidate)

    score = (
        semantic * 0.45  # Increased weight for semantic accuracy
        + overlap * 0.30  # Token overlap with stricter penalties
        + phrase * 0.15  # Phrase matching (now stricter)
        + quality * 0.10  # Source quality signal
    )

    return max(0.0, min(1.0, score))


def _resolve_blenderkit_download(candidate: Candidate) -> str | None:
    if not BLENDERKIT_API_KEY:
        return None

    file_id = candidate.detail.get("download_file_id")
    if not file_id:
        return None

    headers = {
        "Authorization": f"Bearer {BLENDERKIT_API_KEY}",
        "Content-Type": "application/json",
    }
    scene_uuid = str(uuid.uuid4())
    download_endpoint = f"https://www.blenderkit.com/api/v1/downloads/{file_id}/?scene_uuid={scene_uuid}"

    try:
        payload = _request_json_with_retry(download_endpoint, headers=headers, timeout=30)
        return payload.get("filePath")
    except Exception:
        return None


def _resolve_sketchfab_download(candidate: Candidate, api_state: dict | None = None) -> tuple[str | None, dict[str, str] | None]:
    if not SKETCHFAB_API_TOKEN:
        return None, None

    uid = candidate.source_id
    if not uid:
        return None, None

    # Respect API quota if provided
    if api_state is not None:
        if api_state.get("remaining", 0) <= 0:
            print(f"Sketchfab API quota exhausted; skipping download request for {uid}")
            return None, None
        api_state["remaining"] -= 1

    headers = {"Authorization": f"Token {SKETCHFAB_API_TOKEN}", "Accept": "application/json"}
    try:
        data = _request_json_with_retry(f"https://api.sketchfab.com/v3/models/{uid}/download", headers=headers, timeout=25)
    except Exception as e:
        print(f"Sketchfab API download request failed for {uid}: {e}")
        return None, None

    # Debug: show response summary
    try:
        print(f"Sketchfab download API response keys for {uid}: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    except Exception:
        pass

    # Helper to normalize and find URL strings
    def _extract_urls_from_obj(obj):
        urls = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    urls.extend(_extract_urls_from_obj(v))
                elif isinstance(v, str) and (v.lower().endswith('.glb') or v.lower().endswith('.gltf')):
                    urls.append(v)
        elif isinstance(obj, list):
            for item in obj:
                urls.extend(_extract_urls_from_obj(item))
        return urls

    # Try common direct fields first
    if isinstance(data, dict):
        # 1) common 'gltf' or 'formats' fields
        candidates = []
        if 'gltf' in data and isinstance(data['gltf'], dict):
            g = data['gltf']
            candidates.extend([g.get('url'), g.get('root', {}).get('url')])
        if 'formats' in data and isinstance(data['formats'], list):
            for fmt in data['formats']:
                if isinstance(fmt, dict):
                    # fmt may contain 'gltf' or 'url' or 'name'
                    if fmt.get('format') and ('gltf' in str(fmt.get('format')).lower() or 'glb' in str(fmt.get('format')).lower()):
                        candidates.append(fmt.get('url') or (fmt.get('root') or {}).get('url'))
                    # check nested
                    candidates.extend(_extract_urls_from_obj(fmt))

        # 2) archives/list style
        if 'archives' in data and isinstance(data['archives'], list):
            for a in data['archives']:
                candidates.extend(_extract_urls_from_obj(a))

        # 3) fallback: scan entire dict for any .glb/.gltf strings
        if not candidates:
            candidates = _extract_urls_from_obj(data)

        # filter and return first valid-looking candidate
        for c in candidates:
            if not c:
                continue
            cstr = str(c)
            if 'http' in cstr and (cstr.lower().endswith('.glb') or cstr.lower().endswith('.gltf') or 'media.sketchfab.com' in cstr):
                # Media URLs hosted on media.sketchfab.com should be fetched without
                # the Sketchfab API Authorization header which can cause 403s.
                download_headers = None if 'media.sketchfab.com' in cstr else headers
                print(f"Sketchfab API: selected download URL for {uid}: {cstr}")
                return cstr, download_headers

    # If API didn't return a usable url, fall back to None so caller can try scraping
    return None, None


def _resolve_poly_download(candidate: Candidate) -> str | None:
    url = candidate.detail.get("url")
    if not url:
        return None
    return str(url)


def _download_and_cache_glb(candidate: Candidate, models_dir: str) -> str | None:
    os.makedirs(models_dir, exist_ok=True)

    model_filename = f"{candidate.source}_{candidate.source_id}.glb"
    model_path = os.path.join(models_dir, model_filename)
    if os.path.exists(model_path):
        return model_filename

    try:
        if candidate.source == "blenderkit":
            # Check if model is actually downloadable before attempting API call
            raw_meta = candidate.detail.get('raw', {})
            files = raw_meta.get('files', [])
            has_downloadable_file = any(
                f.get('fileType') in ('glb', 'gltf', 'gltf_godot') 
                for f in files
            )
            if not has_downloadable_file:
                print(f"BlenderKit: model {candidate.source_id} has no downloadable GLB/GLTF files; skipping")
                return None
            url = _resolve_blenderkit_download(candidate)
            headers = None
        elif candidate.source == "sketchfab":
            # Prefer API download via helper; falls back to page scrape if needed
            # Prefer API download via helper if token is configured; falls back to page scrape if needed
            raw_meta = candidate.detail.get('raw', {})
            # Prefer using search metadata to avoid unnecessary /download calls (rate limits).
            if not raw_meta.get('isDownloadable', False):
                print(f"Sketchfab: model {candidate.source_id} not marked downloadable in search metadata; skipping API download")
            elif SKETCHFAB_API_TOKEN:
                try:
                    # Pass the running API quota state if present on the candidate (set by caller)
                    api_state = getattr(candidate, 'api_state', None)
                    scraped_path = download_from_api(candidate.source_id, models_dir, SKETCHFAB_API_TOKEN, api_state)
                    if scraped_path:
                        import shutil

                        shutil.copyfile(scraped_path, model_path)
                        # validate copied file is a GLB (avoid serving unrelated files)
                        try:
                            with open(model_path, 'rb') as fh:
                                header = fh.read(16)
                                if not (header[0:4] == b'glTF'):
                                    print(f"Downloaded file for {candidate.source_id} is not a valid GLB; rejecting")
                                    fh.close()
                                    os.remove(model_path)
                                else:
                                    return model_filename
                        except Exception as e:
                            print(f"Error validating downloaded file for {candidate.source_id}: {e}")
                            if os.path.exists(model_path):
                                os.remove(model_path)
                except Exception as e:
                    print(f"Sketchfab API download helper failed for {candidate.source_id}: {e}")
            else:
                print(f"SKETCHFAB_API_TOKEN not set; skipping Sketchfab API download for {candidate.source_id}")

            # If API helper didn't produce a file, try scraping viewer page as last resort (not reliable)
            if 'raw' in candidate.detail and 'viewerUrl' in candidate.detail.get('raw', {}):
                model_url = candidate.detail['raw']['viewerUrl']
                print(f"Sketchfab: falling back to page scrape for {candidate.source_id} (unreliable)")
                scraped_path = scrape_sketchfab_model(model_url, models_dir)
                if scraped_path:
                    import shutil

                    shutil.copyfile(scraped_path, model_path)
                    # validate copied file is a GLB
                    try:
                        with open(model_path, 'rb') as fh:
                            header = fh.read(16)
                            if not (header[0:4] == b'glTF'):
                                print(f"Scraped file for {candidate.source_id} is not a valid GLB; rejecting")
                                fh.close()
                                os.remove(model_path)
                            else:
                                return model_filename
                    except Exception as e:
                        print(f"Error validating scraped file for {candidate.source_id}: {e}")
                        if os.path.exists(model_path):
                            os.remove(model_path)
        elif candidate.source == "poly_archive":
            # Validate that we have a valid URL before attempting download
            url = _resolve_poly_download(candidate)
            if not url:
                print(f"Poly Archive: model {candidate.source_id} has no download URL; skipping")
                return None
            headers = None
        elif candidate.source == "poly_pizza":
            # Validate Poly Pizza URL exists
            url = candidate.detail.get("url")
            if not url:
                print(f"Poly Pizza: model {candidate.source_id} has no download URL; skipping")
                return None
            headers = None
        else:
            return None

        if not url:
            return None

        try:
            binary = _download_binary_with_retry(url, headers=headers, timeout=90)
        except Exception as e:
            print(f"Download failed for {candidate.source}/{candidate.source_id} url={url}: {e}")
            # try scraping as a last resort for sketchfab
            if candidate.source == "sketchfab" and 'raw' in candidate.detail and 'viewerUrl' in candidate.detail.get('raw', {}):
                try:
                    model_url = candidate.detail['raw']['viewerUrl']
                    scraped_path = scrape_sketchfab_model(model_url, models_dir)
                    if scraped_path:
                        import shutil

                        shutil.copyfile(scraped_path, model_path)
                        # validate copied file is a GLB
                        try:
                            with open(model_path, 'rb') as fh:
                                header = fh.read(16)
                                if not (header[0:4] == b'glTF'):
                                    print(f"Scraped file for {candidate.source_id} is not a valid GLB; rejecting")
                                    fh.close()
                                    os.remove(model_path)
                                else:
                                    return model_filename
                        except Exception as e:
                            print(f"Error validating scraped file for {candidate.source_id}: {e}")
                            if os.path.exists(model_path):
                                os.remove(model_path)
                except Exception as se:
                    print(f"Scrape fallback also failed for {candidate.source_id}: {se}")
            return None

        # Handle different download payloads: direct GLB, ZIP containing GLB/GLTF, or GLTF content
        try:
            import io
            import zipfile
            import tempfile
            import shutil

            bio = io.BytesIO(binary)
            # If it's a ZIP archive, extract and look for .glb/.gltf
            if zipfile.is_zipfile(bio):
                with tempfile.TemporaryDirectory() as td:
                    bio.seek(0)
                    with zipfile.ZipFile(bio) as zf:
                        zf.extractall(td)
                    # prefer .glb files
                    glb_files = []
                    gltf_files = []
                    for root, _, files in os.walk(td):
                        for f in files:
                            if f.lower().endswith('.glb'):
                                glb_files.append(os.path.join(root, f))
                            elif f.lower().endswith('.gltf'):
                                gltf_files.append(os.path.join(root, f))

                    if glb_files:
                        shutil.copyfile(glb_files[0], model_path)
                        return model_filename

                    # If only gltf available, try converting using trimesh if present
                    if gltf_files and trimesh is not None:
                        try:
                            scene = trimesh.load(gltf_files[0], force='scene')
                            exported = scene.export(file_type='glb')
                            with open(model_path, 'wb') as fh:
                                fh.write(exported)
                            return model_filename
                        except Exception as e:
                            print(f"Failed to convert GLTF->GLB for {candidate.source_id}: {e}")

                    # No usable asset found inside ZIP
                    print(f"No .glb/.gltf found inside ZIP for {candidate.source}/{candidate.source_id}")
                    return None

            # Not a ZIP: check if raw bytes look like GLB (magic 'glTF' appears at offset 4)
            bio.seek(0)
            header = bio.read(16)
            if header[0:4] == b'glTF':
                # Looks like GLB
                with open(model_path, 'wb') as file_obj:
                    file_obj.write(binary)
                return model_filename

            # Otherwise save to disk and attempt to treat as gltf JSON
            # write to a temp file and try to load via trimesh if available
            if trimesh is not None:
                with tempfile.TemporaryDirectory() as td:
                    maybe = os.path.join(td, 'candidate.data')
                    with open(maybe, 'wb') as fh:
                        fh.write(binary)
                    try:
                        scene = trimesh.load(maybe, force='scene')
                        exported = scene.export(file_type='glb')
                        with open(model_path, 'wb') as fh:
                            fh.write(exported)
                        return model_filename
                    except Exception:
                        pass

            # Do not write raw bytes as a last resort — avoid serving invalid files
            print(f"Downloaded payload for {candidate.source_id} did not produce a valid GLB")
            return None
        except Exception as e:
            print(f"Error handling downloaded payload for {candidate.source_id}: {e}")
            return None
    except Exception:
        return None


def _build_primitive_mesh(concept: str):
    if trimesh is None:
        return None
    
    token_set = set(_keywords(concept))

    if "car" in token_set or "vehicle" in token_set:
        base = trimesh.creation.box(extents=(1.6, 0.45, 0.8))
        wheel_offsets = [(-0.55, -0.25, 0.45), (0.55, -0.25, 0.45), (-0.55, -0.25, -0.45), (0.55, -0.25, -0.45)]
        wheels = [trimesh.creation.cylinder(radius=0.18, height=0.14, sections=24) for _ in wheel_offsets]
        for wheel, (x, y, z) in zip(wheels, wheel_offsets):
            wheel.apply_transform(trimesh.transformations.rotation_matrix(1.5708, [0, 1, 0]))
            wheel.apply_translation([x, y, z])
        return trimesh.util.concatenate([base] + wheels)

    if "house" in token_set or "building" in token_set:
        body = trimesh.creation.box(extents=(1.2, 0.8, 1.0))
        roof = trimesh.creation.cone(radius=0.85, height=0.55, sections=4)
        roof.apply_translation([0, 0.7, 0])
        return trimesh.util.concatenate([body, roof])

    if "tree" in token_set:
        trunk = trimesh.creation.cylinder(radius=0.15, height=1.0, sections=20)
        trunk.apply_translation([0, -0.1, 0])
        crown = trimesh.creation.icosphere(subdivisions=2, radius=0.55)
        crown.apply_translation([0, 0.65, 0])
        return trimesh.util.concatenate([trunk, crown])

    if "chair" in token_set:
        seat = trimesh.creation.box(extents=(0.8, 0.12, 0.8))
        seat.apply_translation([0, 0.1, 0])
        back = trimesh.creation.box(extents=(0.8, 0.8, 0.12))
        back.apply_translation([0, 0.5, -0.34])
        return trimesh.util.concatenate([seat, back])

    return trimesh.creation.icosphere(subdivisions=2, radius=0.7)


def _normalize_mesh(mesh):
    bounds = mesh.bounds
    size = bounds[1] - bounds[0]
    max_size = max(size)
    if max_size > 0:
        mesh.apply_scale(1.8 / max_size)

    center = mesh.bounds.mean(axis=0)
    mesh.apply_translation(-center)
    return mesh


def _generate_glb_fallback(concept: str, models_dir: str) -> str | None:
    if trimesh is None:
        return None

    os.makedirs(models_dir, exist_ok=True)

    concept_key = hashlib.sha1(_normalize_text(concept).encode("utf-8")).hexdigest()[:14]
    model_filename = f"generated_{concept_key}.glb"
    model_path = os.path.join(models_dir, model_filename)

    if os.path.exists(model_path):
        return model_filename

    mesh = _build_primitive_mesh(concept)
    mesh = _normalize_mesh(mesh)

    mesh.visual.face_colors = [82, 183, 255, 255]
    mesh.export(model_path)
    return model_filename


def run_hybrid_pipeline(concept: str, models_dir: str, backend_base_url: str) -> dict[str, Any]:
    concept = (concept or "").strip()
    if not concept:
        return {
            "type": "generated",
            "model_url": None,
            "metadata": {
                "source": "none",
                "confidence_score": 0.0,
                "reason": "empty_concept",
            },
        }

    # Get RAG-based search enhancement from historical feedback
    print(f"[RAG] Retrieving feedback-based recommendations for: {concept}")
    rag_enhancement = get_rag_search_enhancement(concept)
    rag_source_recs = get_rag_source_recommendations(concept)
    
    if rag_enhancement.get("recommended_sources"):
        print(f"[RAG] Recommended sources: {rag_enhancement['recommended_sources']}")
    if rag_enhancement.get("avoid_models"):
        print(f"[RAG] Avoiding {len(rag_enhancement['avoid_models'])} poorly-rated models")
    if rag_enhancement.get("related_concepts"):
        print(f"[RAG] Related successful concepts: {rag_enhancement['related_concepts'][:3]}")

    candidates: list[Candidate] = []
    
    # Get Gemini-enhanced search queries
    print(f"[Gemini] Enhancing search for: {concept}")
    enhancement = get_enhanced_query(concept)
    enhanced_queries = generate_search_queries(concept, enhancement)
    
    print(f"[Gemini] Expanded terms: {enhancement.get('expanded_terms', [])}")
    print(f"[Gemini] Categories: {enhancement.get('categories', [])}")
    
    # Search with enhanced queries
    candidates.extend(_blenderkit_candidates(enhanced_queries.get("blenderkit", concept)))
    
    # Create a per-run Sketchfab API quota state and pass it to sketchfab candidate search
    sketchfab_state = {"remaining": SKETCHFAB_API_MAX_CALLS}
    candidates.extend(_sketchfab_candidates_with_state(enhanced_queries.get("sketchfab", concept), sketchfab_state))
    candidates.extend(_poly_archive_candidates(concept))
    candidates.extend(poly_pizza_candidates(enhanced_queries.get("poly_pizza", concept)))

    # Debug: report how many candidates we found from each source
    try:
        print(f"Hybrid pipeline: total candidates={len(candidates)}")
        source_counts = {}
        for c in candidates:
            source_counts[c.source] = source_counts.get(c.source, 0) + 1
        print(f"Candidate sources: {source_counts}")
    except Exception:
        pass

    # Filter out models that have been poorly rated in the past
    avoid_models = set(rag_enhancement.get("avoid_models", []))
    if avoid_models:
        original_count = len(candidates)
        candidates = [c for c in candidates if c.source_id not in avoid_models]
        filtered_count = original_count - len(candidates)
        if filtered_count > 0:
            print(f"[RAG] Filtered {filtered_count} poorly-rated models")

    ranked: list[tuple[float, Candidate]] = []
    
    # First pass: score all candidates without Gemini (fast)
    for candidate in candidates:
        # attach API state for sketchfab candidates so downstream download helpers can consume quota
        if candidate.source == 'sketchfab':
            setattr(candidate, 'api_state', sketchfab_state)
        score = _composite_score(concept, candidate, use_gemini=False)
        ranked.append((score, candidate))
    
    # Sort and take top 5 for Gemini enhancement
    ranked.sort(key=lambda item: item[0], reverse=True)
    top_5 = ranked[:5]
    
    # Second pass: re-score top 5 with Gemini (slow but accurate)
    print(f"[Gemini] Enhancing top 5 candidates with AI scoring...")
    enhanced_ranked = []
    for score, candidate in top_5:
        enhanced_score = _composite_score(concept, candidate, use_gemini=True)
        enhanced_ranked.append((enhanced_score, candidate))
    
    # Combine: enhanced top 5 + rest without Gemini
    ranked = enhanced_ranked + ranked[5:]

    ranked.sort(key=lambda item: item[0], reverse=True)
    
    # Prioritize BlenderKit over Sketchfab by source tier with RAG-based adjustments
    def _source_priority(candidate):
        # Lower number = higher priority
        base_priority = 0 if candidate.source == "blenderkit" else 1 if candidate.source == "sketchfab" else 2
        
        # Adjust priority based on RAG feedback
        source_rec_score = rag_source_recs.get(candidate.source, 0.5)
        if source_rec_score > 0.7:
            # Boost priority for highly-rated sources
            return max(0, base_priority - 1)
        elif source_rec_score < 0.3:
            # Lower priority for poorly-rated sources
            return base_priority + 1
        return base_priority
    
    # Apply source bias with RAG-based adjustments
    def _get_source_bias(candidate):
        # Base bias
        if candidate.source == "blenderkit":
            base_bias = 0.25
        elif candidate.source == "sketchfab":
            base_bias = 0.08
        else:
            base_bias = 0.04
        
        # Adjust based on RAG recommendations
        source_rec_score = rag_source_recs.get(candidate.source, 0.5)
        # Scale: 0.0-1.0 -> -0.1 to +0.1 adjustment
        rag_adjustment = (source_rec_score - 0.5) * 0.2
        
        return base_bias + rag_adjustment
    
    # Re-sort by score first, then by source priority (group by tier)
    ranked = [(s + _get_source_bias(c), c) for s, c in ranked]
    ranked.sort(key=lambda item: (-item[0], _source_priority(item[1])))
    
    # DISABLED: Gemini re-ranking to save API quota
    # if len(ranked) > 3:
    #     print("[Gemini] Intelligently re-ranking top candidates...")
    #     top_candidates = [c for _, c in ranked[:15]]
    #     reranked = rank_candidates(concept, top_candidates)
    #     # Update ranked list with Gemini re-ranking
    #     ranked = [(ranked[[c for _, c in ranked].index(c)][0], c) for c in reranked if c in [x[1] for x in ranked]]
    #     ranked.extend([(s, c) for s, c in ranked if c not in reranked])

    for confidence, candidate in ranked:
        print(f"Candidate {candidate.source}/{candidate.source_id} score={confidence:.3f} format={candidate.format_type}")
        if not _candidate_matches_required_tokens(concept, candidate):
            print(
                f"Skipping candidate due to missing required concept tokens: "
                f"{_required_concept_tokens(concept)}"
            )
            continue
        # Skip non-GLB formats from BlenderKit (we can't display .blend files)
        if candidate.source == "blenderkit" and candidate.format_type not in ("glb", "gltf"):
            print(f"Skipping BlenderKit candidate {candidate.source_id} - unsupported format: {candidate.format_type}")
            continue
        if confidence < MIN_CONFIDENCE:
            print(f"Skipping candidate due to low confidence: {confidence:.3f} < {MIN_CONFIDENCE}")
            continue

        filename = _download_and_cache_glb(candidate, models_dir)
        if not filename:
            print(f"Failed to download candidate {candidate.source}/{candidate.source_id}")
            continue

        viewer = f"{backend_base_url}/models/{filename}"
        
        # Include RAG metadata in response for tracking
        result = {
            "type": "retrieved",
            "model_url": viewer,
            "metadata": {
                "source": candidate.source,
                "confidence_score": round(confidence, 4),
                "name": candidate.name,
                "description": candidate.description,
                "tags": candidate.tags,
                "format": candidate.format_type,
                "rag_enhanced": bool(rag_enhancement.get("recommended_sources")),
                "source_recommendation_score": round(rag_source_recs.get(candidate.source, 0.5), 2),
            },
        }
        
        return result

    if ENABLE_ML_FALLBACK:
        ml_generation = generate_ml_glb(concept=concept, models_dir=models_dir)
        if ml_generation:
            viewer = f"{backend_base_url}/models/{ml_generation['filename']}"
            return {
                "type": "generated",
                "model_url": viewer,
                "metadata": {
                    "source": ml_generation.get("source", "ml_openlrm"),
                    "confidence_score": 0.0,
                    "name": f"Generated {concept.title()}",
                    "description": "SD + OpenLRM generated fallback mesh",
                    "tags": _keywords(concept),
                    "format": "glb",
                    "generator_details": ml_generation.get("details", {}),
                },
            }
    else:
        print("ML fallback disabled (ENABLE_ML_FALLBACK=false); using procedural fallback")

    generated_filename = _generate_glb_fallback(concept, models_dir)
    if generated_filename:
        viewer = f"{backend_base_url}/models/{generated_filename}"
        return {
            "type": "generated",
            "model_url": viewer,
            "metadata": {
                "source": "procedural_generator",
                "confidence_score": 0.0,
                "name": f"Generated {concept.title()}",
                "description": "Procedural generated fallback mesh",
                "tags": _keywords(concept),
                "format": "glb",
            },
        }

    return {
        "type": "generated",
        "model_url": None,
        "metadata": {
            "source": "primitive_fallback",
            "confidence_score": 0.0,
            "name": concept.title(),
            "description": "Fallback primitive representation",
            "tags": _keywords(concept),
            "format": "none",
        },
        "shapes": ["cube"],
    }
