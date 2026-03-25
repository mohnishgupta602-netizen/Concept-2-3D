import re

STOPWORDS = {
    "a", "an", "and", "or", "the", "of", "for", "to", "in", "on", "at", "with", "by", "from",
    "is", "are", "was", "were", "this", "that", "these", "those", "about",
}

CATEGORY_SEED_TERMS = {
    "monuments": [
        "taj mahal", "eiffel tower", "statue of liberty", "colosseum", "big ben", "pyramid",
        "temple", "cathedral", "palace", "fort", "castle", "landmark"
    ],
    "body_parts": [
        "heart anatomy", "brain anatomy", "lungs anatomy", "kidney anatomy", "liver anatomy", "eye anatomy",
        "ear anatomy", "human skull", "skeleton", "hand anatomy", "foot anatomy", "spine"
    ],
    "animals": [
        "bear", "lion", "tiger", "elephant", "horse", "dog", "cat", "wolf", "deer", "bird", "eagle", "shark"
    ],
    "vehicles": [
        "car", "truck", "bus", "motorbike", "bicycle", "train", "airplane", "helicopter",
        "ship", "boat", "submarine", "tank"
    ],
    "architecture": [
        "house", "building", "skyscraper", "bridge", "stadium", "office", "apartment", "school",
        "hospital", "factory", "warehouse", "museum"
    ],
    "furniture": [
        "chair", "table", "sofa", "bed", "desk", "cabinet", "wardrobe", "lamp", "bookshelf", "stool"
    ],
    "electronics": [
        "laptop", "computer", "smartphone", "camera", "television", "speaker", "headphones", "drone"
    ],
    "nature": [
        "tree", "flower", "plant", "mountain", "rock", "river", "waterfall", "forest", "cloud"
    ],
    "food": [
        "apple", "banana", "pizza", "burger", "bread", "cake", "bottle", "cup", "plate"
    ],
    "medical": [
        "stethoscope", "syringe", "hospital bed", "microscope", "xray machine", "medical instrument"
    ],
    "space": [
        "solar system", "sun", "mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune", "planet", "orbit"
    ],
}


def tokenize(text: str):
    if not text:
        return []
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t and t not in STOPWORDS]


def detect_categories(query: str):
    tokens = set(tokenize(query))
    if not tokens:
        return []

    matched = []
    joined = " ".join(tokens)
    for category, terms in CATEGORY_SEED_TERMS.items():
        if any(term in joined for term in terms):
            matched.append(category)
            continue

        for term in terms:
            term_tokens = set(tokenize(term))
            if term_tokens and len(term_tokens & tokens) >= max(1, min(2, len(term_tokens))):
                matched.append(category)
                break

    return matched


def get_seed_terms_for_query(query: str, max_terms: int = 24):
    categories = detect_categories(query)
    terms = [query.strip().lower()] if query else []

    if categories:
        for category in categories:
            terms.extend(CATEGORY_SEED_TERMS.get(category, []))
    else:
        # Broad defaults when category is not obvious.
        for category in ["monuments", "body_parts", "animals", "vehicles", "architecture"]:
            terms.extend(CATEGORY_SEED_TERMS.get(category, [])[:6])

    deduped = []
    seen = set()
    for term in terms:
        key = " ".join(tokenize(term))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(term)
        if len(deduped) >= max_terms:
            break

    return deduped


def get_category_part_priors(query: str):
    q = (query or "").lower()

    if any(t in q for t in ["brain", "cerebrum"]):
        return [
            {"name": "frontal_lobe", "primitive": "sphere", "description": "Executive and motor planning region.", "position": {"x": 0.0, "y": 0.25, "z": 0.22}, "parameters": {}},
            {"name": "parietal_lobe", "primitive": "sphere", "description": "Sensory integration region.", "position": {"x": 0.0, "y": 0.34, "z": 0.0}, "parameters": {}},
            {"name": "temporal_lobe", "primitive": "sphere", "description": "Auditory processing region.", "position": {"x": 0.28, "y": 0.05, "z": 0.08}, "parameters": {}},
            {"name": "occipital_lobe", "primitive": "sphere", "description": "Visual cortex region.", "position": {"x": 0.0, "y": 0.15, "z": -0.22}, "parameters": {}},
            {"name": "brainstem", "primitive": "cylinder", "description": "Connection to spinal cord.", "position": {"x": 0.0, "y": -0.25, "z": -0.05}, "parameters": {}},
        ]

    if any(t in q for t in ["lung", "lungs"]):
        return [
            {"name": "left_lung", "primitive": "sphere", "description": "Left pulmonary lobe complex.", "position": {"x": -0.22, "y": 0.12, "z": 0.06}, "parameters": {}},
            {"name": "right_lung", "primitive": "sphere", "description": "Right pulmonary lobe complex.", "position": {"x": 0.22, "y": 0.12, "z": 0.06}, "parameters": {}},
            {"name": "trachea", "primitive": "cylinder", "description": "Primary airway conduit.", "position": {"x": 0.0, "y": 0.42, "z": 0.08}, "parameters": {}},
            {"name": "bronchi", "primitive": "tube", "description": "Main branches feeding lungs.", "position": {"x": 0.0, "y": 0.26, "z": 0.06}, "parameters": {}},
        ]

    if any(t in q for t in ["kidney", "renal"]):
        return [
            {"name": "renal_cortex", "primitive": "sphere", "description": "Outer kidney filtration region.", "position": {"x": 0.0, "y": 0.08, "z": 0.08}, "parameters": {}},
            {"name": "renal_medulla", "primitive": "sphere", "description": "Inner collecting pyramids.", "position": {"x": 0.0, "y": 0.0, "z": 0.02}, "parameters": {}},
            {"name": "renal_pelvis", "primitive": "cone", "description": "Collection funnel to ureter.", "position": {"x": 0.2, "y": -0.06, "z": 0.0}, "parameters": {}},
            {"name": "ureter", "primitive": "cylinder", "description": "Urine transport tube.", "position": {"x": 0.28, "y": -0.26, "z": 0.0}, "parameters": {}},
        ]

    if any(t in q for t in ["eye", "eyeball"]):
        return [
            {"name": "cornea", "primitive": "sphere", "description": "Transparent front optical surface.", "position": {"x": 0.0, "y": 0.05, "z": 0.26}, "parameters": {}},
            {"name": "iris", "primitive": "sphere", "description": "Pigmented aperture control ring.", "position": {"x": 0.0, "y": 0.03, "z": 0.2}, "parameters": {}},
            {"name": "lens", "primitive": "sphere", "description": "Focus-adjusting optical lens.", "position": {"x": 0.0, "y": 0.02, "z": 0.08}, "parameters": {}},
            {"name": "retina", "primitive": "sphere", "description": "Light sensing posterior layer.", "position": {"x": 0.0, "y": -0.02, "z": -0.18}, "parameters": {}},
            {"name": "optic_nerve", "primitive": "cylinder", "description": "Signal pathway to brain.", "position": {"x": 0.0, "y": -0.08, "z": -0.3}, "parameters": {}},
        ]

    if any(t in q for t in ["monument", "fort", "palace", "temple", "tower", "taj", "mahal"]):
        return [
            {"name": "base_plinth", "primitive": "cube", "description": "Foundational platform structure.", "position": {"x": 0.0, "y": -0.62, "z": 0.0}, "parameters": {}},
            {"name": "central_mass", "primitive": "cube", "description": "Main architectural core mass.", "position": {"x": 0.0, "y": 0.0, "z": 0.0}, "parameters": {}},
            {"name": "main_dome_or_roof", "primitive": "sphere", "description": "Upper landmark crown element.", "position": {"x": 0.0, "y": 0.84, "z": 0.0}, "parameters": {}},
            {"name": "left_tower", "primitive": "cylinder", "description": "Left flanking tower/minaret.", "position": {"x": -0.9, "y": 0.1, "z": 0.0}, "parameters": {}},
            {"name": "right_tower", "primitive": "cylinder", "description": "Right flanking tower/minaret.", "position": {"x": 0.9, "y": 0.1, "z": 0.0}, "parameters": {}},
        ]

    if any(t in q for t in ["airplane", "aircraft", "plane"]):
        return [
            {"name": "fuselage", "primitive": "cylinder", "description": "Main aircraft body.", "position": {"x": 0.0, "y": 0.0, "z": 0.0}, "parameters": {}},
            {"name": "left_wing", "primitive": "cube", "description": "Left lift surface.", "position": {"x": -0.7, "y": 0.02, "z": 0.0}, "parameters": {}},
            {"name": "right_wing", "primitive": "cube", "description": "Right lift surface.", "position": {"x": 0.7, "y": 0.02, "z": 0.0}, "parameters": {}},
            {"name": "tail_fin", "primitive": "cube", "description": "Vertical stabilizer.", "position": {"x": 0.0, "y": 0.3, "z": -0.8}, "parameters": {}},
            {"name": "engine_cluster", "primitive": "cylinder", "description": "Propulsion section.", "position": {"x": 0.0, "y": -0.15, "z": 0.08}, "parameters": {}},
        ]

    if any(t in q for t in ["solar system", "planet", "sun", "mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune"]):
        return [
            {"name": "sun", "primitive": "sphere", "description": "Central star around which all planets orbit.", "position": {"x": 0.0, "y": 0.0, "z": 0.0}, "parameters": {}},
            {"name": "inner_planets_orbit", "primitive": "tube", "description": "Orbital region for Mercury, Venus, Earth, and Mars.", "position": {"x": 0.0, "y": 0.0, "z": 0.0}, "parameters": {}},
            {"name": "earth", "primitive": "sphere", "description": "Third planet from the Sun; a terrestrial planet.", "position": {"x": 0.42, "y": 0.0, "z": 0.0}, "parameters": {}},
            {"name": "mars", "primitive": "sphere", "description": "Fourth planet from the Sun, beyond Earth.", "position": {"x": 0.58, "y": 0.04, "z": 0.06}, "parameters": {}},
            {"name": "jupiter", "primitive": "sphere", "description": "Largest gas giant in the solar system.", "position": {"x": 0.82, "y": 0.0, "z": 0.0}, "parameters": {}},
            {"name": "saturn", "primitive": "sphere", "description": "Gas giant known for its prominent ring system.", "position": {"x": 1.02, "y": 0.02, "z": 0.05}, "parameters": {}},
            {"name": "outer_planets_orbit", "primitive": "tube", "description": "Orbital zone for Jupiter through Neptune.", "position": {"x": 0.0, "y": 0.0, "z": 0.0}, "parameters": {}},
        ]

    return []
