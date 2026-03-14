from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from search import search_models
from fallback import generate_fallback
from database import save_search_result
from wikipedia_api import get_wikipedia_summary
from vision import classify_image

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the forged Tripo3D .glb models locally
models_dir = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(models_dir, exist_ok=True)
app.mount("/models", StaticFiles(directory=models_dir), name="models")

@app.get("/visualize")
def visualize(concept: str):
    # Tripo3D Generative AI Search Pipeline (Zero Sketchfab)
    generated_models = search_models(concept)
    ai_overview = get_wikipedia_summary(concept)

    if generated_models:
        top_match = generated_models[0]
        # Save to DB
        save_search_result(
            concept=concept,
            model_name=top_match.get("name"),
            description=top_match.get("description"),
            similarity_score=top_match.get("score"),
            source="tripo3d_ai"
        )
        return {
            "type": "model",
            "data": top_match,
            "ai_overview": ai_overview
        }
        
    # Save fallback to DB
    save_search_result(
        concept=concept,
        model_name="fallback",
        description="Geometric fallback",
        similarity_score=0.0,
        source="internal"
    )

    return {
        "type": "fallback",
        "shapes": generate_fallback(concept),
        "ai_overview": ai_overview
    }

@app.post("/upload")
async def handle_image_upload(file: UploadFile = File(...)):
    """Receives an image, runs local inference to determine the concept string, 
    and returns it so the frontend can trigger the pipeline to generate it."""
    image_bytes = await file.read()
    concept_label = classify_image(image_bytes)
    return {"concept": concept_label}

