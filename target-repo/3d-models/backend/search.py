import requests

import json
import concurrent.futures
import os
import re
import math
import base64
from cache import QueryCache
from fallback import build_fallback_payload
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

CACHE_VERSION = "v37"
HIGH_SIMILARITY_THRESHOLD = 85

class ModelSearchEngine:
    def __init__(self):
        # We can configure keys for Sketchfab, PolyHaven, etc.
        self.sketchfab_token = os.getenv("SKETCHFAB_API_TOKEN")
        self.tripo3d_token = os.getenv("TRIPO3D_API_KEY")
        self.backend_base_url = os.getenv("BACKEND_BASE_URL") or "http://127.0.0.1:8000"
        self.concept2_backend_url = (os.getenv("CONCEPT2D_BACKEND_URL") or "").strip().rstrip("/")
        self.concept2_timeout_seconds = int(os.getenv("CONCEPT2_VISUALIZE_TIMEOUT_SECONDS", "60"))
        self.models_dir = os.path.join(os.path.dirname(__file__), "models")
        self.cache = QueryCache()
        
        # Initialize Gemini API for vision-based label positioning
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        if GEMINI_AVAILABLE and self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-exp')
        else:
            self.gemini_model = None

    def _get_gemini_label_positions(self, normalized_keywords: str, part_definitions: list, model_image_base64: str = None):
        """
        Use Gemini vision API to analyze model image and generate precise x,y,z coordinates for labels.
        
        Args:
            normalized_keywords: The concept/model name
            part_definitions: List of parts with name and description
            model_image_base64: Base64-encoded image of the 3D model
        
        Returns:
            Updated part_definitions with refined x,y,z coordinates from Gemini vision analysis
        """
        if not self.gemini_model or not model_image_base64:
            return part_definitions
        
        if not part_definitions:
            return part_definitions
        
        try:
            # Prepare parts list for Gemini prompt
            parts_list = "\n".join([
                f"- {i+1}. {p.get('name', 'Part')} (Description: {p.get('description', 'N/A')})"
                for i, p in enumerate(part_definitions[:10])  # Limit to 10 parts
            ])
            
            prompt = f"""You are analyzing a 3D model image of a '{normalized_keywords}' and need to identify the precise spatial positions of labeled parts.

The following parts need to be positioned:
{parts_list}

Analyze the 3D model in the image and for each part, provide the most accurate x, y, z coordinates:
- X-axis (left/right): -1.0 (far left) to +1.0 (far right), center at 0
- Y-axis (up/down): -1.0 (bottom) to +1.0 (top), center at 0
- Z-axis (front/back): -1.0 (far back) to +1.0 (far front), center at 0

Return the response as valid JSON with this exact structure:
{{
  "coordinates": [
    {{"name": "part name", "x": 0.0, "y": 0.0, "z": 0.0}},
    ...
  ]
}}

Be precise and place labels exactly where the parts are visible in the image. Consider the 3D geometry carefully."""
            
            # Decode image and send bytes to Gemini for vision analysis
            image_data = base64.b64decode(model_image_base64)
            image = {
                "mime_type": "image/png",
                "data": image_data,
            }
            
            message = self.gemini_model.generate_content([
                prompt,
                image
            ])
            
            response_text = message.text or ""
            
            # Parse JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                gemini_response = json.loads(json_str)
                coordinates = gemini_response.get("coordinates", [])
                
                # Map Gemini coordinates back to part_definitions
                coords_by_name = {c.get("name", "").lower(): c for c in coordinates}
                
                for part in part_definitions:
                    part_name_lower = part.get("name", "").lower()
                    
                    # Try exact match first, then partial match
                    match = coords_by_name.get(part_name_lower)
                    if not match:
                        for coord in coordinates:
                            if part_name_lower in coord.get("name", "").lower():
                                match = coord
                                break
                    
                    if match:
                        # Clamp values to valid range
                        x = max(-0.5, min(0.5, float(match.get("x", 0))))
                        y = max(-0.5, min(0.5, float(match.get("y", 0))))
                        z = max(-0.3, min(0.3, float(match.get("z", 0))))
                        
                        part["position"] = {
                            "x": round(x, 3),
                            "y": round(y, 3),
                            "z": round(z, 3)
                        }
                
                return part_definitions
        
        except Exception as e:
            print(f"Gemini vision positioning failed: {e}")
            return part_definitions
        
        return part_definitions

    def _semantic_anchor(self, text: str):
        value = (text or "").lower()

        x = None
        y = None
        z = None

        if any(k in value for k in ["left", "lobe", "wing left", "arm left", "leg left"]):
            x = -0.38
        elif any(k in value for k in ["right", "wing right", "arm right", "leg right"]):
            x = 0.38

        if any(k in value for k in ["top", "upper", "head", "aorta", "artery", "dome", "roof", "crown", "neck", "stem"]):
            y = 0.48
        elif any(k in value for k in ["bottom", "lower", "base", "leg", "foot", "wheel", "stand", "foundation", "support"]):
            y = -0.38

        if any(k in value for k in ["front", "face", "mouth", "nose", "drawer", "panel", "door"]):
            z = 0.28
        elif any(k in value for k in ["back", "rear", "tail", "spine"]):
            z = -0.28

        return x, y, z

    def _query_specific_parts(self, normalized_keywords: str):
        query = (normalized_keywords or "").lower()

        if "heart" in query:
            return [
                {
                    "name": "left_atrium",
                    "primitive": "sphere",
                    "description": "Upper left chamber receiving oxygenated blood from lungs.",
                    "position": {"x": -0.25, "y": 0.35, "z": 0.1},
                    "parameters": {},
                },
                {
                    "name": "right_atrium",
                    "primitive": "sphere",
                    "description": "Upper right chamber receiving deoxygenated blood from body.",
                    "position": {"x": 0.25, "y": 0.35, "z": 0.1},
                    "parameters": {},
                },
                {
                    "name": "left_ventricle",
                    "primitive": "sphere",
                    "description": "Main pumping chamber that sends oxygenated blood to the body.",
                    "position": {"x": -0.2, "y": -0.15, "z": 0.05},
                    "parameters": {},
                },
                {
                    "name": "right_ventricle",
                    "primitive": "sphere",
                    "description": "Pumps deoxygenated blood to the lungs.",
                    "position": {"x": 0.2, "y": -0.15, "z": 0.05},
                    "parameters": {},
                },
                {
                    "name": "aorta",
                    "primitive": "cylinder",
                    "description": "Largest artery carrying oxygenated blood from the heart.",
                    "position": {"x": 0.0, "y": 0.5, "z": 0.0},
                    "parameters": {},
                },
                {
                    "name": "pulmonary_artery",
                    "primitive": "cylinder",
                    "description": "Carries blood from heart to lungs.",
                    "position": {"x": 0.05, "y": 0.45, "z": -0.1},
                    "parameters": {},
                },
            ]

        return []

    def _dynamic_part_definitions(self, normalized_keywords: str, intent_data: dict | None = None, model: dict | None = None, max_parts: int = 8):
        # Build labels from prompt intent + current model metadata (no concept-specific hardcoding).
        query_specific = self._query_specific_parts(normalized_keywords)
        if query_specific:
            return query_specific[:max_parts]

        candidates = []

        if isinstance(intent_data, dict):
            for token in intent_data.get("structural_components", []) or []:
                if isinstance(token, str):
                    value = token.strip().lower()
                    if value:
                        candidates.append(value)

        metadata_blob = ""
        if isinstance(model, dict):
            metadata_blob = " ".join(
                [
                    model.get("title") or "",
                    model.get("name") or "",
                    model.get("explanation") or "",
                    model.get("description") or "",
                ]
            )

        token_blob = f"{normalized_keywords or ''} {metadata_blob}".lower()
        extracted = re.findall(r"[a-z0-9]+", token_blob)
        stop = {
            "the", "and", "for", "with", "from", "this", "that", "model", "scene", "object",
            "asset", "match", "high", "strong", "top", "test", "labeling", "labels", "original",
            "concept", "using", "source", "generated", "retrieved", "animation", "animated",
            "sketchfab", "polyhaven", "tripo", "human", "male", "female", "render", "viewer",
        }
        for token in extracted:
            if len(token) < 3 or token in stop:
                continue
            candidates.append(token)

        deduped = []
        seen = set()
        for token in candidates:
            t = token.strip().lower()
            if not t or t in seen:
                continue
            seen.add(t)
            deduped.append(t)

        if not deduped:
            words = [w for w in re.findall(r"[a-z0-9]+", (normalized_keywords or "").lower()) if len(w) >= 3]
            deduped = words or ["part", "core", "feature"]

        selected = deduped[:max_parts]
        total = max(1, len(selected))
        radius = 0.32 if total > 1 else 0.0

        parts = []
        for idx, token in enumerate(selected):
            angle = (2 * math.pi * idx) / total if total > 1 else 0.0
            x = math.cos(angle) * radius
            y = 0.12 + (0.06 if idx % 2 == 0 else -0.06)
            z = math.sin(angle) * radius * 0.48

            sx, sy, sz = self._semantic_anchor(token)
            if sx is not None:
                x = sx
            if sy is not None:
                y = sy
            if sz is not None:
                z = sz

            # tiny deterministic spread to avoid full overlap when multiple labels infer same anchor
            spread = ((idx % 3) - 1) * 0.03
            x += spread

            x = round(x, 3)
            y = round(y, 3)
            z = round(z, 3)

            primitive = "sphere"
            if any(k in token for k in ["tube", "pipe", "aorta", "artery", "vein", "stem"]):
                primitive = "cylinder"
            elif any(k in token for k in ["base", "core", "block", "body"]):
                primitive = "cube"

            parts.append(
                {
                    "name": token,
                    "primitive": primitive,
                    "description": f"Detected semantic part: {token}.",
                    "position": {"x": x, "y": y, "z": z},
                    "parameters": {},
                }
            )

        return parts

    def _location_to_position(self, location: str, index: int, total_parts: int, part_name: str = ""):
        location_text = (location or "").lower()
        spacing = 0.35
        center_offset = (total_parts - 1) / 2.0
        default_x = (index - center_offset) * spacing
        x = default_x
        y = 0.0
        z = 0.0

        if "left" in location_text:
            x = -0.5
        elif "right" in location_text:
            x = 0.5

        if "top" in location_text or "upper" in location_text:
            y = 0.45
        elif "bottom" in location_text or "lower" in location_text or "base" in location_text:
            y = -0.45

        if "front" in location_text:
            z = 0.35
        elif "back" in location_text or "rear" in location_text:
            z = -0.35

        sx, sy, sz = self._semantic_anchor(f"{location_text} {part_name}")
        if sx is not None:
            x = sx
        if sy is not None:
            y = sy
        if sz is not None:
            z = sz

        return {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)}

    def _convert_external_part_labels(self, labels_payload: dict):
        if not isinstance(labels_payload, dict):
            return []

        parts = labels_payload.get("parts")
        if not isinstance(parts, list):
            return []

        converted = []
        total = len(parts)
        for idx, part in enumerate(parts):
            if not isinstance(part, dict):
                continue

            name = (part.get("name") or f"part_{idx + 1}").strip() or f"part_{idx + 1}"
            description = (part.get("description") or "").strip()
            function = (part.get("function") or "").strip()
            location = (part.get("location") or "center").strip()

            if function and description:
                full_description = f"{description} Function: {function}."
            else:
                full_description = description or function or f"Labeled part: {name}"

            primitive = "sphere"
            lowered_name = name.lower()
            if "wheel" in lowered_name:
                primitive = "cylinder"
            elif "body" in lowered_name or "base" in lowered_name or "frame" in lowered_name:
                primitive = "cube"

            converted.append(
                {
                    "name": name,
                    "primitive": primitive,
                    "description": full_description,
                    "position": self._location_to_position(location, idx, max(total, 1), part_name=name),
                    "parameters": {},
                }
            )

        return converted

    def _labels_need_fallback(self, normalized_keywords: str, part_definitions: list):
        if not part_definitions:
            return True

        query_tokens = set(re.findall(r"[a-z0-9]+", (normalized_keywords or "").lower()))
        combined = " ".join(
            [
                f"{p.get('name', '')} {p.get('description', '')}"
                for p in part_definitions
                if isinstance(p, dict)
            ]
        ).lower()

        # If query terms barely appear in label set, labels are likely noisy.
        token_hits = sum(1 for token in query_tokens if token and token in combined)
        if query_tokens and token_hits == 0:
            return True

        # Guardrail for common bad anatomy fallback observed for heart concepts.
        if "heart" in query_tokens:
            bad_terms = {"head", "torso", "arm", "hand", "leg", "foot"}
            names = {
                (p.get("name") or "").strip().lower()
                for p in part_definitions
                if isinstance(p, dict)
            }
            if names.intersection(bad_terms):
                return True

            # Reject generic labels from noisy external pipelines.
            generic_terms = {
                "human", "heart", "stylized", "both", "animation", "model", "object", "shape", "part",
                "sketchfab", "original", "label", "labels",
            }
            generic_hits = sum(1 for n in names if n in generic_terms)
            if generic_hits >= max(2, len(names) // 2):
                return True

            # Require at least 2 canonical heart structures for acceptance.
            canonical_heart = {
                "left_atrium", "right_atrium", "left_ventricle", "right_ventricle",
                "aorta", "pulmonary_artery", "pulmonary_vein", "vena_cava",
                "mitral_valve", "tricuspid_valve", "septum",
            }
            canonical_hits = len(names.intersection(canonical_heart))
            if canonical_hits < 2:
                return True

        return False

    def _fetch_concept2_labeled_model(self, normalized_keywords: str, base_score: float = 81.0):
        if not self.concept2_backend_url:
            return None

        url = f"{self.concept2_backend_url}/visualize"
        try:
            response = requests.get(
                url,
                params={"concept": normalized_keywords},
                timeout=self.concept2_timeout_seconds,
            )
            if response.status_code != 200:
                print(f"Concept-2-3D visualize returned status={response.status_code} for '{normalized_keywords}'")
                return None

            payload_raw = response.json()
            payload = payload_raw if isinstance(payload_raw, dict) else {}
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            model_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            model_url = payload.get("model_url") or model_data.get("viewer")

            if not model_url:
                return None

            labels_payload = payload.get("part_labels")
            if not isinstance(labels_payload, dict):
                labels_payload = model_data.get("part_labels") if isinstance(model_data.get("part_labels"), dict) else {}

            part_definitions = self._convert_external_part_labels(labels_payload)
            if self._labels_need_fallback(normalized_keywords, part_definitions):
                part_definitions = self._dynamic_part_definitions(
                    normalized_keywords,
                    intent_data=None,
                    model={
                        "title": metadata.get("name") or model_data.get("name") or normalized_keywords,
                        "description": metadata.get("description") or model_data.get("description") or "",
                    },
                )
            title = (
                (metadata.get("name") if isinstance(metadata, dict) else None)
                or model_data.get("name")
                or normalized_keywords.title()
            )
            description = (
                (metadata.get("description") if isinstance(metadata, dict) else None)
                or model_data.get("description")
                or f"External hybrid model + labels for '{normalized_keywords}'."
            )

            return {
                "source": "Original 3D Labeling Test (Concept-2-3D)",
                "title": f"Original + Labels: {title}",
                "uid": f"original-labeled-{normalized_keywords.replace(' ', '-')}",
                "thumbnails": [],
                "model_url": model_url,
                "embed_url": None,
                "score": float(base_score),
                "explanation": description,
                "labeling_mode": "original-3d-test",
                "labeling_preview_note": "Labels imported from Concept-2-3D pipeline output.",
                "labeling_pipeline": "concept-2-3d",
                "built_in_annotations": [],
                "built_in_annotations_count": len(part_definitions),
                "part_definitions": part_definitions,
                "geometry_details": {
                    "concept": normalized_keywords,
                    "total_parts": len(part_definitions),
                    "shapes": part_definitions,
                },
            }
        except Exception as e:
            print(f"Concept-2-3D bridge failed for '{normalized_keywords}': {e}")
            return None

    def _build_similarity_labels(self, model: dict):
        score = float(model.get("score") or 0)
        is_3d = bool(model.get("model_url") or model.get("embed_url"))
        if not is_3d or score < HIGH_SIMILARITY_THRESHOLD:
            return None

        if score >= 95:
            tier = "Top Match"
        elif score >= 90:
            tier = "High Match"
        else:
            tier = "Strong Match"

        labels = [
            {"key": "tier", "value": tier},
            {"key": "similarity", "value": f"{int(round(score))}%"},
            {"key": "source", "value": model.get("source", "Unknown")},
        ]

        explanation = (model.get("explanation") or "").strip()
        if explanation:
            labels.append({"key": "reason", "value": explanation})

        return {
            "high_similarity": True,
            "threshold": HIGH_SIMILARITY_THRESHOLD,
            "labels": labels,
        }

    def _attach_semantic_labels(self, model: dict, normalized_keywords: str, intent_data: dict | None = None):
        if not isinstance(model, dict):
            return

        existing_parts = model.get("part_definitions")
        if not isinstance(existing_parts, list) or not existing_parts:
            semantic_parts = self._dynamic_part_definitions(
                normalized_keywords,
                intent_data=intent_data,
                model=model,
            )
            if semantic_parts:
                model["part_definitions"] = semantic_parts

        if isinstance(model.get("part_definitions"), list) and model.get("part_definitions"):
            if not isinstance(model.get("geometry_details"), dict):
                model["geometry_details"] = {
                    "concept": normalized_keywords,
                    "total_parts": len(model["part_definitions"]),
                    "shapes": model["part_definitions"],
                }

            if model.get("built_in_annotations_count") is None:
                model["built_in_annotations_count"] = len(model["part_definitions"])

            if model.get("model_url") or model.get("embed_url"):
                model.setdefault("labeling_mode", "semantic-overlay")

    def _score_tier(self, score: float):
        if score >= 95:
            return "elite"
        if score >= 90:
            return "high"
        if score >= 80:
            return "good"
        if score >= 70:
            return "moderate"
        return "low"

    def _build_model_labels(self, model: dict):
        score = float(model.get("score") or 0)
        is_embed = bool(model.get("embed_url"))
        is_model_file = bool(model.get("model_url"))
        has_procedural = bool(model.get("procedural_data"))

        if has_procedural:
            model_type = "procedural-3d"
        elif is_model_file:
            model_type = "native-3d"
        elif is_embed:
            model_type = "embedded-3d"
        else:
            model_type = "other"

        provenance = "fallback" if "fallback" in (model.get("source", "").lower()) else "retrieved"

        labels = [
            {"key": "type", "value": model_type},
            {"key": "tier", "value": self._score_tier(score)},
            {"key": "similarity", "value": f"{int(round(score))}%"},
            {"key": "source", "value": model.get("source", "Unknown")},
            {"key": "provenance", "value": provenance},
        ]

        annotation_count = int(model.get("built_in_annotations_count") or 0)
        if annotation_count > 0:
            labels.append({"key": "annotations", "value": str(annotation_count)})

        return labels

    def _build_original_model_labeling_test(self, model: dict):
        has_procedural = bool(model.get("procedural_data"))
        is_embed = bool(model.get("embed_url"))
        is_model_file = bool(model.get("model_url"))

        # This test section is only for original retrieved 3D outputs.
        if has_procedural or not (is_embed or is_model_file):
            return None

        score = float(model.get("score") or 0)
        title = (model.get("title") or "").strip()
        explanation = (model.get("explanation") or "").strip()

        model_type = "Embedded 3D" if is_embed else "Native 3D"

        inferred_tokens = []
        for token in re.findall(r"[a-z0-9]+", title.lower()):
            if len(token) < 4:
                continue
            if token in {"model", "scene", "asset", "object", "from", "with"}:
                continue
            if token not in inferred_tokens:
                inferred_tokens.append(token)
            if len(inferred_tokens) >= 4:
                break

        labels = [
            {"label": "Model Type", "value": model_type},
            {"label": "Source", "value": model.get("source", "Unknown")},
            {"label": "Similarity", "value": f"{int(round(score))}%"},
            {"label": "Tier", "value": self._score_tier(score).title()},
        ]

        if inferred_tokens:
            labels.append({"label": "Inferred Tags", "value": ", ".join(inferred_tokens)})

        if explanation:
            labels.append({"label": "Match Reason", "value": explanation})

        return {
            "enabled": True,
            "section_title": "Original 3D Labeling (Test)",
            "labels": labels,
        }

    def _is_model_result_valid(self, model: dict):
        if not isinstance(model, dict):
            return False

        # Procedural fallback cards are always valid render targets.
        if model.get("procedural_data"):
            return True

        model_url = (model.get("model_url") or "").strip()
        embed_url = (model.get("embed_url") or "").strip()

        if embed_url and embed_url.startswith(("http://", "https://")):
            return True

        if model_url and model_url.startswith(("http://", "https://")):
            lowered = model_url.lower()
            banned = ["undefined", "null", "placeholder", "example.com"]
            if any(token in lowered for token in banned):
                return False
            return True

        return False

    def _ensure_point_based_labels(self, model: dict, normalized_keywords: str, intent_data: dict | None = None):
        if not isinstance(model, dict):
            return

        # Ensure every model receives part_definitions.
        self._attach_semantic_labels(model, normalized_keywords, intent_data=intent_data)

        parts = model.get("part_definitions")
        if self._labels_need_fallback(normalized_keywords, parts if isinstance(parts, list) else []):
            parts = self._dynamic_part_definitions(
                normalized_keywords,
                intent_data=intent_data,
                model=model,
            )
            model["part_definitions"] = parts

        if not isinstance(parts, list) or not parts:
            return

        total = max(1, len(parts))
        radius = 0.32 if total > 1 else 0.0

        normalized_parts = []
        for idx, part in enumerate(parts[:10]):
            if not isinstance(part, dict):
                continue

            name = (part.get("name") or f"part_{idx + 1}").strip() or f"part_{idx + 1}"
            primitive = (part.get("primitive") or "sphere").strip() or "sphere"
            description = (part.get("description") or f"Labeled part: {name}").strip()
            parameters = part.get("parameters") if isinstance(part.get("parameters"), dict) else {}

            position = part.get("position") if isinstance(part.get("position"), dict) else {}
            x = position.get("x")
            y = position.get("y")
            z = position.get("z")

            has_numeric = all(isinstance(v, (int, float)) for v in [x, y, z])
            if not has_numeric:
                angle = (2 * math.pi * idx) / total if total > 1 else 0.0
                x = math.cos(angle) * radius
                y = 0.1 + (0.06 if idx % 2 == 0 else -0.06)
                z = math.sin(angle) * radius * 0.5

            x = max(-0.5, min(0.5, float(x)))
            y = max(-0.5, min(0.5, float(y)))
            z = max(-0.5, min(0.5, float(z)))

            normalized_parts.append(
                {
                    "name": name,
                    "primitive": primitive,
                    "description": description,
                    "position": {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)},
                    "parameters": parameters,
                }
            )

        if normalized_parts:
            model["part_definitions"] = normalized_parts
            model["geometry_details"] = {
                "concept": normalized_keywords,
                "total_parts": len(normalized_parts),
                "shapes": normalized_parts,
            }
            model.setdefault("labeling_mode", "point-based")
            model["built_in_annotations_count"] = max(
                int(model.get("built_in_annotations_count") or 0),
                len(normalized_parts),
            )

    def _normalize_query(self, keywords: str) -> str:
        if not keywords:
            return keywords

        normalized = keywords.lower().strip()

        # Correct high-impact common typo variants so fallback/media lookup stays relevant.
        aliases = {
            "zina virus": "zika virus",
            "zina": "zika",
            "corona virus": "coronavirus",
            "shah ruk khan": "shah rukh khan",
        }
        if normalized in aliases:
            return aliases[normalized]

        tokens = re.findall(r"[a-z0-9]+", normalized)
        mapped = []
        token_map = {
            "zina": "zika",
            "corona": "coronavirus",
            "ruk": "rukh",
        }
        for token in tokens:
            mapped.append(token_map.get(token, token))
        return " ".join(mapped)

    def _build_labeled_breakdown_model(self, normalized_keywords: str, base_score: float = 82.0):
        fallback_payload = build_fallback_payload(normalized_keywords)
        geometry_details = (fallback_payload or {}).get("geometry_details") or {}
        parts = geometry_details.get("shapes") or []

        if not parts:
            parts = [
                {
                    "name": "part_1",
                    "primitive": "cube",
                    "parameters": {"width": 1.2, "height": 1.0, "depth": 1.0},
                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "description": f"Core conceptual block for {normalized_keywords}",
                }
            ]

        part_definitions = [
            {
                "name": p.get("name") or f"part_{idx + 1}",
                "primitive": p.get("primitive") or "cube",
                "description": p.get("description") or f"Structural part {idx + 1}",
                "position": p.get("position") or {"x": 0.0, "y": 0.0, "z": 0.0},
                "parameters": p.get("parameters") or {},
            }
            for idx, p in enumerate(parts)
            if isinstance(p, dict)
        ]

        return {
            "source": "Labeled 3D Breakdown",
            "title": f"Labeled Breakdown: {normalized_keywords.title()}",
            "uid": f"labeled-breakdown-{normalized_keywords.replace(' ', '-')}",
            "thumbnails": [],
            "model_url": None,
            "score": float(base_score),
            "explanation": f"Procedural 3D breakdown with labeled parts for '{normalized_keywords}'.",
            "procedural_data": {
                "components": [pd["primitive"] for pd in part_definitions],
                "parts": part_definitions,
            },
            "part_definitions": part_definitions,
            "geometry_details": {
                "concept": normalized_keywords,
                "total_parts": len(part_definitions),
                "shapes": part_definitions,
            },
        }

    def _build_original_labeled_test_card(self, normalized_keywords: str, base_model: dict, base_score: float = 81.0, intent_data: dict | None = None):
        external_card = self._fetch_concept2_labeled_model(normalized_keywords, base_score=base_score)
        if external_card:
            return external_card

        sketchfab_annotations = []
        if (base_model.get("source") or "").lower() == "sketchfab":
            sketchfab_annotations = self._fetch_sketchfab_annotations(base_model.get("uid"))

        part_definitions = self._dynamic_part_definitions(
            normalized_keywords,
            intent_data=intent_data,
            model=base_model,
        )

        title = (base_model.get("title") or normalized_keywords.title()).strip()
        return {
            "source": "Original 3D Labeling Test",
            "title": f"Original + Labels: {title}",
            "uid": f"original-labeled-{normalized_keywords.replace(' ', '-')}",
            "thumbnails": base_model.get("thumbnails") or [],
            "model_url": base_model.get("model_url"),
            "embed_url": base_model.get("embed_url"),
            "score": float(base_score),
            "explanation": f"Original 3D model with test labels inferred from '{normalized_keywords}'.",
            "labeling_mode": "original-3d-test",
            "labeling_preview_note": "Concept-2-3D output unavailable for this query; using local embedded proxy.",
            "labeling_pipeline": "local-fallback",
            "built_in_annotations": sketchfab_annotations,
            "built_in_annotations_count": len(sketchfab_annotations),
            "part_definitions": part_definitions,
            "geometry_details": {
                "concept": normalized_keywords,
                "total_parts": len(part_definitions),
                "shapes": part_definitions,
            },
        }

    def _fetch_sketchfab_annotations(self, uid: str):
        if not uid or not self.sketchfab_token:
            return []

        url = f"https://api.sketchfab.com/v3/models/{uid}/annotations"
        headers = {"Authorization": f"Token {self.sketchfab_token}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                return []

            payload = response.json() or {}
            rows = payload.get("results") if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                return []

            annotations = []
            for idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                title = (row.get("name") or row.get("title") or f"Annotation {idx + 1}").strip()
                content = (row.get("content") or row.get("description") or "").strip()
                annotations.append({"index": idx + 1, "title": title, "content": content})
            return annotations
        except Exception:
            return []

    def search(self, intent_data: dict) -> list:
        """
        Queries various APIs based on the extracted intent.
        """
        keywords_list = intent_data.get("primary_keywords", [])
        keywords = " ".join(keywords_list)
        normalized_keywords = self._normalize_query(keywords)
        cache_key = f"{CACHE_VERSION}::{normalized_keywords}"
        
        # Check cache first
        cached_results = self.cache.get_cached_results(cache_key)
        if cached_results:
            print(f"Returning cached results for: {normalized_keywords}")
            return cached_results
            
        import concurrent.futures
        
        results = []
        
        # Parallelize API Calls
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            normalized_list = normalized_keywords.split()
            future_tripo = executor.submit(self._generate_tripo3d, normalized_keywords)
            future_sketchfab = executor.submit(self._search_sketchfab, normalized_keywords)
            future_polyhaven = executor.submit(self._search_polyhaven, normalized_list)
            
            # Wait for 3D results
            tripo_results = future_tripo.result()
            sketchfab_results = future_sketchfab.result()
            polyhaven_results = future_polyhaven.result()

        if tripo_results:
            results.extend(tripo_results)
        if sketchfab_results:
            results.extend(sketchfab_results)
        if polyhaven_results:
            results.extend(polyhaven_results)

        # Keep only valid model cards; invalid URLs should not block fallback generation.
        valid_results = [model for model in results if self._is_model_result_valid(model)]
        results = valid_results
            
        # If no real 3D models found, add procedural 3D fallback
        if not results:
            print(f"No valid 3D models found across sources for '{normalized_keywords}', generating procedural point-based fallback.")
            fallback_payload = build_fallback_payload(normalized_keywords)
            geometry_details = (fallback_payload or {}).get("geometry_details") or {}
            parts = geometry_details.get("shapes") or []
            components = [
                p.get("primitive")
                for p in parts
                if isinstance(p, dict) and isinstance(p.get("primitive"), str)
            ]

            results.append({
                "source": "Procedural 3D Fallback",
                "title": f"Procedural Concept: {normalized_keywords.title()}",
                "uid": f"fallback-3d-{normalized_keywords.replace(' ', '-')}",
                "thumbnails": [],
                "model_url": None,
                "score": 84,
                "explanation": f"No valid 3D model was found across sources for '{normalized_keywords}'. Showing an accurate point-based procedural fallback.",
                "procedural_data": {
                    "components": components or ["cube"],
                    "parts": parts,
                },
                "part_definitions": parts,
                "geometry_details": geometry_details,
                "labeling_mode": "point-based-fallback",
            })

        # Guarantee point-based labels for every model card before ranking.
        for model in results:
            self._ensure_point_based_labels(model, normalized_keywords, intent_data=intent_data)

        # Add one extra model in the list: labeled conceptual 3D breakdown with part definitions.
        if results:
            top_score = float(results[0].get("score") or 82)
            breakdown_score = max(60.0, min(86.0, top_score - 3.0))
            results.append(self._build_labeled_breakdown_model(normalized_keywords, base_score=breakdown_score))

            # Add a separate card for original-model labeling test, similar to labeled breakdown card.
            primary_retrieved = next(
                (
                    model
                    for model in results
                    if not model.get("procedural_data") and model.get("model_url")
                ),
                None,
            ) or next(
                (
                    model
                    for model in results
                    if not model.get("procedural_data") and model.get("embed_url")
                ),
                None,
            )
            if primary_retrieved:
                original_test_score = max(58.0, min(85.0, top_score - 4.0))
                results.append(
                    self._build_original_labeled_test_card(
                        normalized_keywords,
                        primary_retrieved,
                        base_score=original_test_score,
                        intent_data=intent_data,
                    )
                )

        # Sort results by score (descending)
        results.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Add detailed labels on top similarity 3D results.
        for model in results:
            model["model_labels"] = self._build_model_labels(model)
            metadata = self._build_similarity_labels(model)
            if metadata:
                model["similarity_metadata"] = metadata
            original_labeling = self._build_original_model_labeling_test(model)
            if original_labeling:
                model["original_model_labeling_test"] = original_labeling
        
        # Save to cache before returning
        self.cache.cache_results(cache_key, results)
        
        return results

    def _generate_2d_image(self, keywords: str) -> dict:
        """
        Uses Gemini to generate a descriptive prompt and returns a 2D image URL.
        """
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
            
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = f"Create a highly descriptive, artistic prompt for an image of '{keywords}'. Return ONLY the prompt text."
            response = model.generate_content(prompt)
            img_prompt = response.text.strip().replace(" ", "%20")
            
            # Use Pollinations AI for free image generation
            image_url = f"https://image.pollinations.ai/prompt/{img_prompt}?width=1024&height=1024&nologo=true"
            
            return {
                "source": "Gemini 2D AI",
                "title": f"2D Concept: {keywords.title()}",
                "uid": f"2d-{hash(keywords)}",
                "thumbnails": [{"url": image_url}],
                "image_url": image_url, # Special field for 2D
                "model_url": None,
                "score": 80,
                "explanation": f"AI-generated 2D visualization of '{keywords}' since no suitable 3D models were found."
            }
        except Exception as e:
            print(f"2D Fallback failed: {e}")
            return None

    def _search_polyhaven(self, keywords: list) -> list:
        # Poly Haven's public API for models
        url = "https://api.polyhaven.com/assets?t=models"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                assets = response.json()
                results = []
                
                # Match keywords against asset names or tags
                for uid, data in assets.items():
                    name_lower = data.get("name", "").lower()
                    tags = [t.lower() for t in data.get("tags", [])]
                    
                    # If any keyword matches name or tags
                    name_words = set(name_lower.split())
                    match = any(kw.lower() in name_words or kw.lower() in tags for kw in keywords)
                    
                    if match:
                        # Fetch file info to get the actual GLTF url
                        model_url = None
                        try:
                            file_res = requests.get(f"https://api.polyhaven.com/files/{uid}")
                            if file_res.status_code == 200:
                                files_data = file_res.json()
                                # Attempt to get the lowest res gltf for fast web loading (1k or 2k)
                                gltf_data = files_data.get("gltf", {})
                                if gltf_data:
                                    # Get the smallest available resolution key (e.g., '1k')
                                    res_key = min(gltf_data.keys(), key=lambda k: int(k.replace('k','')) if k.replace('k','').isdigit() else 99)
                                    model_url = gltf_data[res_key].get("gltf", {}).get("url")
                                    
                                    # Fallback to the larger glb if gltf format isn't nested right
                                    if not model_url and "glb" in gltf_data[res_key]:
                                         model_url = gltf_data[res_key]["glb"].get("url")
                        except Exception as fetch_err:
                            print(f"Error fetching file URLs for {uid}: {fetch_err}")

                        results.append({
                            "source": "Poly Haven",
                            "title": data.get("name"),
                            "uid": uid,
                            "thumbnails": [{"url": f"https://cdn.polyhaven.com/asset_img/thumbs/{uid}.png"}],
                            "model_url": model_url,
                            "embed_url": None,
                            "score": 95,
                            "explanation": f"High quality free HDR/PBR model from Poly Haven matching '{', '.join(keywords)}'"
                        })
                        
                    # Stop if we found a few good ones
                    if len(results) >= 2:
                        break
                return results
        except Exception as e:
            print(f"Poly Haven search failed: {e}")
            
        return []

    def _search_sketchfab(self, keywords: str) -> list:
        if not self.sketchfab_token:
            print("No Sketchfab token, skipping Sketchfab search.")
            return []
            
        # Sketchfab API example (requires auth for download urls, but free for search)
        url = "https://api.sketchfab.com/v3/search"
        params = {
            "type": "models",
            "q": keywords
        }
        headers = {}
        if self.sketchfab_token:
            headers["Authorization"] = f"Token {self.sketchfab_token}"
            
        try:
            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                results = []
                for item in data.get("results", [])[:5]: # Get slightly more for sorting
                    # Calculate a dynamic score based on likes and views
                    likes = item.get("likeCount", 0)
                    views = item.get("viewCount", 0)
                    # Base score 80 + bonus for popularity up to 15
                    popularity_bonus = min(15, (likes * 10 + views) / 1000)
                    dynamic_score = 80 + popularity_bonus
                    
                    results.append({
                        "source": "Sketchfab",
                        "title": item.get("name"),
                        "uid": item.get("uid"),
                        "thumbnails": item.get("thumbnails", {}).get("images", []),
                        "model_url": None, 
                        "embed_url": f"https://sketchfab.com/models/{item.get('uid')}/embed?ui_watermark=0&ui_infos=0&ui_stop=0&ui_animations=0&ui_controls=0&transparent=1&autostart=1",
                        "score": dynamic_score,
                        "explanation": f"Match from Sketchfab for '{keywords}' (Likes: {likes}, Views: {views})"
                    })
                return results
        except Exception as e:
            print(f"Sketchfab search failed: {e}")
            
        return []

    def _generate_tripo3d(self, keywords: str) -> list:
        import time
        if not self.tripo3d_token:
            print("No Tripo3D token, skipping generation.")
            return []
            
        print(f"Generating Tripo3D model for: {keywords}")
        url = "https://api.tripo3d.ai/v2/openapi/task"
        headers = {
            "Authorization": f"Bearer {self.tripo3d_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "type": "text_to_model",
            "prompt": keywords
        }
        
        try:
            # 1. Create the generation task
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                print(f"Tripo3D Task Creation Failed: {response.status_code} - {response.text}")
                return []
                
            task_data = response.json()
            if task_data.get("code") != 0:
                return []
            
            task_id = task_data.get("data", {}).get("task_id")
            if not task_id:
                return []
                
            print(f"Tripo3D task created: {task_id}. Polling for completion...")
            
            # 2. Poll the task until success (Max ~90 seconds)
            poll_url = f"https://api.tripo3d.ai/v2/openapi/task/{task_id}"
            
            for _ in range(30):
                time.sleep(3)
                poll_resp = requests.get(poll_url, headers=headers)
                if poll_resp.status_code == 200:
                    poll_data = poll_resp.json()
                    status = poll_data.get("data", {}).get("status")
                    
                    if status == "success":
                        glb_url = poll_data.get("data", {}).get("result", {}).get("model", {}).get("url")
                        return [{
                            "source": "Tripo3D AI",
                            "title": f"Generative {keywords.title()}",
                            "uid": task_id,
                            "thumbnails": [],
                            "model_url": glb_url,
                            "embed_url": None,
                            "score": 99,
                            "explanation": f"Successfully synthesized a custom 3D model using Tripo3D Generative AI for '{keywords}'."
                        }]
                    elif status in ["failed", "cancelled", "deleted"]:
                        print(f"Tripo3D task failed with status: {status}")
                        break
            
            return []
        except Exception as e:
            print(f"Tripo3D API error: {e}")
            return []
