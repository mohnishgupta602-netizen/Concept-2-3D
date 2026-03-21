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

try:
    import trimesh
except Exception:
    trimesh = None


STOPWORDS = {
    "a", "an", "the", "of", "for", "to", "in", "on", "with", "and", "or", "by", "is", "are",
    "was", "were", "be", "this", "that", "it", "about", "into", "from"
}

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.5

BLENDERKIT_API_KEY = os.getenv("BLENDERKIT_API_KEY", "").strip()
SKETCHFAB_API_TOKEN = os.getenv("SKETCHFAB_API_TOKEN", "").strip()
POLY_ARCHIVE_FEED_URL = os.getenv("POLY_ARCHIVE_FEED_URL", "").strip()

MIN_CONFIDENCE = float(os.getenv("MODEL_CONFIDENCE_THRESHOLD", "0.56"))


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

        candidates.append(
            Candidate(
                source="blenderkit",
                source_id=str(result.get("id", "")),
                name=str(result.get("name", "")),
                description=str(result.get("description", "")),
                tags=_extract_tags_from_blenderkit(result.get("tags", [])),
                category=str(result.get("category", "")),
                format_type="glb",
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
    headers: dict[str, str] = {}
    if SKETCHFAB_API_TOKEN:
        headers["Authorization"] = f"Token {SKETCHFAB_API_TOKEN}"

    query_encoded = urllib.parse.quote(concept)
    search_url = (
        "https://api.sketchfab.com/v3/search"
        f"?type=models&q={query_encoded}&downloadable=true&count=24"
    )

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


def _semantic_similarity(concept: str, text: str) -> float:
    c = _normalize_text(concept)
    t = _normalize_text(text)
    if not c or not t:
        return 0.0
    return SequenceMatcher(None, c, t).ratio()


def _token_overlap(concept_tokens: list[str], text_tokens: list[str]) -> float:
    if not concept_tokens or not text_tokens:
        return 0.0
    cset = set(concept_tokens)
    tset = set(text_tokens)
    intersection = len(cset.intersection(tset))
    return intersection / max(1, len(cset))


def _phrase_match(concept: str, text: str) -> float:
    concept_normalized = _normalize_text(concept)
    text_normalized = _normalize_text(text)
    if not concept_normalized or not text_normalized:
        return 0.0
    if concept_normalized in text_normalized:
        return 1.0
    if any(token in text_normalized for token in _keywords(concept)):
        return 0.35
    return 0.0


def _quality_signal(candidate: Candidate) -> float:
    rating = max(0.0, min(candidate.rating, 1.0))
    popularity = min(candidate.downloads, 50000) / 50000.0
    source_bias = 0.15 if candidate.source == "blenderkit" else 0.08 if candidate.source == "sketchfab" else 0.04
    return min(1.0, (rating * 0.55) + (popularity * 0.30) + source_bias)


def _composite_score(concept: str, candidate: Candidate) -> float:
    meta_blob = " ".join(
        part for part in [candidate.name, candidate.description, " ".join(candidate.tags), candidate.category] if part
    )
    concept_tokens = _keywords(concept)
    text_tokens = _keywords(meta_blob)

    semantic = _semantic_similarity(concept, meta_blob)
    overlap = _token_overlap(concept_tokens, text_tokens)
    phrase = _phrase_match(concept, meta_blob)
    quality = _quality_signal(candidate)

    score = (
        semantic * 0.36
        + overlap * 0.30
        + phrase * 0.20
        + quality * 0.14
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


def _resolve_sketchfab_download(candidate: Candidate) -> tuple[str | None, dict[str, str] | None]:
    if not SKETCHFAB_API_TOKEN:
        return None, None

    uid = candidate.source_id
    if not uid:
        return None, None

    headers = {"Authorization": f"Token {SKETCHFAB_API_TOKEN}"}
    try:
        data = _request_json_with_retry(f"https://api.sketchfab.com/v3/models/{uid}/download", headers=headers, timeout=25)
    except Exception:
        return None, None

    gltf = data.get("gltf") if isinstance(data, dict) else None
    if isinstance(gltf, dict):
        return gltf.get("url"), headers
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
            url = _resolve_blenderkit_download(candidate)
            headers = None
        elif candidate.source == "sketchfab":
            url, headers = _resolve_sketchfab_download(candidate)
        elif candidate.source == "poly_archive":
            url = _resolve_poly_download(candidate)
            headers = None
        else:
            return None

        if not url:
            return None

        binary = _download_binary_with_retry(url, headers=headers, timeout=90)
        with open(model_path, "wb") as file_obj:
            file_obj.write(binary)
        return model_filename
    except Exception:
        return None


def _build_primitive_mesh(concept: str):
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

    candidates: list[Candidate] = []
    candidates.extend(_blenderkit_candidates(concept))
    candidates.extend(_sketchfab_candidates(concept))
    candidates.extend(_poly_archive_candidates(concept))

    ranked: list[tuple[float, Candidate]] = []
    for candidate in candidates:
        score = _composite_score(concept, candidate)
        ranked.append((score, candidate))

    ranked.sort(key=lambda item: item[0], reverse=True)

    for confidence, candidate in ranked:
        if confidence < MIN_CONFIDENCE:
            break

        filename = _download_and_cache_glb(candidate, models_dir)
        if not filename:
            continue

        viewer = f"{backend_base_url}/models/{filename}"
        return {
            "type": "retrieved",
            "model_url": viewer,
            "metadata": {
                "source": candidate.source,
                "confidence_score": round(confidence, 4),
                "name": candidate.name,
                "description": candidate.description,
                "tags": candidate.tags,
                "format": candidate.format_type,
            },
        }

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
        "fallback_shapes": ["cube"],
    }
