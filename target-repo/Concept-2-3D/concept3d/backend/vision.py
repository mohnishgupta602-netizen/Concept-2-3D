from transformers import pipeline
from PIL import Image
import io

# Load an extremely lightweight Image classification model for speed.
try:
    classifier = pipeline("image-classification", model="google/vit-base-patch16-224")
except Exception as e:
    print(f"Error loading vision model: {e}")
    classifier = None

def classify_image(file_bytes: bytes) -> str:
    if classifier is None:
        return "Unknown"
        
    try:
        image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        results = classifier(image)
        # The first result is the highest confidence
        if results and len(results) > 0:
            # Often labels are comma separated list of nouns, we'll take the first primary noun
            best_label = results[0]['label'].split(',')[0].strip()
            return best_label
    except Exception as e:
        print(f"Image classification error: {e}")
        
    return "Unknown Object"
