import hashlib
import html
import json
import os
import re
import urllib.parse
from difflib import SequenceMatcher
from urllib.parse import urlparse

import requests

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None
    ImageDraw = None


_STOPWORDS = {
    "a", "an", "and", "or", "the", "of", "for", "to", "in", "on", "at", "with", "by", "from",
    "is", "are", "was", "were", "this", "that", "these", "those", "about",
}

_DOMAIN_TOKENS = {
    "virus", "disease", "bacteria", "bacterium", "anatomy", "heart", "lung", "brain", "kidney",
    "animal", "plant", "car", "tree", "house", "monument", "fort", "mahal",
}

_BIOGRAPHY_HINTS = {
    "person", "actor", "actress", "singer", "politician", "cleric", "scholar", "leader", "biography",
}

_EXTERNAL_IMAGE_CONFIDENCE_THRESHOLD = 0.62
_PERSON_ENTITY_CONFIDENCE_THRESHOLD = 0.78


def _tokenize(text: str):
    if not text:
        return []
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t and t not in _STOPWORDS]


def _strip_html(text: str):
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


def _is_wikipedia_summary_relevant(concept: str, payload: dict):
    concept_tokens = _tokenize(concept)
    if not concept_tokens:
        return True

    title = payload.get("title", "") if isinstance(payload, dict) else ""
    description = payload.get("description", "") if isinstance(payload, dict) else ""
    extract = payload.get("extract", "") if isinstance(payload, dict) else ""
    combined_tokens = set(_tokenize(f"{title} {description} {extract}"))

    overlap = set(concept_tokens) & combined_tokens
    if not overlap:
        return False

    required = set(concept_tokens) & _DOMAIN_TOKENS
    if required and not (required & combined_tokens):
        return False

    if (set(_tokenize(description)) | set(_tokenize(extract))) & _BIOGRAPHY_HINTS:
        if not (set(concept_tokens) & _BIOGRAPHY_HINTS):
            return False

    return True


def _is_person_entity_query(concept: str):
    tokens = _tokenize(concept)
    if not tokens:
        return False

    # A short phrase without domain terms is likely a person/entity name query.
    if len(tokens) <= 4 and not (set(tokens) & _DOMAIN_TOKENS):
        return True
    return bool(set(tokens) & _BIOGRAPHY_HINTS)


def _compute_external_match_confidence(concept: str, title: str, description: str = "", extract: str = ""):
    concept_tokens = _tokenize(concept)
    title_tokens = _tokenize(title)
    context_tokens = set(_tokenize(f"{title} {description} {extract}"))
    if not concept_tokens:
        return 0.0

    overlap = len(set(concept_tokens) & context_tokens) / max(1, len(set(concept_tokens)))
    title_ratio = SequenceMatcher(None, " ".join(concept_tokens), " ".join(title_tokens)).ratio()
    domain_tokens = set(concept_tokens) & _DOMAIN_TOKENS
    domain_hit = 1.0 if (domain_tokens and domain_tokens & context_tokens) else (0.6 if not domain_tokens else 0.0)

    confidence = 0.45 * overlap + 0.4 * title_ratio + 0.15 * domain_hit

    # Penalize non-person queries accidentally matching biography pages.
    if not _is_person_entity_query(concept):
        bio_tokens = set(_tokenize(f"{description} {extract}"))
        if bio_tokens & _BIOGRAPHY_HINTS:
            confidence -= 0.2

    return max(0.0, min(1.0, confidence))


def _passes_confidence_threshold(concept: str, confidence: float):
    threshold = _PERSON_ENTITY_CONFIDENCE_THRESHOLD if _is_person_entity_query(concept) else _EXTERNAL_IMAGE_CONFIDENCE_THRESHOLD
    return confidence >= threshold


def _score_wikipedia_title_match(concept: str, title: str, snippet: str):
    concept_tokens = _tokenize(concept)
    if not concept_tokens:
        return 0

    haystack = set(_tokenize(f"{title} {_strip_html(snippet)}"))
    required = set(concept_tokens) & _DOMAIN_TOKENS
    if required and not (required & haystack):
        return -100

    score = 0
    for token in concept_tokens:
        if token in haystack:
            score += 3
        if token in _DOMAIN_TOKENS and token in haystack:
            score += 5

    if "disambiguation" in (title or "").lower():
        score -= 5

    return score


def _is_strong_title_match(concept: str, title: str):
    concept_tokens = _tokenize(concept)
    title_tokens = _tokenize(title)
    if not concept_tokens or not title_tokens:
        return False

    overlap = len(set(concept_tokens) & set(title_tokens))
    overlap_ratio = overlap / max(1, len(set(concept_tokens)))
    ratio = SequenceMatcher(None, " ".join(concept_tokens), " ".join(title_tokens)).ratio()

    # For open-domain queries (mostly names), require stronger lexical agreement.
    has_domain_token = bool(set(concept_tokens) & _DOMAIN_TOKENS)
    if has_domain_token:
        return overlap_ratio >= 0.5 or ratio >= 0.72
    return overlap_ratio >= 0.6 or ratio >= 0.78


def _is_valid_image_file(filepath: str):
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return False

    if Image is not None:
        try:
            with Image.open(filepath) as img:
                img.verify()
            return True
        except Exception:
            return False

    # Minimal magic-byte check when Pillow is unavailable.
    try:
        with open(filepath, "rb") as fh:
            header = fh.read(16)
        if header.startswith(b"\xFF\xD8\xFF"):
            return True  # JPEG
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return True  # PNG
        if header.startswith(b"RIFF") and b"WEBP" in header:
            return True  # WEBP
    except Exception:
        return False
    return False


def _is_remote_image_url_available(url: str):
    if not url:
        return False
    try:
        response = requests.get(url, timeout=12, stream=True)
        response.raise_for_status()
        content_type = (response.headers.get("Content-Type") or "").lower()
        return "image" in content_type
    except Exception:
        return False


def _concept_primitives(concept: str):
    templates = _concept_part_templates(concept)
    if templates:
        return [p.get("primitive", "cube") for p in templates]

    # Smarter default: complex queries should not collapse to a single cube.
    tokens = _tokenize(concept)
    if len(tokens) >= 2:
        return ["cube", "sphere", "cylinder"]
    return ["cube", "sphere"]


def _concept_part_templates(concept: str):
    query = (concept or "").lower()

    if "chair" in query:
        return [
            {
                "name": "seat",
                "primitive": "cube",
                "parameters": {"width": 1.5, "height": 0.25, "depth": 1.4},
                "position": {"x": 0.0, "y": 0.3, "z": 0.0},
                "description": "Main sitting surface.",
            },
            {
                "name": "backrest",
                "primitive": "cube",
                "parameters": {"width": 1.5, "height": 1.3, "depth": 0.2},
                "position": {"x": 0.0, "y": 1.0, "z": -0.6},
                "description": "Supports the back.",
            },
            {
                "name": "front_left_leg",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.08, "radiusBottom": 0.08, "height": 1.0, "radialSegments": 20},
                "position": {"x": -0.6, "y": -0.35, "z": 0.55},
                "description": "Front-left support leg.",
            },
            {
                "name": "front_right_leg",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.08, "radiusBottom": 0.08, "height": 1.0, "radialSegments": 20},
                "position": {"x": 0.6, "y": -0.35, "z": 0.55},
                "description": "Front-right support leg.",
            },
            {
                "name": "rear_left_leg",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.08, "radiusBottom": 0.08, "height": 1.0, "radialSegments": 20},
                "position": {"x": -0.6, "y": -0.35, "z": -0.55},
                "description": "Rear-left support leg.",
            },
            {
                "name": "rear_right_leg",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.08, "radiusBottom": 0.08, "height": 1.0, "radialSegments": 20},
                "position": {"x": 0.6, "y": -0.35, "z": -0.55},
                "description": "Rear-right support leg.",
            },
        ]

    if "table" in query:
        return [
            {
                "name": "table_top",
                "primitive": "cube",
                "parameters": {"width": 2.2, "height": 0.2, "depth": 1.4},
                "position": {"x": 0.0, "y": 0.7, "z": 0.0},
                "description": "Top flat surface.",
            },
            {
                "name": "leg_1",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.09, "radiusBottom": 0.09, "height": 1.4, "radialSegments": 20},
                "position": {"x": -0.95, "y": -0.1, "z": 0.55},
                "description": "Corner support leg.",
            },
            {
                "name": "leg_2",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.09, "radiusBottom": 0.09, "height": 1.4, "radialSegments": 20},
                "position": {"x": 0.95, "y": -0.1, "z": 0.55},
                "description": "Corner support leg.",
            },
            {
                "name": "leg_3",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.09, "radiusBottom": 0.09, "height": 1.4, "radialSegments": 20},
                "position": {"x": -0.95, "y": -0.1, "z": -0.55},
                "description": "Corner support leg.",
            },
            {
                "name": "leg_4",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.09, "radiusBottom": 0.09, "height": 1.4, "radialSegments": 20},
                "position": {"x": 0.95, "y": -0.1, "z": -0.55},
                "description": "Corner support leg.",
            },
        ]

    if "car" in query:
        return [
            {
                "name": "body",
                "primitive": "cube",
                "parameters": {"width": 2.7, "height": 0.9, "depth": 1.3},
                "position": {"x": 0.0, "y": 0.1, "z": 0.0},
                "description": "Main vehicle body.",
            },
            {
                "name": "cabin",
                "primitive": "cube",
                "parameters": {"width": 1.5, "height": 0.7, "depth": 1.1},
                "position": {"x": 0.2, "y": 0.75, "z": 0.0},
                "description": "Passenger cabin.",
            },
            {
                "name": "front_left_wheel",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.35, "radiusBottom": 0.35, "height": 0.3, "radialSegments": 24},
                "position": {"x": -0.9, "y": -0.45, "z": 0.7},
                "description": "Front-left wheel.",
            },
            {
                "name": "front_right_wheel",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.35, "radiusBottom": 0.35, "height": 0.3, "radialSegments": 24},
                "position": {"x": 0.9, "y": -0.45, "z": 0.7},
                "description": "Front-right wheel.",
            },
            {
                "name": "rear_left_wheel",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.35, "radiusBottom": 0.35, "height": 0.3, "radialSegments": 24},
                "position": {"x": -0.9, "y": -0.45, "z": -0.7},
                "description": "Rear-left wheel.",
            },
            {
                "name": "rear_right_wheel",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.35, "radiusBottom": 0.35, "height": 0.3, "radialSegments": 24},
                "position": {"x": 0.9, "y": -0.45, "z": -0.7},
                "description": "Rear-right wheel.",
            },
        ]

    if "house" in query:
        return [
            {
                "name": "base",
                "primitive": "cube",
                "parameters": {"width": 2.2, "height": 1.5, "depth": 2.0},
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "description": "Main building mass.",
            },
            {
                "name": "roof",
                "primitive": "cone",
                "parameters": {"radius": 1.5, "height": 1.0, "radialSegments": 4},
                "position": {"x": 0.0, "y": 1.25, "z": 0.0},
                "description": "Pitched roof structure.",
            },
            {
                "name": "door",
                "primitive": "cube",
                "parameters": {"width": 0.45, "height": 0.9, "depth": 0.08},
                "position": {"x": 0.0, "y": -0.35, "z": 1.02},
                "description": "Front entrance.",
            },
        ]

    if "tree" in query:
        return [
            {
                "name": "trunk",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.2, "radiusBottom": 0.28, "height": 1.8, "radialSegments": 20},
                "position": {"x": 0.0, "y": -0.2, "z": 0.0},
                "description": "Central trunk.",
            },
            {
                "name": "canopy",
                "primitive": "sphere",
                "parameters": {"radius": 1.0, "widthSegments": 28, "heightSegments": 28},
                "position": {"x": 0.0, "y": 1.2, "z": 0.0},
                "description": "Leaf canopy.",
            },
        ]

    if "heart" in query:
        return [
            {
                "name": "left_lobe",
                "primitive": "sphere",
                "parameters": {"radius": 0.58, "widthSegments": 28, "heightSegments": 28},
                "position": {"x": -0.35, "y": 0.4, "z": 0.0},
                "description": "Upper left lobe.",
            },
            {
                "name": "right_lobe",
                "primitive": "sphere",
                "parameters": {"radius": 0.58, "widthSegments": 28, "heightSegments": 28},
                "position": {"x": 0.35, "y": 0.4, "z": 0.0},
                "description": "Upper right lobe.",
            },
            {
                "name": "aorta",
                "primitive": "tube",
                "parameters": {"radiusTop": 0.15, "radiusBottom": 0.15, "height": 1.1, "radialSegments": 24},
                "position": {"x": 0.0, "y": 1.1, "z": 0.0},
                "description": "Primary outgoing vessel.",
            },
        ]

    if "apple" in query:
        return [
            {
                "name": "fruit_body",
                "primitive": "sphere",
                "parameters": {"radius": 0.95, "widthSegments": 30, "heightSegments": 30},
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "description": "Main edible body of the apple.",
            },
            {
                "name": "top_indent",
                "primitive": "sphere",
                "parameters": {"radius": 0.35, "widthSegments": 18, "heightSegments": 18},
                "position": {"x": 0.0, "y": 0.85, "z": 0.0},
                "description": "Top cavity where the stem emerges.",
            },
            {
                "name": "stem",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.06, "radiusBottom": 0.08, "height": 0.45, "radialSegments": 16},
                "position": {"x": 0.0, "y": 1.2, "z": 0.0},
                "description": "Short central stem.",
            },
            {
                "name": "leaf",
                "primitive": "cone",
                "parameters": {"radius": 0.16, "height": 0.45, "radialSegments": 12},
                "position": {"x": 0.2, "y": 1.25, "z": 0.0},
                "description": "Stylized leaf attached near the stem.",
            },
        ]

    if "taj mahal" in query:
        return [
            {
                "name": "main_platform",
                "primitive": "cube",
                "parameters": {"width": 3.6, "height": 0.5, "depth": 3.6},
                "position": {"x": 0.0, "y": -0.8, "z": 0.0},
                "description": "Raised marble platform.",
            },
            {
                "name": "central_block",
                "primitive": "cube",
                "parameters": {"width": 2.2, "height": 1.6, "depth": 2.2},
                "position": {"x": 0.0, "y": 0.15, "z": 0.0},
                "description": "Central mausoleum chamber.",
            },
            {
                "name": "main_dome",
                "primitive": "sphere",
                "parameters": {"radius": 0.95, "widthSegments": 30, "heightSegments": 24},
                "position": {"x": 0.0, "y": 1.35, "z": 0.0},
                "description": "Primary onion-shaped dome.",
            },
            {
                "name": "minaret_nw",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.12, "radiusBottom": 0.14, "height": 2.2, "radialSegments": 18},
                "position": {"x": -1.6, "y": 0.1, "z": -1.6},
                "description": "North-west corner minaret.",
            },
            {
                "name": "minaret_ne",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.12, "radiusBottom": 0.14, "height": 2.2, "radialSegments": 18},
                "position": {"x": 1.6, "y": 0.1, "z": -1.6},
                "description": "North-east corner minaret.",
            },
            {
                "name": "minaret_sw",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.12, "radiusBottom": 0.14, "height": 2.2, "radialSegments": 18},
                "position": {"x": -1.6, "y": 0.1, "z": 1.6},
                "description": "South-west corner minaret.",
            },
            {
                "name": "minaret_se",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.12, "radiusBottom": 0.14, "height": 2.2, "radialSegments": 18},
                "position": {"x": 1.6, "y": 0.1, "z": 1.6},
                "description": "South-east corner minaret.",
            },
        ]

    if "red fort" in query or "fort" in query:
        return [
            {
                "name": "fort_base",
                "primitive": "cube",
                "parameters": {"width": 3.6, "height": 1.2, "depth": 2.4},
                "position": {"x": 0.0, "y": -0.1, "z": 0.0},
                "description": "Main fortified wall body.",
            },
            {
                "name": "left_tower",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.38, "radiusBottom": 0.42, "height": 1.8, "radialSegments": 20},
                "position": {"x": -1.45, "y": 0.2, "z": 0.0},
                "description": "Left defensive bastion.",
            },
            {
                "name": "right_tower",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.38, "radiusBottom": 0.42, "height": 1.8, "radialSegments": 20},
                "position": {"x": 1.45, "y": 0.2, "z": 0.0},
                "description": "Right defensive bastion.",
            },
            {
                "name": "gate_block",
                "primitive": "cube",
                "parameters": {"width": 1.0, "height": 1.4, "depth": 0.7},
                "position": {"x": 0.0, "y": 0.15, "z": 0.95},
                "description": "Central gateway block.",
            },
        ]

    # Generic monument/city landmarks as structured breakdown.
    if any(token in query for token in ["mahal", "monument", "temple", "palace", "tower", "castle"]):
        return [
            {
                "name": "base_plinth",
                "primitive": "cube",
                "parameters": {"width": 3.0, "height": 0.5, "depth": 2.6},
                "position": {"x": 0.0, "y": -0.7, "z": 0.0},
                "description": "Foundational platform.",
            },
            {
                "name": "central_mass",
                "primitive": "cube",
                "parameters": {"width": 1.8, "height": 1.5, "depth": 1.8},
                "position": {"x": 0.0, "y": 0.1, "z": 0.0},
                "description": "Primary central structure.",
            },
            {
                "name": "crown",
                "primitive": "sphere",
                "parameters": {"radius": 0.7, "widthSegments": 24, "heightSegments": 24},
                "position": {"x": 0.0, "y": 1.35, "z": 0.0},
                "description": "Top architectural crown.",
            },
            {
                "name": "side_tower_left",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.16, "radiusBottom": 0.18, "height": 1.8, "radialSegments": 16},
                "position": {"x": -1.25, "y": 0.1, "z": 0.0},
                "description": "Left side tower.",
            },
            {
                "name": "side_tower_right",
                "primitive": "cylinder",
                "parameters": {"radiusTop": 0.16, "radiusBottom": 0.18, "height": 1.8, "radialSegments": 16},
                "position": {"x": 1.25, "y": 0.1, "z": 0.0},
                "description": "Right side tower.",
            },
        ]

    return _build_generalized_part_template(concept)


def _build_generalized_part_template(concept: str):
    query = (concept or "object").strip().lower()
    tokens = _tokenize(query)

    def _part(name, primitive, description, position, parameters):
        return {
            "name": name,
            "primitive": primitive,
            "description": description,
            "position": position,
            "parameters": parameters,
        }

    category = "generic"
    if any(t in query for t in ["chair", "table", "desk", "sofa", "bed"]):
        category = "furniture"
    elif any(t in query for t in ["apple", "mango", "banana", "fruit", "orange", "grape"]):
        category = "fruit"
    elif any(t in query for t in ["car", "bus", "truck", "bike", "vehicle", "train"]):
        category = "vehicle"
    elif any(t in query for t in ["heart", "brain", "lung", "kidney", "organ", "anatomy"]):
        category = "anatomy"
    elif any(t in query for t in ["mahal", "monument", "temple", "palace", "tower", "castle", "fort"]):
        category = "monument"
    elif any(t in query for t in ["house", "building", "home", "architecture"]):
        category = "architecture"

    complexity = "simple"
    if len(tokens) >= 4:
        complexity = "complex"
    elif len(tokens) >= 2:
        complexity = "medium"

    if category == "furniture":
        parts = [
            _part(
                "main_surface",
                "cube",
                f"Primary functional surface for {concept}.",
                {"x": 0.0, "y": 0.3, "z": 0.0},
                {"width": 1.8, "height": 0.28, "depth": 1.4},
            ),
            _part(
                "support_frame",
                "cube",
                "Structural frame connecting supports.",
                {"x": 0.0, "y": -0.05, "z": 0.0},
                {"width": 1.5, "height": 0.22, "depth": 1.1},
            ),
            _part(
                "left_support",
                "cylinder",
                "Left vertical support element.",
                {"x": -0.65, "y": -0.45, "z": 0.45},
                {"radiusTop": 0.08, "radiusBottom": 0.09, "height": 1.0, "radialSegments": 16},
            ),
            _part(
                "right_support",
                "cylinder",
                "Right vertical support element.",
                {"x": 0.65, "y": -0.45, "z": 0.45},
                {"radiusTop": 0.08, "radiusBottom": 0.09, "height": 1.0, "radialSegments": 16},
            ),
        ]
        if complexity != "simple":
            parts.append(
                _part(
                    "rear_support_pair",
                    "cylinder",
                    "Back support pair represented as one grouped component.",
                    {"x": 0.0, "y": -0.45, "z": -0.5},
                    {"radiusTop": 0.1, "radiusBottom": 0.1, "height": 1.0, "radialSegments": 16},
                )
            )
        return parts

    if category == "fruit":
        parts = [
            _part(
                "fruit_body",
                "sphere",
                f"Main volume of {concept}.",
                {"x": 0.0, "y": 0.0, "z": 0.0},
                {"radius": 0.9, "widthSegments": 26, "heightSegments": 26},
            ),
            _part(
                "top_cavity",
                "sphere",
                "Top indentation zone.",
                {"x": 0.0, "y": 0.78, "z": 0.0},
                {"radius": 0.3, "widthSegments": 18, "heightSegments": 18},
            ),
            _part(
                "stem",
                "cylinder",
                "Stem attachment.",
                {"x": 0.0, "y": 1.15, "z": 0.0},
                {"radiusTop": 0.05, "radiusBottom": 0.07, "height": 0.35, "radialSegments": 12},
            ),
        ]
        if complexity != "simple":
            parts.append(
                _part(
                    "leaf",
                    "cone",
                    "Leaf-like accent element.",
                    {"x": 0.2, "y": 1.2, "z": 0.0},
                    {"radius": 0.15, "height": 0.38, "radialSegments": 10},
                )
            )
        return parts

    if category == "vehicle":
        return [
            _part(
                "chassis",
                "cube",
                f"Main body frame for {concept}.",
                {"x": 0.0, "y": 0.1, "z": 0.0},
                {"width": 2.6, "height": 0.85, "depth": 1.2},
            ),
            _part(
                "upper_cabin",
                "cube",
                "Upper passenger or control area.",
                {"x": 0.1, "y": 0.72, "z": 0.0},
                {"width": 1.4, "height": 0.6, "depth": 1.0},
            ),
            _part(
                "front_axle_wheels",
                "cylinder",
                "Front wheel assembly.",
                {"x": 0.9, "y": -0.45, "z": 0.0},
                {"radiusTop": 0.34, "radiusBottom": 0.34, "height": 1.2, "radialSegments": 22},
            ),
            _part(
                "rear_axle_wheels",
                "cylinder",
                "Rear wheel assembly.",
                {"x": -0.9, "y": -0.45, "z": 0.0},
                {"radiusTop": 0.34, "radiusBottom": 0.34, "height": 1.2, "radialSegments": 22},
            ),
        ]

    if category == "anatomy":
        return [
            _part(
                "core_mass",
                "sphere",
                f"Core anatomical mass for {concept}.",
                {"x": 0.0, "y": 0.2, "z": 0.0},
                {"radius": 0.95, "widthSegments": 26, "heightSegments": 26},
            ),
            _part(
                "secondary_lobe",
                "sphere",
                "Secondary structural lobe.",
                {"x": 0.45, "y": 0.25, "z": 0.0},
                {"radius": 0.55, "widthSegments": 20, "heightSegments": 20},
            ),
            _part(
                "primary_vessel",
                "tube",
                "Major connecting vessel/tube.",
                {"x": 0.0, "y": 1.0, "z": 0.0},
                {"radiusTop": 0.16, "radiusBottom": 0.16, "height": 1.1, "radialSegments": 20},
            ),
        ]

    if category == "monument":
        parts = [
            _part(
                "base_plinth",
                "cube",
                f"Foundational platform for {concept}.",
                {"x": 0.0, "y": -0.7, "z": 0.0},
                {"width": 3.1, "height": 0.5, "depth": 2.8},
            ),
            _part(
                "central_structure",
                "cube",
                "Primary mass of the monument.",
                {"x": 0.0, "y": 0.1, "z": 0.0},
                {"width": 2.0, "height": 1.6, "depth": 2.0},
            ),
            _part(
                "main_crown",
                "sphere",
                "Top crown/dome element.",
                {"x": 0.0, "y": 1.35, "z": 0.0},
                {"radius": 0.75, "widthSegments": 24, "heightSegments": 24},
            ),
            _part(
                "left_tower",
                "cylinder",
                "Left side vertical tower.",
                {"x": -1.3, "y": 0.2, "z": 0.0},
                {"radiusTop": 0.15, "radiusBottom": 0.17, "height": 1.9, "radialSegments": 16},
            ),
            _part(
                "right_tower",
                "cylinder",
                "Right side vertical tower.",
                {"x": 1.3, "y": 0.2, "z": 0.0},
                {"radiusTop": 0.15, "radiusBottom": 0.17, "height": 1.9, "radialSegments": 16},
            ),
        ]
        if complexity == "complex":
            parts.extend(
                [
                    _part(
                        "front_tower",
                        "cylinder",
                        "Front perimeter tower.",
                        {"x": 0.0, "y": 0.2, "z": 1.35},
                        {"radiusTop": 0.13, "radiusBottom": 0.15, "height": 1.7, "radialSegments": 14},
                    ),
                    _part(
                        "rear_tower",
                        "cylinder",
                        "Rear perimeter tower.",
                        {"x": 0.0, "y": 0.2, "z": -1.35},
                        {"radiusTop": 0.13, "radiusBottom": 0.15, "height": 1.7, "radialSegments": 14},
                    ),
                ]
            )
        return parts

    if category == "architecture":
        return [
            _part(
                "base_volume",
                "cube",
                f"Primary building mass for {concept}.",
                {"x": 0.0, "y": 0.0, "z": 0.0},
                {"width": 2.4, "height": 1.6, "depth": 2.0},
            ),
            _part(
                "roof_structure",
                "cone",
                "Roofing structure.",
                {"x": 0.0, "y": 1.25, "z": 0.0},
                {"radius": 1.5, "height": 0.95, "radialSegments": 4},
            ),
            _part(
                "entry_block",
                "cube",
                "Entrance mass.",
                {"x": 0.0, "y": -0.35, "z": 1.02},
                {"width": 0.5, "height": 0.9, "depth": 0.08},
            ),
        ]

    # Generic multi-part conceptual breakdown for unknown input.
    generic_parts = [
        _part(
            "core",
            "cube",
            f"Core structure inferred from '{concept}'.",
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"width": 1.6, "height": 1.1, "depth": 1.3},
        ),
        _part(
            "upper_feature",
            "sphere",
            "Primary top-level feature.",
            {"x": 0.0, "y": 1.0, "z": 0.0},
            {"radius": 0.55, "widthSegments": 22, "heightSegments": 22},
        ),
        _part(
            "support",
            "cylinder",
            "Supportive connecting element.",
            {"x": 0.0, "y": -0.7, "z": 0.0},
            {"radiusTop": 0.16, "radiusBottom": 0.2, "height": 1.2, "radialSegments": 16},
        ),
    ]
    if complexity == "complex":
        generic_parts.append(
            _part(
                "secondary_feature",
                "cone",
                "Secondary feature inferred from query complexity.",
                {"x": 0.9, "y": 0.5, "z": 0.0},
                {"radius": 0.35, "height": 0.9, "radialSegments": 14},
            )
        )
    return generic_parts


def _shape_parameters(shape_name: str):
    defaults = {
        "cube": {"width": 1.4, "height": 1.0, "depth": 1.2},
        "sphere": {"radius": 0.75, "widthSegments": 32, "heightSegments": 32},
        "cylinder": {
            "radiusTop": 0.5,
            "radiusBottom": 0.55,
            "height": 1.6,
            "radialSegments": 24,
        },
        "cone": {"radius": 0.6, "height": 1.5, "radialSegments": 24},
        "tube": {
            "radiusTop": 0.28,
            "radiusBottom": 0.28,
            "height": 1.6,
            "radialSegments": 24,
        },
    }
    return defaults.get(shape_name, {"width": 1.0, "height": 1.0, "depth": 1.0})


def _build_geometry_details(concept: str, shapes: list[str]):
    templates = _concept_part_templates(concept)
    if templates:
        return {
            "concept": concept,
            "total_parts": len(templates),
            "shapes": templates,
        }

    details = []
    total = len(shapes)
    for idx, shape in enumerate(shapes):
        x_offset = (idx - (total - 1) / 2.0) * 2.0
        details.append(
            {
                "name": f"part_{idx + 1}",
                "primitive": shape,
                "parameters": _shape_parameters(shape),
                "position": {"x": round(x_offset, 3), "y": 0.0, "z": 0.0},
                "description": f"Procedural {shape} block for {concept}",
            }
        )
    return {
        "concept": concept,
        "total_parts": len(details),
        "shapes": details,
    }


def _draw_shape(draw, shape: str, x: int, y: int, size: int, color):
    if shape == "cube":
        draw.rectangle((x - size, y - size, x + size, y + size), outline=color, width=4)
    elif shape == "sphere":
        draw.ellipse((x - size, y - size, x + size, y + size), outline=color, width=4)
    elif shape in ["cylinder", "tube"]:
        draw.ellipse((x - size, y - size, x + size, y - size // 2), outline=color, width=3)
        draw.ellipse((x - size, y + size // 2, x + size, y + size), outline=color, width=3)
        draw.line((x - size, y - size * 3 // 4, x - size, y + size * 3 // 4), fill=color, width=3)
        draw.line((x + size, y - size * 3 // 4, x + size, y + size * 3 // 4), fill=color, width=3)
    elif shape == "cone":
        draw.polygon([(x, y - size), (x - size, y + size), (x + size, y + size)], outline=color, width=4)
    else:
        draw.rectangle((x - size, y - size, x + size, y + size), outline=color, width=3)


def _generate_preview_image(concept: str, shapes: list[str], models_dir: str, backend_base_url: str):
    if Image is None or ImageDraw is None:
        return None

    key = hashlib.md5(
        json.dumps(
            {"concept": concept, "shapes": shapes, "layout_version": 2},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    filename = f"fallback_preview_{key}.png"
    filepath = os.path.join(models_dir, filename)
    if _is_valid_image_file(filepath):
        return f"{backend_base_url}/models/{filename}"
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass

    width, height = 1000, 620
    image = Image.new("RGB", (width, height), (12, 14, 22))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, width, 120), fill=(18, 22, 35))
    draw.text((32, 32), f"Fallback 2D Blueprint: {concept.title()}", fill=(220, 235, 255))
    draw.text(
        (32, 74),
        "Generated from primitive geometry because no exact 3D match was found.",
        fill=(150, 170, 190),
    )

    # Draw abstract concept cards so fallback remains visually meaningful
    # even when external image providers fail.
    words = [w for w in concept.title().split() if w]
    if not words:
        words = ["Concept"]

    color_palette = [(26, 188, 156), (52, 152, 219), (241, 196, 15), (231, 76, 60), (155, 89, 182)]
    digest = hashlib.md5(concept.encode("utf-8")).digest()

    card_w, card_h = 260, 150
    start_x = 80
    gap = 36
    y = 250
    max_cards = min(3, max(1, len(words)))
    for idx in range(max_cards):
        x = start_x + idx * (card_w + gap)
        c = color_palette[digest[idx] % len(color_palette)]
        draw.rectangle((x, y, x + card_w, y + card_h), outline=c, width=4)
        label = words[idx] if idx < len(words) else f"Part {idx + 1}"
        draw.text((x + 20, y + 56), label, fill=(220, 230, 245))

    # A subtle horizon line adds structure and avoids an empty center.
    draw.line((70, 455, width - 70, 455), fill=(44, 62, 80), width=2)

    draw.text(
        (32, 560),
        "Use the geometry details below the viewer to inspect exact dimensions and placement.",
        fill=(132, 145, 160),
    )

    os.makedirs(models_dir, exist_ok=True)
    image.save(filepath, format="PNG")
    return f"{backend_base_url}/models/{filename}"


def _generate_svg_fallback_image(concept: str, models_dir: str, backend_base_url: str):
        if not concept or not models_dir or not backend_base_url:
                return None

        key = hashlib.md5(
                json.dumps({"concept": concept, "type": "svg_fallback", "version": 1}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        filename = f"fallback_svg_{key}.svg"
        filepath = os.path.join(models_dir, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                return f"{backend_base_url}/models/{filename}"

        safe_concept = html.escape((concept or "Object").title())
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="620" viewBox="0 0 1000 620">
    <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#0b1220" />
            <stop offset="100%" stop-color="#111c33" />
        </linearGradient>
    </defs>
    <rect width="1000" height="620" fill="url(#bg)" />
    <rect x="0" y="0" width="1000" height="110" fill="#18223a" />
    <text x="32" y="44" fill="#dbeafe" font-size="26" font-family="Arial, sans-serif">2D Concept Fallback</text>
    <text x="32" y="82" fill="#a5b4cc" font-size="18" font-family="Arial, sans-serif">{safe_concept}</text>
    <rect x="120" y="190" width="320" height="220" rx="14" fill="none" stroke="#22d3ee" stroke-width="4" />
    <rect x="560" y="190" width="320" height="220" rx="14" fill="none" stroke="#fbbf24" stroke-width="4" />
    <text x="160" y="320" fill="#e2e8f0" font-size="30" font-family="Arial, sans-serif">{safe_concept.split(' ')[0]}</text>
    <text x="600" y="320" fill="#e2e8f0" font-size="30" font-family="Arial, sans-serif">Concept</text>
    <line x1="100" y1="470" x2="900" y2="470" stroke="#334155" stroke-width="2" />
</svg>'''

        os.makedirs(models_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
                fh.write(svg)
        return f"{backend_base_url}/models/{filename}"


def _download_image(url: str, destination_path: str):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://commons.wikimedia.org/",
        }
        response = requests.get(url, timeout=20, headers=headers)
        response.raise_for_status()
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "image" not in content_type:
            print(f"[Fallback] Skipping non-image response for {url} (Content-Type={content_type})")
            return False

        # Reject SVG for local static serving unless explicitly converted.
        if "svg" in content_type:
            print(f"[Fallback] Skipping SVG response for {url}; using alternate fallback source")
            return False

        with open(destination_path, "wb") as fh:
            fh.write(response.content)
        print(f"[Fallback] Successfully downloaded image: {url} -> {destination_path}")
        return True
    except Exception as e:
        print(f"[Fallback] Failed to download image from {url}: {e}")
        return False


def _get_wikipedia_summary_image_url(concept: str, query_context: str | None = None):
    if not concept:
        return None

    relevance_query = query_context or concept

    headers = {
        "User-Agent": "Concept3D-Generative/1.0 (Educational AI model generation; contact: support@example.com)"
    }

    normalized = concept.strip().replace(" ", "_")
    candidates = [
        normalized,
        normalized.title(),
        concept.strip(),
    ]

    for title in candidates:
        encoded = urllib.parse.quote(title)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        try:
            response = requests.get(url, timeout=12, headers=headers)
            if response.status_code != 200:
                continue
            payload = response.json()
            if not _is_wikipedia_summary_relevant(relevance_query, payload):
                continue

            confidence = _compute_external_match_confidence(
                relevance_query,
                payload.get("title", "") if isinstance(payload, dict) else "",
                payload.get("description", "") if isinstance(payload, dict) else "",
                payload.get("extract", "") if isinstance(payload, dict) else "",
            )
            if not _passes_confidence_threshold(relevance_query, confidence):
                continue

            thumb = payload.get("thumbnail", {}) if isinstance(payload, dict) else {}
            image_url = thumb.get("source") or payload.get("originalimage", {}).get("source")
            if image_url:
                print(f"[Fallback] Found Wikipedia image for '{concept}': {image_url}")
                return image_url
        except Exception as e:
            print(f"[Fallback] Wikipedia API error for '{title}': {e}")
            continue

    print(f"[Fallback] No Wikipedia image found for '{concept}'")
    return None


def _resolve_wikipedia_title(concept: str):
    if not concept:
        return None

    headers = {
        "User-Agent": "Concept3D-Generative/1.0 (Educational AI model generation; contact: support@example.com)"
    }
    params = {
        "action": "query",
        "list": "search",
        "format": "json",
        "srsearch": concept,
        "srlimit": 8,
    }
    try:
        response = requests.get("https://en.wikipedia.org/w/api.php", params=params, timeout=12, headers=headers)
        response.raise_for_status()
        results = (response.json().get("query", {}) or {}).get("search", [])
        best_title = None
        best_score = -1
        for result in results:
            title = result.get("title")
            snippet = result.get("snippet", "")
            if isinstance(title, str) and title.strip():
                score = _score_wikipedia_title_match(concept, title.strip(), snippet)
                if score > best_score:
                    best_score = score
                    best_title = title.strip()
        if best_title and best_score > 0 and _is_strong_title_match(concept, best_title):
            return best_title
    except Exception as e:
        print(f"[Fallback] Wikipedia title resolution failed for '{concept}': {e}")
    return None


def _get_wikimedia_search_image_url(concept: str, query_context: str | None = None):
    if not concept:
        return None

    relevance_query = query_context or concept

    headers = {
        "User-Agent": "Concept3D-Generative/1.0 (Educational AI model generation; contact: support@example.com)"
    }

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": concept,
        "gsrnamespace": 6,
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": 1280,
    }
    try:
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params=params,
            timeout=15,
            headers=headers,
        )
        response.raise_for_status()
        pages = (response.json().get("query", {}) or {}).get("pages", {})
        concept_tokens = _tokenize(relevance_query)
        required = set(concept_tokens) & _DOMAIN_TOKENS
        best_url = None
        best_confidence = -1.0
        for page in pages.values():
            page_title = page.get("title", "")
            title_tokens = set(_tokenize(page_title))
            if required and not (required & title_tokens):
                continue

            confidence = _compute_external_match_confidence(relevance_query, page_title)
            if not _passes_confidence_threshold(relevance_query, confidence):
                continue

            imageinfo = page.get("imageinfo", [])
            if not imageinfo:
                continue
            info = imageinfo[0]
            image_url = info.get("thumburl") or info.get("url")
            if image_url:
                lower = image_url.lower()
                # Skip Wikimedia PDF document thumbnails that often return 429 or non-useful pages.
                if ".pdf" in lower:
                    continue
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_url = image_url
        return best_url
    except Exception:
        return None

    return None


def _generate_concept_image_from_free_api(concept: str, models_dir: str, backend_base_url: str):
    if not concept or not models_dir or not backend_base_url:
        return None

    key = hashlib.md5(
        json.dumps(
            {"concept": concept, "type": "external", "resolver_version": 2},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    resolved_title = _resolve_wikipedia_title(concept)
    source_url = (
        _get_wikipedia_summary_image_url(concept, query_context=concept)
        or _get_wikipedia_summary_image_url(resolved_title, query_context=concept)
        or _get_wikimedia_search_image_url(concept, query_context=concept)
        or _get_wikimedia_search_image_url(resolved_title, query_context=concept)
    )
    if not source_url:
        print(f"[Fallback] No free API image source found for '{concept}'")
        return None

    parsed = urlparse(source_url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".jpg"

    filename = f"fallback_concept_{key}{ext}"
    filepath = os.path.join(models_dir, filename)
    if _is_valid_image_file(filepath):
        print(f"[Fallback] Found cached free API image: {filename}")
        return f"{backend_base_url}/models/{filename}"
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass

    os.makedirs(models_dir, exist_ok=True)
    print(f"[Fallback] Fetching concept image for '{concept}' from Wikipedia/Wikimedia...")

    saved = _download_image(source_url, filepath)
    if not saved:
        return None

    if not _is_valid_image_file(filepath):
        print(f"[Fallback] Downloaded image is invalid: {filepath}")
        try:
            os.remove(filepath)
        except Exception:
            pass
        return None

    print("[Fallback] Successfully generated free API image URL")
    return f"{backend_base_url}/models/{filename}"


def _pollinations_fallback_url(concept: str):
    if not concept:
        return None
    prompt = urllib.parse.quote(f"high quality concept illustration of {concept}")
    return f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=768&nologo=true"


def _generate_concept_image_from_pollinations(concept: str, models_dir: str, backend_base_url: str):
    if not concept or not models_dir or not backend_base_url:
        return None

    key = hashlib.md5(
        json.dumps({"concept": concept, "type": "pollinations", "version": 1}, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    filename = f"fallback_pollinations_{key}.jpg"
    filepath = os.path.join(models_dir, filename)

    if _is_valid_image_file(filepath):
        return f"{backend_base_url}/models/{filename}"
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass

    image_url = _pollinations_fallback_url(concept)
    if not image_url:
        return None

    try:
        response = requests.get(image_url, timeout=25)
        response.raise_for_status()
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "image" not in content_type:
            return None

        os.makedirs(models_dir, exist_ok=True)
        with open(filepath, "wb") as fh:
            fh.write(response.content)

        if not _is_valid_image_file(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass
            return None

        return f"{backend_base_url}/models/{filename}"
    except Exception:
        return None


def build_fallback_payload(concept: str, models_dir: str | None = None, backend_base_url: str = ""):
    concept_name = concept or "object"
    shapes = _concept_primitives(concept_name)
    geometry = _build_geometry_details(concept_name, shapes)
    image_url = None
    image_source = None

    if models_dir and backend_base_url:
        print(f"[Fallback] Building fallback payload for '{concept_name}'...")
        image_url = _generate_concept_image_from_free_api(concept_name, models_dir, backend_base_url)
        if image_url:
            image_source = "free_api"
        else:
            image_url = _generate_concept_image_from_pollinations(concept_name, models_dir, backend_base_url)
            image_source = "pollinations" if image_url else None

        # Final safety net when external image sources are unavailable.
        if not image_url:
            image_url = _generate_preview_image(concept_name, shapes, models_dir, backend_base_url)
            image_source = "procedural_blueprint" if image_url else None

    if not image_url and models_dir and backend_base_url:
        image_url = _generate_preview_image(concept_name, shapes, models_dir, backend_base_url)
        image_source = image_source or ("procedural_blueprint" if image_url else None)

    if not image_url and models_dir and backend_base_url:
        image_url = _generate_svg_fallback_image(concept_name, models_dir, backend_base_url)
        image_source = image_source or ("svg_fallback" if image_url else None)

    return {
        "shapes": shapes,
        "geometry_details": geometry,
        "fallback_2d_image_url": image_url,
        "fallback_2d_source": image_source,
    }


def generate_fallback(concept: str):
    return _concept_primitives(concept)
