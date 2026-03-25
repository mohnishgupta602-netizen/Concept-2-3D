import hashlib
import json
import os
import urllib.parse

import requests

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None
    ImageDraw = None


def _concept_primitives(concept):
    if not concept:
        return ["cube"]

    primitives = {
        "tree": ["cylinder", "sphere"],
        "heart": ["sphere", "tube"],
        "taj mahal": ["cube", "sphere", "cylinder"],
        "car": ["cube", "cylinder"],
        "house": ["cube", "cone"],
        "red fort": ["cube", "cylinder", "cone"],
    }
    return primitives.get(concept.lower(), ["cube"])


def _shape_parameters(shape_name):
    defaults = {
        "cube": {"width": 1.4, "height": 1.0, "depth": 1.2},
        "sphere": {"radius": 0.75, "widthSegments": 32, "heightSegments": 32},
        "cylinder": {"radiusTop": 0.5, "radiusBottom": 0.55, "height": 1.6, "radialSegments": 24},
        "cone": {"radius": 0.6, "height": 1.5, "radialSegments": 24},
        "tube": {"radiusTop": 0.28, "radiusBottom": 0.28, "height": 1.6, "radialSegments": 24},
    }
    return defaults.get(shape_name, {"width": 1.0, "height": 1.0, "depth": 1.0})


def _build_geometry_details(concept, shapes):
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


def _draw_shape(draw, shape, x, y, size, color):
    if shape == "cube":
        draw.rectangle((x - size, y - size, x + size, y + size), outline=color, width=4)
    elif shape == "sphere":
        draw.ellipse((x - size, y - size, x + size, y + size), outline=color, width=4)
    elif shape == "cylinder" or shape == "tube":
        draw.ellipse((x - size, y - size, x + size, y - size // 2), outline=color, width=3)
        draw.ellipse((x - size, y + size // 2, x + size, y + size), outline=color, width=3)
        draw.line((x - size, y - size * 3 // 4, x - size, y + size * 3 // 4), fill=color, width=3)
        draw.line((x + size, y - size * 3 // 4, x + size, y + size * 3 // 4), fill=color, width=3)
    elif shape == "cone":
        draw.polygon([(x, y - size), (x - size, y + size), (x + size, y + size)], outline=color, width=4)
    else:
        draw.rectangle((x - size, y - size, x + size, y + size), outline=color, width=3)


def _generate_preview_image(concept, shapes, models_dir, backend_base_url):
    if Image is None or ImageDraw is None:
        return None

    key = hashlib.md5(json.dumps({"concept": concept, "shapes": shapes}, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    filename = f"fallback_preview_{key}.png"
    filepath = os.path.join(models_dir, filename)
    if os.path.exists(filepath):
        return f"{backend_base_url}/models/{filename}"

    width, height = 1000, 620
    image = Image.new("RGB", (width, height), (12, 14, 22))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, width, 120), fill=(18, 22, 35))
    draw.text((32, 32), f"Fallback 2D Blueprint: {concept.title()}", fill=(220, 235, 255))
    draw.text((32, 74), "Generated from primitive geometry because no exact 3D match was found.", fill=(150, 170, 190))

    colors = [(0, 220, 180), (70, 160, 255), (255, 170, 70), (255, 95, 140), (185, 170, 255)]
    pad = 90
    span = max(1, len(shapes))
    y = 310
    for idx, shape in enumerate(shapes):
        x = int(pad + (idx + 0.5) * (width - pad * 2) / span)
        color = colors[idx % len(colors)]
        _draw_shape(draw, shape, x, y, 62, color)
        draw.text((x - 45, y + 92), shape.upper(), fill=(220, 220, 220))

    draw.text((32, 560), "Use the geometry details below the viewer to inspect exact dimensions and placement.", fill=(132, 145, 160))

    os.makedirs(models_dir, exist_ok=True)
    image.save(filepath, format="PNG")
    return f"{backend_base_url}/models/{filename}"


def _download_image(url, destination_path):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://commons.wikimedia.org/",
        }
        response = requests.get(url, timeout=20, headers=headers)
        response.raise_for_status()
        with open(destination_path, "wb") as fh:
            fh.write(response.content)
        print(f"[Fallback] Successfully downloaded image: {url} -> {destination_path}")
        return True
    except Exception as e:
        print(f"[Fallback] Failed to download image from {url}: {e}")
        return False


def _get_wikipedia_summary_image_url(concept):
    if not concept:
        return None

    # User-Agent header is required by Wikipedia APIs to prevent bot blocking
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


def _get_wikimedia_search_image_url(concept):
    if not concept:
        return None

    # User-Agent header is required by Wikimedia APIs to prevent bot blocking
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
        response = requests.get("https://commons.wikimedia.org/w/api.php", params=params, timeout=15, headers=headers)
        response.raise_for_status()
        pages = (response.json().get("query", {}) or {}).get("pages", {})
        for page in pages.values():
            imageinfo = page.get("imageinfo", [])
            if not imageinfo:
                continue
            info = imageinfo[0]
            image_url = info.get("thumburl") or info.get("url")
            if image_url:
                lower = image_url.lower()
                if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    return image_url
                return image_url
    except Exception:
        return None

    return None


def _generate_concept_image_from_free_api(concept, models_dir, backend_base_url):
    if not concept or not models_dir or not backend_base_url:
        print(f"[Fallback] Skipping free API image: missing params (concept={bool(concept)}, models_dir={bool(models_dir)}, backend_base_url={bool(backend_base_url)})")
        return None

    key = hashlib.md5(json.dumps({"concept": concept, "type": "external"}, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    filename = f"fallback_concept_{key}.jpg"
    filepath = os.path.join(models_dir, filename)
    if os.path.exists(filepath):
        print(f"[Fallback] Found cached free API image: {filename}")
        return f"{backend_base_url}/models/{filename}"

    os.makedirs(models_dir, exist_ok=True)
    print(f"[Fallback] Fetching concept image for '{concept}' from Wikipedia/Wikimedia...")
    source_url = _get_wikipedia_summary_image_url(concept) or _get_wikimedia_search_image_url(concept)
    if not source_url:
        print(f"[Fallback] No free API image source found for '{concept}'")
        return None

    print(f"[Fallback] Attempting to download free API image: {source_url}")
    saved = _download_image(source_url, filepath)
    if not saved:
        print(f"[Fallback] Failed to download free API image")
        return None
    
    print(f"[Fallback] Successfully generated free API image URL")
    return f"{backend_base_url}/models/{filename}"


def build_fallback_payload(concept, models_dir=None, backend_base_url=""):
    shapes = _concept_primitives(concept)
    geometry = _build_geometry_details(concept or "object", shapes)
    image_url = None
    image_source = None
    if models_dir and backend_base_url:
        print(f"[Fallback] Building fallback payload for '{concept}'...")
        image_url = _generate_concept_image_from_free_api(concept or "object", models_dir, backend_base_url)
        if image_url:
            image_source = "free_api"
            print(f"[Fallback] Using free API image source")
        else:
            print(f"[Fallback] Falling back to procedural blueprint")
            image_url = _generate_preview_image(concept or "object", shapes, models_dir, backend_base_url)
            image_source = "procedural_blueprint" if image_url else None

    return {
        "shapes": shapes,
        "geometry_details": geometry,
        "fallback_2d_image_url": image_url,
        "fallback_2d_source": image_source,
    }


def generate_fallback(concept):
    # Backward-compatible return shape list only.
    return _concept_primitives(concept)
