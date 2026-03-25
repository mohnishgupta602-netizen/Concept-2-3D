import os
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from groq import Groq
from intent import IntentAnalyzer
from search import ModelSearchEngine, CACHE_VERSION
from reviews import submit_review, get_reviews, get_review_summary, get_user_review

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

app = FastAPI(title="3D Model Generation API")

# Configure allowed origins from env (comma-separated). Defaults to open for local/dev convenience.
raw_origins = (os.getenv("ALLOWED_ORIGINS") or "*").strip()
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()] or ["*"]

# Setup CORS for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

models_dir = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(models_dir, exist_ok=True)
app.mount("/models", StaticFiles(directory=models_dir), name="models")

intent_analyzer = IntentAnalyzer()
search_engine = ModelSearchEngine()

class QueryRequest(BaseModel):
    query: str

@app.post("/api/intent")
async def analyze_intent(request: QueryRequest):
    """
    Expands the user prompt into primary keywords, structural components, and context.
    Provides fallback capabilities using Gemini if configured.
    """
    try:
        result = intent_analyzer.parse(request.query)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
async def search_models(request: QueryRequest):
    """
    Takes the parsed intent and queries external APIs to find the best 3D models.
    """
    try:
        # First, analyze intent (or expect the frontend to pass the intent)
        intent = intent_analyzer.parse(request.query)
        
        # Search using the intent keywords
        results = search_engine.search(intent)
        
        if not results:
            # Fallback 1: Procedural generation metadata
            return {
                "status": "fallback",
                "message": "No specific models found, using procedural generation.",
                "data": {
                    "type": "procedural",
                    "components": intent.get("structural_components", ["sphere", "box"])
                }
            }
        
        return {"status": "success", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ChatRequest(BaseModel):
    message: str
    model_context: Optional[str] = None


class CacheClearRequest(BaseModel):
    query: Optional[str] = None


class ReviewRequest(BaseModel):
    model_id: str
    user_id: str
    rating: int
    comment: Optional[str] = ""


class LabelPositioningRequest(BaseModel):
    model_id: str
    concept: str
    part_definitions: list
    model_image_base64: str  # Base64-encoded PNG/JPG image

@app.post("/api/chat")
async def chat_with_ai(request: ChatRequest):
    """
    Handles user questions about the current model using Groq API.
    """
    try:
        completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": f"You are a helpful AI 3D design assistant. The user is currently viewing a 3D model: {request.model_context or 'Unknown'}. Answer their questions concisely."
                },
                {
                    "role": "user",
                    "content": request.message,
                }
            ],
            model="llama-3.3-70b-versatile",
        )
        return {"status": "success", "message": completion.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cache/clear")
async def clear_cache(request: CacheClearRequest):
    """
    Clears cached search entries.
    - If query is provided, clears only that normalized query key.
    - If omitted, clears all cached entries.
    """
    try:
        if request.query:
            normalized = search_engine._normalize_query(request.query)
            cache_key = f"{CACHE_VERSION}::{normalized}"
            deleted = search_engine.cache.clear_cache(cache_key)
            return {"status": "success", "cleared": deleted, "scope": "single", "query": normalized}

        deleted = search_engine.cache.clear_cache()
        return {"status": "success", "cleared": deleted, "scope": "all"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reviews/submit")
async def submit_model_review(request: ReviewRequest):
    """
    Submit or update a review for a model.
    Allows users to rate (1-5 stars) and add optional comments.
    """
    try:
        review = submit_review(
            model_id=request.model_id,
            user_id=request.user_id,
            rating=request.rating,
            comment=request.comment or ""
        )
        return {"status": "success", "review": review}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reviews/{model_id}")
async def get_model_reviews(model_id: str, limit: int = 50):
    """
    Fetch all reviews for a specific model.
    Returns reviews sorted by newest first.
    """
    try:
        reviews = get_reviews(model_id, limit=limit)
        summary = get_review_summary(model_id)
        return {
            "status": "success",
            "model_id": model_id,
            "summary": summary,
            "reviews": reviews
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reviews/{model_id}/summary")
async def get_model_review_summary(model_id: str):
    """
    Get aggregate review statistics for a model.
    Returns average rating, total count, and distribution by star rating.
    """
    try:
        summary = get_review_summary(model_id)
        return {"status": "success", "data": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reviews/{model_id}/user/{user_id}")
async def get_user_model_review(model_id: str, user_id: str):
    """
    Get the current user's review for a specific model.
    Used to pre-populate review form if user has already reviewed.
    """
    try:
        review = get_user_review(model_id, user_id)
        if not review:
            return {"status": "success", "review": None}
        return {"status": "success", "review": review}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/labels/position-from-image")
async def position_labels_from_image(request: LabelPositioningRequest):
    """
    Use Gemini vision API to analyze a model image and generate precise x,y,z coordinates
    for each part label based on visual analysis of the 3D model.
    
    The frontend captures a screenshot of the 3D model and sends it here along with part definitions.
    Gemini analyzes the image and returns optimized x,y,z coordinates for each label.
    """
    try:
        # Validate input
        if not request.model_image_base64:
            raise ValueError("Model image is required for vision-based positioning")
        
        if not request.part_definitions or len(request.part_definitions) == 0:
            return {"status": "success", "updated_parts": []}
        
        # Use Gemini vision to refine positions
        updated_parts = search_engine._get_gemini_label_positions(
            normalized_keywords=request.concept or "model",
            part_definitions=request.part_definitions,
            model_image_base64=request.model_image_base64
        )
        
        return {
            "status": "success",
            "model_id": request.model_id,
            "concept": request.concept,
            "updated_parts": updated_parts,
            "message": "Label positions optimized using Gemini vision analysis"
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Label positioning error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
