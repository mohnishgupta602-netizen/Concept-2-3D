"""
AI-powered 3D model part labeling module.
Uses Gemini API to analyze 3D models and label individual parts.
"""

import os
import json
import time
import requests
from typing import Optional, Dict, List
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

_last_request_time = 0
MIN_REQUEST_INTERVAL = 1.0


def _gemini_request(prompt: str, temperature: float = 0.2, max_tokens: int = 2048, max_retries: int = 3) -> Optional[str]:
    """Make a request to Gemini API with rate limiting."""
    global _last_request_time
    
    if not GEMINI_API_KEY:
        return None
    
    elapsed = time.time() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    
    url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
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
                url, headers=headers, json=payload,
                params={"key": GEMINI_API_KEY}, timeout=30
            )
            
            if response.status_code == 429:
                retry_delay = (2 ** attempt) + 1
                time.sleep(retry_delay)
                continue
            
            response.raise_for_status()
            data = response.json()
            
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep((2 ** attempt) + 1)
            else:
                print(f"[LabelAI] Request failed: {e}")
    
    return None


def generate_part_labels(concept: str, model_name: str, model_description: str = "") -> Dict[str, List[str]]:
    """
    Generate AI-powered part labels for a 3D model based on concept and metadata.
    Returns a dict with 'parts' list containing {name, description, function} objects.
    """
    prompt = f"""Analyze this 3D model and identify its main parts/components.

Model Concept: "{concept}"
Model Name: "{model_name}"
Model Description: "{model_description[:200]}"

Provide a JSON object with:
{{
  "parts": [
    {{
      "name": "Part name (e.g., 'wheel', 'door', 'handle')",
      "description": "Brief description of this part",
      "function": "What this part does/its purpose",
      "location": "Where on the model this part is typically located"
    }}
  ]
}}

Identify 3-8 main parts that would be visible and distinguishable in a 3D model.
Respond ONLY with valid JSON, no markdown."""
    
    result = _gemini_request(prompt, temperature=0.3, max_tokens=1024)
    if not result:
        return _fallback_labels(concept)
    
    try:
        cleaned = result.replace("```json", "").replace("```", "").strip()
        labels = json.loads(cleaned)
        if "parts" in labels and isinstance(labels["parts"], list):
            return labels
    except json.JSONDecodeError:
        pass
    
    return _fallback_labels(concept)


def _fallback_labels(concept: str) -> Dict[str, List[str]]:
    """Generate basic fallback labels based on concept keywords."""
    concept_lower = concept.lower()
    
    # Common object type mappings
    fallback_map = {
        "car": ["body", "wheel", "door", "window", "headlight", "bumper", "mirror"],
        "vehicle": ["body", "wheel", "window", "door", "engine"],
        "house": ["wall", "roof", "door", "window", "floor"],
        "building": ["wall", "roof", "window", "door", "foundation"],
        "tree": ["trunk", "branch", "leaf", "root", "crown"],
        "chair": ["seat", "backrest", "leg", "armrest", "cushion"],
        "table": ["surface", "leg", "drawer", "frame"],
        "human": ["head", "torso", "arm", "hand", "leg", "foot"],
        "animal": ["head", "body", "leg", "tail", "ear"],
        "phone": ["screen", "body", "button", "camera", "speaker"],
        "laptop": ["screen", "keyboard", "trackpad", "body", "port"],
    }
    
    # Find matching category
    for key, parts in fallback_map.items():
        if key in concept_lower:
            return {
                "parts": [
                    {"name": p, "description": f"The {p} of the {concept}", 
                     "function": "Structural component", "location": "Various"}
                    for p in parts
                ]
            }
    
    # Generic fallback
    return {
        "parts": [
            {"name": "body", "description": f"Main body of the {concept}",
             "function": "Primary structure", "location": "Center"}
        ]
    }


def label_model_from_mesh(concept: str, model_path: str) -> Dict[str, List[str]]:
    """
    Attempt to analyze a 3D mesh file and generate labels.
    Falls back to concept-based labeling if mesh analysis fails.
    """
    try:
        # Try to load mesh metadata if available
        import trimesh
        if trimesh and os.path.exists(model_path):
            mesh = trimesh.load(model_path, force='scene')
            
            # Extract basic mesh info
            num_geometries = len(mesh.geometry) if hasattr(mesh, 'geometry') else 1
            bounds = mesh.bounds if hasattr(mesh, 'bounds') else None
            
            # Use mesh info + concept for better labeling
            mesh_info = f"3D model with {num_geometries} parts"
            if bounds is not None:
                size = bounds[1] - bounds[0]
                mesh_info += f", dimensions approximately {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f}"
            
            return generate_part_labels(concept, mesh_info)
    except Exception as e:
        print(f"[LabelAI] Mesh analysis failed, using concept-based labeling: {e}")
    
    # Fallback to concept-only labeling
    return generate_part_labels(concept, concept)


# Cache for labels
_label_cache = {}


def get_cached_labels(model_id: str, concept: str, model_name: str = "", model_path: str = "") -> Dict[str, List[str]]:
    """Get cached or generate new labels for a model."""
    cache_key = f"{model_id}:{concept}"
    
    if cache_key in _label_cache:
        return _label_cache[cache_key]
    
    if model_path and os.path.exists(model_path):
        labels = label_model_from_mesh(concept, model_path)
    else:
        labels = generate_part_labels(concept, model_name or concept)
    
    _label_cache[cache_key] = labels
    return labels
