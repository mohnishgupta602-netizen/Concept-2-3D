import argparse
import json
import os
import time
from typing import Dict, List

import requests

from category_index import CATEGORY_SEED_TERMS, get_seed_terms_for_query


def quality_score(item: dict) -> float:
    likes = float(item.get("likeCount") or 0)
    views = float(item.get("viewCount") or 0)
    vertices = float(item.get("vertexCount") or 0)
    comments = float(item.get("commentCount") or 0)

    text_blob = " ".join(
        [
            str(item.get("name") or ""),
            str(item.get("description") or ""),
            " ".join([t.get("name", "") for t in (item.get("tags") or []) if isinstance(t, dict)]),
        ]
    ).lower()

    realism_terms = ["realistic", "pbr", "photogrammetry", "scan", "anatomy", "high poly", "hd"]
    stylized_terms = ["cartoon", "stylized", "anime", "lowpoly", "low-poly", "toon"]

    realism_bonus = sum(1 for t in realism_terms if t in text_blob) * 4.0
    stylized_penalty = sum(1 for t in stylized_terms if t in text_blob) * 4.5

    return min(100.0, 55.0 + (likes / 25.0) + (views / 2500.0) + (vertices / 200000.0) + (comments / 10.0) + realism_bonus - stylized_penalty)


def fetch_sketchfab_models(query: str, token: str, per_query_limit: int = 120, timeout: int = 20) -> List[dict]:
    url = "https://api.sketchfab.com/v3/search"
    headers = {}
    if token:
        headers["Authorization"] = f"Token {token}"

    params = {
        "type": "models",
        "q": query,
        "count": 24,
    }

    rows: List[dict] = []
    next_url = url
    page = 0

    while next_url and len(rows) < per_query_limit and page < 8:
        page += 1
        response = requests.get(next_url, params=params if next_url == url else None, headers=headers, timeout=timeout)
        if response.status_code != 200:
            break

        payload = response.json() or {}
        results = payload.get("results") if isinstance(payload, dict) else []
        if not isinstance(results, list):
            break

        rows.extend(results)
        next_url = payload.get("next")
        params = None
        time.sleep(0.08)

    return rows[:per_query_limit]


def build_index(target_count: int = 2500, per_query_limit: int = 90):
    token = (os.getenv("SKETCHFAB_API_TOKEN") or "").strip()

    term_category_pairs = []
    for category, category_terms in CATEGORY_SEED_TERMS.items():
        for term in get_seed_terms_for_query(" ".join(category_terms[:2]), max_terms=16):
            term_category_pairs.append((term, category))
        for term in category_terms:
            term_category_pairs.append((term, category))

    # Deduplicate search terms while preserving dominant category mapping.
    deduped_terms = []
    seen = set()
    for term, category in term_category_pairs:
        key = " ".join(term.strip().lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped_terms.append((term, category))

    by_uid: Dict[str, dict] = {}
    print(f"Collecting seed models from {len(deduped_terms)} category terms...")

    for idx, item in enumerate(deduped_terms, start=1):
        term, category = item
        try:
            items = fetch_sketchfab_models(term, token=token, per_query_limit=per_query_limit)
        except Exception as exc:
            print(f"[{idx}/{len(deduped_terms)}] term='{term}' failed: {exc}")
            continue

        for item in items:
            uid = item.get("uid")
            if not uid:
                continue

            tags = [t.get("name", "") for t in (item.get("tags") or []) if isinstance(t, dict)]
            row = {
                "uid": uid,
                "title": item.get("name") or "Untitled",
                "description": item.get("description") or "",
                "thumbnails": (item.get("thumbnails", {}) or {}).get("images", []),
                "embed_url": f"https://sketchfab.com/models/{uid}/embed?ui_watermark=0&ui_infos=0&ui_stop=0&ui_animations=0&ui_controls=0&transparent=1&autostart=1",
                "model_url": None,
                "source": "Sketchfab Category Index",
                "category": category,
                "tags": tags,
                "query_term": term,
                "likeCount": item.get("likeCount", 0),
                "viewCount": item.get("viewCount", 0),
                "commentCount": item.get("commentCount", 0),
                "vertexCount": item.get("vertexCount", 0),
                "faceCount": item.get("faceCount", 0),
                "animationCount": item.get("animationCount", 0),
            }
            row["quality_score"] = round(quality_score(item), 3)

            old = by_uid.get(uid)
            if not old or row["quality_score"] > old.get("quality_score", 0):
                by_uid[uid] = row

        print(f"[{idx}/{len(deduped_terms)}] term='{term}' -> total unique: {len(by_uid)}")

        if len(by_uid) >= target_count:
            break

    rows = sorted(by_uid.values(), key=lambda r: r.get("quality_score", 0), reverse=True)[:target_count]

    models_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(models_dir, exist_ok=True)
    output_path = os.path.join(models_dir, "high_probability_model_index.json")

    payload = {
        "version": 1,
        "size": len(rows),
        "generated_at": int(time.time()),
        "source": "sketchfab-category-index",
        "rows": rows,
    }

    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=True)

    print(f"Saved {len(rows)} indexed models to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Build high-probability category model index for fallback retrieval.")
    parser.add_argument("--target", type=int, default=2500, help="Total models to keep in the index")
    parser.add_argument("--per-query", type=int, default=90, help="Max models fetched per term")
    args = parser.parse_args()

    build_index(target_count=max(200, args.target), per_query_limit=max(24, args.per_query))


if __name__ == "__main__":
    main()
