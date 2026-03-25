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
        print("[LabelAI] Gemini API key not configured - will use fallback labels")
        return None
    
    elapsed = time.time() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    
    url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent"
    headers = {"Content-Type": "application/json"}
    print(f"[LabelAI] Requesting labels from {GEMINI_MODEL}...")

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
                print(f"[LabelAI] Rate limited, retrying in {(2 ** attempt) + 1}s...")
                retry_delay = (2 ** attempt) + 1
                time.sleep(retry_delay)
                continue
            
            response.raise_for_status()
            data = response.json()
            
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    print("[LabelAI] Successfully generated labels from AI")
                    return parts[0].get("text", "").strip()
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[LabelAI] Attempt {attempt + 1} failed: {e}")
                time.sleep((2 ** attempt) + 1)
            else:
                print(f"[LabelAI] All {max_retries} attempts failed, will use fallback")
    
    return None


def generate_part_labels(concept: str, model_name: str, model_description: str = "") -> Dict[str, List[str]]:
    """
    Generate AI-powered part labels for a 3D model based on concept and metadata.
    Uses enhanced prompting for better accuracy and multi-step refinement.
    Returns a dict with 'parts' list containing {name, description, function, location} objects.
    """
    print(f"[LabelAI] Generating labels for concept='{concept}', model='{model_name}'")
    
    # Step 1: Enhanced initial analysis with structured requirements
    initial_prompt = f"""You are an expert 3D model analyst. Analyze this object and identify its key parts.

Object Concept: "{concept}"
Model Name: "{model_name}"
Description: "{model_description[:200]}"

CRITICAL REQUIREMENTS:
- Only identify PHYSICAL, VISIBLE parts that would exist in a real 3D model
- Parts should be distinct and visually separable
- Avoid overlapping or redundant part names
- Use lowercase, singular noun forms (e.g., 'wheel' not 'wheels')
- Prioritize structural and functional components

Return ONLY valid JSON with NO markdown:
{{
  "parts": [
    {{
      "name": "exact part name",
      "description": "What this part is (max 15 words)",
      "function": "What it does or its role (max 15 words)",
      "location": "Where it's positioned (top/bottom/center/left/right/front/back)"
    }}
  ]
}}

Identify 4-7 main parts. Be specific and technical."""

    result = _gemini_request(initial_prompt, temperature=0.2, max_tokens=1024)
    if not result:
        print(f"[LabelAI] Initial generation failed for '{concept}', using fallback")
        return _fallback_labels(concept)
    
    labels = _parse_label_json(result)
    if not labels:
        print(f"[LabelAI] Failed to parse initial response for '{concept}', using fallback")
        return _fallback_labels(concept)
    
    parts_count = len(labels.get("parts", []))
    print(f"[LabelAI] Initial generation: {parts_count} parts")
    
    # Step 2: Validation pass - check if labels are coherent with the concept
    validation_prompt = f"""Review these labels for a {concept} and fix any issues:

Current labels:
{json.dumps(labels, indent=2)}

Check for:
1. Overlap/redundancy between parts
2. Parts that don't exist on a {concept}
3. Missing common parts of a {concept}
4. Location descriptions that make sense
5. Clear distinguishability in a 3D model

Return CORRECTED JSON (same format). Fix issues, ensure accuracy."""
    
    refined = _gemini_request(validation_prompt, temperature=0.1, max_tokens=1024)
    if refined:
        refined_labels = _parse_label_json(refined)
        if refined_labels and len(refined_labels.get("parts", [])) > 0:
            labels = refined_labels
            print(f"[LabelAI] Refined via validation: {len(labels.get('parts', []))} parts")
    
    return labels


def _parse_label_json(response: str) -> Optional[Dict[str, List[Dict]]]:
    """Parse JSON response from Gemini with better error handling."""
    if not response:
        return None
    
    try:
        # Remove markdown formatting
        cleaned = response.replace("```json", "").replace("```", "").strip()
        
        # Try direct parse
        labels = json.loads(cleaned)
        
        # Validate structure
        if not isinstance(labels, dict) or "parts" not in labels:
            return None
        
        if not isinstance(labels["parts"], list) or len(labels["parts"]) == 0:
            return None
        
        # Validate each part
        valid_parts = []
        for part in labels["parts"]:
            if not isinstance(part, dict):
                continue
            
            # Ensure required fields exist
            if "name" not in part or "description" not in part:
                continue
            
            # Clean and standardize
            part["name"] = str(part.get("name", "")).strip().lower()
            part["description"] = str(part.get("description", "")).strip()
            part["function"] = str(part.get("function", "")).strip() or "Functional component"
            part["location"] = str(part.get("location", "")).strip() or "Part of structure"
            
            # Validate name is not empty
            if part["name"]:
                valid_parts.append(part)
        
        if not valid_parts:
            return None
        
        return {"parts": valid_parts}
    
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"[LabelAI] JSON parse error: {e}")
        return None


def _fallback_labels(concept: str) -> Dict[str, List[str]]:
    """
    Generate intelligent fallback labels based on concept using a comprehensive knowledge base.
    """
    concept_lower = concept.lower().strip()
    
    # Comprehensive concept-to-parts mapping
    fallback_map = {
        # Vehicles
        "car": ["body", "wheel", "door", "window", "bumper", "headlight", "mirror"],
        "truck": ["cabin", "bed", "wheel", "bumper", "mirror", "door"],
        "bus": ["body", "window", "door", "wheel", "bumper", "steering wheel"],
        "bicycle": ["frame", "wheel", "pedal", "handlebar", "seat", "chain"],
        "motorcycle": ["engine", "wheel", "handlebar", "seat", "exhaust pipe"],
        "train": ["locomotive", "carriage", "wheel", "coupling", "pantograph"],
        "plane": ["fuselage", "wing", "tail", "cockpit", "engine", "landing gear"],
        "helicopter": ["rotor", "fuselage", "tail boom", "landing skid", "cockpit"],
        "boat": ["hull", "sail", "rudder", "cabin", "mast"],
        "ship": ["hull", "deck", "cabin", "mast", "anchor", "propeller"],
        
        # Buildings & Architecture
        "house": ["wall", "roof", "door", "window", "foundation", "chimney"],
        "building": ["wall", "roof", "window", "entrance", "floor", "balcony"],
        "tower": ["base", "shaft", "pinnacle", "window", "staircase"],
        "bridge": ["deck", "support", "railing", "arch", "pillar"],
        "church": ["steeple", "nave", "altar", "door", "window", "cross"],
        "mosque": ["dome", "minaret", "courtyard", "entrance", "prayer hall"],
        "temple": ["roof", "pillar", "altar", "stairway", "gateway"],
        "hospital": ["building", "entrance", "window", "roof", "ambulance bay"],
        
        # Furniture
        "chair": ["seat", "backrest", "leg", "armrest", "cushion"],
        "table": ["surface", "leg", "drawer", "frame"],
        "sofa": ["cushion", "armrest", "leg", "backrest"],
        "bed": ["frame", "mattress", "headboard", "footboard", "leg"],
        "desk": ["surface", "drawer", "leg", "shelf"],
        "cabinet": ["door", "drawer", "shelf", "handle", "leg"],
        "couch": ["cushion", "armrest", "leg", "backrest", "frame"],
        "bench": ["seat", "leg", "backrest"],
        
        # Anatomy
        "human": ["head", "torso", "arm", "hand", "leg", "foot"],
        "skeleton": ["skull", "spine", "rib cage", "pelvis", "limb bone"],
        "face": ["forehead", "eye", "nose", "mouth", "cheek"],
        
        # Animals
        "dog": ["head", "body", "leg", "tail", "ear"],
        "cat": ["head", "body", "leg", "tail", "ear"],
        "bird": ["head", "body", "wing", "tail", "leg"],
        "fish": ["head", "body", "fin", "tail"],
        "horse": ["head", "neck", "body", "leg", "tail"],
        "elephant": ["head", "trunk", "body", "leg", "ear"],
        "lion": ["head", "mane", "body", "leg", "tail"],
        
        # Technology
        "phone": ["screen", "body", "button", "camera", "speaker", "port"],
        "laptop": ["screen", "keyboard", "trackpad", "body", "port"],
        "computer": ["case", "motherboard", "cpu", "fan", "port"],
        "monitor": ["screen", "stand", "bezel", "base"],
        "keyboard": ["key", "case", "cable"],
        "camera": ["lens", "body", "viewfinder", "trigger"],
        "robot": ["head", "torso", "arm", "hand", "leg"],
        
        # Nature
        "tree": ["trunk", "branch", "leaf", "root", "crown"],
        "flower": ["petal", "stem", "leaf", "center"],
        "cactus": ["stem", "spine", "bulge"],
        
        # Food & Beverage
        "apple": ["skin", "flesh", "core", "stem"],
        "pizza": ["crust", "sauce", "cheese", "topping"],
        "cake": ["cake", "frosting", "layer", "candle"],
        "cup": ["rim", "body", "handle", "base"],
        "bottle": ["cap", "neck", "body", "bottom"],
        "glass": ["rim", "bowl", "stem", "base"],
        
        # Objects & Structures
        "sword": ["blade", "hilt", "crossguard", "pommel"],
        "gun": ["barrel", "trigger", "magazine", "grip"],
        "door": ["frame", "panel", "handle", "hinge"],
        "window": ["frame", "glass", "sill", "latch"],
        "box": ["lid", "base", "side", "edge"],
        "lamp": ["base", "shade", "bulb", "switch"],
        
        # Landmarks & Monuments
        "taj mahal": ["main dome", "minarets", "main platform", "entrance gateway", "reflecting pool"],
        "pyramid": ["apex", "base", "face", "chamber", "passage"],
        "statue": ["head", "torso", "arm", "hand", "legs", "base"],
        "monument": ["main structure", "base", "pedestal", "inscription", "platform"],
        "mosque": ["dome", "minaret", "courtyard", "prayer hall", "entrance"],
        "pagoda": ["roof", "spire", "level", "column", "railing"],
        
        # Celestial Objects
        "solar system": ["sun", "planet", "asteroid", "comet", "moon"],
        "planet": ["core", "surface", "atmosphere", "poles"],
        "moon": ["crater", "surface", "terminator"],
        "star": ["core", "surface", "corona"],
        "galaxy": ["center", "arm", "disk", "halo"],
    }
    
    # Match concept against fallback map - try exact first, then partial
    matched_parts = None
    
    # Exact match
    if concept_lower in fallback_map:
        matched_parts = fallback_map[concept_lower]
    else:
        # Partial match - check if concept contains any key
        for key in fallback_map.keys():
            if key in concept_lower:
                matched_parts = fallback_map[key]
                break
    
    # Build the return structure
    if matched_parts:
        return {
            "parts": [
                {
                    "name": part,
                    "description": f"The {part} of this {concept}",
                    "function": "Structural and functional component",
                    "location": _infer_location(part, concept_lower)
                }
                for part in matched_parts
            ]
        }
    
    # Generic fallback if no match found
    return {
        "parts": [
            {
                "name": "body",
                "description": f"Main body of the {concept}",
                "function": "Primary structural element",
                "location": "Center"
            }
        ]
    }


def _infer_location(part: str, concept: str) -> str:
    """Infer likely location of a part based on common conventions."""
    part_lower = part.lower()
    
    # Common location patterns
    top_parts = {"roof", "crown", "top", "head", "cap", "lid", "antenna", "mast", "steeple"}
    bottom_parts = {"base", "leg", "foot", "foundation", "sole", "bottom", "bed", "footboard"}
    front_parts = {"door", "window", "face", "bumper", "headlight", "grille", "entrance"}
    back_parts = {"trunk", "tail", "exhaust", "rear panel", "engine"}
    center_parts = {"body", "torso", "core", "center", "main"}
    
    if any(p in part_lower for p in top_parts):
        return "Top"
    elif any(p in part_lower for p in bottom_parts):
        return "Bottom"
    elif any(p in part_lower for p in front_parts):
        return "Front"
    elif any(p in part_lower for p in back_parts):
        return "Back"
    elif any(p in part_lower for p in center_parts):
        return "Center"
    
    return "Part of structure"


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
        print(f"[LabelAI] Using cached labels for {model_id}")
        return _label_cache[cache_key]
    
    if model_path and os.path.exists(model_path):
        labels = label_model_from_mesh(concept, model_path)
    else:
        labels = generate_part_labels(concept, model_name or concept)
    
    _label_cache[cache_key] = labels
    return labels
