def generate_fallback(concept):
    primitives = {
        "tree": ["cylinder", "sphere"],
        "heart": ["sphere", "tube"],
        "taj mahal": ["cube", "sphere", "cylinder"],
        "car": ["cube", "cylinder"],
        "house": ["cube", "cone"]
    }

    # Default fallback is a simple box representation
    return primitives.get(concept.lower(), ["cube"])
