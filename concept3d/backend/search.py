import requests
import os
import urllib.parse
import re
import uuid
from difflib import SequenceMatcher
from dotenv import load_dotenv

load_dotenv()

BLENDERKIT_API_KEY = os.getenv("BLENDERKIT_API_KEY")


STOPWORDS = {
    "a", "an", "the", "of", "for", "to", "in", "on", "with", "and", "or", "by", "is", "are"
}


def _normalize_text(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _tokenize(value):
    text = _normalize_text(value)
    return [token for token in re.findall(r"[a-z0-9]+", text) if token]


def _query_tokens(query):
    tokens = [token for token in _tokenize(query) if token not in STOPWORDS]
    return tokens if tokens else _tokenize(query)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_file(result):
    gltf_priority = {"gltf": 2, "gltf_godot": 1}
    best_file = None
    best_priority = 0

    for fileinfo in result.get("files", []):
        file_type = fileinfo.get("fileType")
        priority = gltf_priority.get(file_type, 0)
        if priority > best_priority:
            best_priority = priority
            best_file = fileinfo

    return best_file


def _extract_tags(result):
    tags = result.get("tags", [])
    normalized = []
    for tag in tags:
        if isinstance(tag, str):
            normalized.append(tag)
        elif isinstance(tag, dict):
            normalized.append(tag.get("name", ""))
    return " ".join(normalized)


def _score_candidate(query, tokens, result):
    name = _normalize_text(result.get("name", ""))
    description = _normalize_text(result.get("description", ""))
    tags = _normalize_text(_extract_tags(result))
    category = _normalize_text(result.get("category", ""))

    combined = " ".join(part for part in [name, description, tags, category] if part)
    if not combined:
        return None

    exact_matches = sum(1 for token in tokens if re.search(rf"\b{re.escape(token)}\b", combined))
    name_or_tag_matches = sum(1 for token in tokens if re.search(rf"\b{re.escape(token)}\b", f"{name} {tags}"))
    partial_matches = sum(1 for token in tokens if token in combined)

    phrase_bonus = 0.0
    phrase_match_in_name = False
    query_normalized = _normalize_text(query)
    if query_normalized and query_normalized in name:
        phrase_match_in_name = True
        phrase_bonus += 3.0
    elif query_normalized and query_normalized in combined:
        phrase_bonus += 0.5

    name_similarity = SequenceMatcher(None, query_normalized, name).ratio() if name else 0.0

    token_coverage = (exact_matches / len(tokens)) if tokens else 0.0
    relevance_score = (
        (exact_matches * 2.8)
        + (partial_matches * 0.6)
        + (token_coverage * 2.5)
        + (name_similarity * 2.0)
        + phrase_bonus
    )

    # Mild quality boost to break ties between similarly relevant assets.
    quality_boost = 0.0
    quality_boost += min(_safe_float(result.get("score", 0) or 0), 1.0) * 0.6
    quality_boost += min(_safe_float(result.get("downloads", 0) or 0), 1000.0) / 1000.0 * 0.4

    strict_min_exact = 1 if len(tokens) <= 1 else 2
    is_relevant = (
        phrase_match_in_name
        or (exact_matches >= strict_min_exact and name_or_tag_matches >= 1)
        or (len(tokens) <= 1 and token_coverage >= 0.6)
    )

    return {
        "exact_matches": exact_matches,
        "name_or_tag_matches": name_or_tag_matches,
        "token_coverage": token_coverage,
        "is_relevant": is_relevant,
        "relevance_score": relevance_score,
        "final_score": relevance_score + quality_boost,
    }


def search_models(query):
    # This now ACTS as the BlenderKit search engine instead of Tripo3D.
    print(f"Requesting BlenderKit to find: {query}")

    headers = {
        "Authorization": f"Bearer {BLENDERKIT_API_KEY}",
        "Content-Type": "application/json"
    }

    if not BLENDERKIT_API_KEY:
        print("Missing BLENDERKIT_API_KEY. Returning fallback.")
        return []

    try:
        # Step 1: Search the BlenderKit Library
        query_encoded = urllib.parse.quote(f"{query}+is_free:true")
        search_url = f"https://www.blenderkit.com/api/v1/search/?query={query_encoded}&asset_type=model"

        res = requests.get(search_url, headers=headers, timeout=30)
        res.raise_for_status()
        results = res.json().get("results", [])
        
        if not results:
            print("No results found on BlenderKit.")
            return []

        # Step 2: Rank all WebGL-ready candidates and choose the most relevant.
        query_tokens = _query_tokens(query)
        ranked_candidates = []

        for result in results:
            target_gltf_file = _extract_file(result)
            if not target_gltf_file:
                continue

            score_data = _score_candidate(query, query_tokens, result)
            if not score_data:
                continue

            ranked_candidates.append((score_data, result, target_gltf_file))

        if not ranked_candidates:
            print(f"BlenderKit has models for '{query}', but none are in GLTF/GLB web-browser format yet.")
            return []

        strict_candidates = [candidate for candidate in ranked_candidates if candidate[0]["is_relevant"]]
        if strict_candidates:
            ranked_candidates = strict_candidates
        elif len(query_tokens) > 1:
            print(f"No strictly relevant GLTF model found for multi-word query '{query}'.")
            return []

        ranked_candidates.sort(key=lambda item: item[0]["final_score"], reverse=True)
        score_data, top_match, target_gltf_file = ranked_candidates[0]
                
        if not top_match or not target_gltf_file:
            print(f"BlenderKit has models for '{query}', but none are in GLTF/GLB web-browser format yet.")
            return []
            
        # Step 3: Fetch the direct download URL for the GLTF
        download_id = target_gltf_file.get("id")
        if not download_id:
            return []
        
        # A scene_uuid is strictly required by BlenderKit API.
        dummy_scene_uuid = str(uuid.uuid4())
        download_endpoint = f"https://www.blenderkit.com/api/v1/downloads/{download_id}/?scene_uuid={dummy_scene_uuid}"
        
        print(
            f"Selected BlenderKit model '{top_match.get('name', 'unknown')}' "
            f"with relevance={score_data['relevance_score']:.2f} and exact_matches={score_data['exact_matches']}"
        )
        print(f"Found GLB on BlenderKit (ID {download_id}). Requesting download URL...")
        dl_res = requests.get(download_endpoint, headers=headers, timeout=30)
        dl_res.raise_for_status()
        dl_data = dl_res.json()
        
        final_file_url = dl_data.get("filePath")
        if not final_file_url:
            print("BlenderKit did not return a valid file path for the model.")
            return []
            
        MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
        os.makedirs(MODELS_DIR, exist_ok=True)
        
        uid = top_match.get("id")
        model_filename = f"{uid}.glb"
        model_path = os.path.join(MODELS_DIR, model_filename)
        
        if not os.path.exists(model_path):
            print(f"Downloading model locally to bypass CORS -> {model_filename}")
            model_bin = requests.get(final_file_url, timeout=60).content
            with open(model_path, "wb") as f:
                f.write(model_bin)
        
        print(f"Success! Proxied and downloaded BlenderKit model.")
        
        # Return the unified format that app expects
        return [{
            "uid": uid,
            "name": top_match.get("name", query.title()),
            "description": top_match.get("description", f"BlenderKit Asset: {query.title()}"),
            "viewer": f"http://localhost:8000/models/{model_filename}",
            "isDownloadable": top_match.get("isFree", True),
            "score": round(score_data["relevance_score"], 4)
        }]

    except Exception as e:
        print(f"BlenderKit API Error: {e}")
        return []
