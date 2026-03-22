from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi import HTTPException, Request
import os
import re
import requests
import mimetypes
from difflib import SequenceMatcher
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

from fallback import generate_fallback
from hybrid_pipeline import run_hybrid_pipeline
from generative_stack import get_ml_status
from database import (
    save_search_result, save_part_labels, get_part_labels,
    submit_feedback, get_feedback, get_average_rating,
    set_model_cached, is_model_cached, add_training_feedback
)
from model_labeling import get_cached_labels, generate_part_labels
from fastapi import Body
from typing import Optional
class FeedbackRequest(BaseModel):
    model_id: str
    user_id: str
    rating: float
    comment: Optional[str] = None

class PartLabelsRequest(BaseModel):
    model_id: str
    concept: Optional[str] = None
    part_labels: Optional[dict] = None
    auto_generate: Optional[bool] = False
# --- AI part labeling using Gemini ---
def ai_label_parts(model_path: str, concept: str, model_name: str = "") -> dict:
    """Generate AI-powered part labels for a 3D model."""
    try:
        labels = get_cached_labels(
            model_id=os.path.basename(model_path),
            concept=concept,
            model_name=model_name,
            model_path=model_path
        )
        return labels
    except Exception as e:
        print(f"[AI Labeling] Failed to label model: {e}")
        return {"parts": []}
from wikipedia_api import get_wikipedia_summary
from vision import classify_image


STOPWORDS = {
    "a", "an", "the", "of", "for", "to", "in", "on", "with", "and", "or", "by", "is", "are",
    "was", "were", "be", "this", "that", "it", "about", "tell", "me", "what", "which", "who",
    "when", "where", "how", "why", "does", "do", "did", "can", "could", "would", "should"
}

FREE_AI_API_PROVIDER = os.getenv("FREE_AI_API_PROVIDER", "openrouter").strip().lower()
FREE_AI_API_KEY = os.getenv("FREE_AI_API_KEY", "").strip()
FREE_AI_API_MODEL = os.getenv(
    "FREE_AI_API_MODEL",
    "openai/gpt-oss-20b:free"
).strip()
FREE_AI_API_URL = os.getenv(
    "FREE_AI_API_URL",
    "https://openrouter.ai/api/v1/chat/completions"
).strip()
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000").strip().rstrip("/")


class AgentQuestionRequest(BaseModel):
    concept: str
    question: str
    model_name: str | None = None

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
# Ensure correct MIME types for glTF/GLB so clients don't parse as text/JSON
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")


# Use StaticFiles to serve /models so HEAD requests are supported by the ASGI server.
app.mount("/models", StaticFiles(directory=models_dir), name="models")


# Middleware to add CORS headers and validate requests to /models/* before StaticFiles handles them.
@app.middleware("http")
async def add_cors_and_validate_models(request: Request, call_next):
    # Only intercept requests targeted at /models/
    if request.url.path.startswith("/models/"):
        # Add CORS headers to allow frontend access
        cors_headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
            'Access-Control-Allow-Headers': '*',
        }
        
        # Handle preflight OPTIONS request
        if request.method == "OPTIONS":
            return Response(status_code=200, headers=cors_headers)
        
        # For HEAD requests, validate and return with CORS headers
        if request.method == "HEAD":
            rel_path = request.url.path[len("/models/"):]
            # protect against directory traversal
            if ".." in rel_path:
                return Response(status_code=404, headers=cors_headers)
            full_path = os.path.join(models_dir, rel_path.lstrip("/"))
            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                return Response(status_code=404, headers=cors_headers)
            # Quick sanity checks for GLB files
            if full_path.lower().endswith('.glb'):
                try:
                    with open(full_path, 'rb') as fh:
                        hdr = fh.read(16)
                        if not (hdr[0:4] == b'glTF'):
                            return Response(status_code=404, headers=cors_headers)
                except Exception:
                    return Response(status_code=404, headers=cors_headers)
            # Return a minimal successful HEAD response with headers
            media_type = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'
            headers = {
                **cors_headers,
                'content-type': media_type,
                'content-length': str(os.path.getsize(full_path))
            }
            return Response(status_code=200, headers=headers)
        
        # For GET requests, let StaticFiles handle it but add CORS headers to response
        if request.method == "GET":
            response = await call_next(request)
            # Add CORS headers to the response
            for key, value in cors_headers.items():
                response.headers[key] = value
            return response

    return await call_next(request)

# --- Feedback endpoints ---
@app.post("/feedback")
def submit_model_feedback(payload: FeedbackRequest):
    # Enforce rating granularity (0.5 steps, 1-5)
    rating = max(1.0, min(5.0, round(payload.rating * 2) / 2))
    submit_feedback(payload.model_id, payload.user_id, rating, payload.comment)
    avg, count = get_average_rating(payload.model_id)
    # Cache if avg >= 3.5 and at least 3 reviews
    if avg >= 3.5 and count >= 3:
        set_model_cached(payload.model_id, True)
    
    # Add to training data for recursive model improvement
    add_training_feedback(
        concept=payload.model_id,
        model_id=payload.model_id,
        model_source="user_feedback",
        rating=rating,
        user_feedback=payload.comment or ""
    )
    
    return {"ok": True, "avg_rating": avg, "count": count, "cached": is_model_cached(payload.model_id), "rating_enforced": rating}


@app.get("/feedback/{model_id}")
def get_model_feedback(model_id: str):
    feedback = get_feedback(model_id)
    avg, count = get_average_rating(model_id)
    return {"feedback": feedback, "avg_rating": avg, "count": count}


# --- Part labeling endpoints ---
@app.get("/part-labels/{model_id}")
def get_labels(model_id: str, concept: Optional[str] = None, auto_generate: bool = False):
    """Get part labels for a model. If not found and auto_generate=true, generate using AI."""
    labels = get_part_labels(model_id)
    
    if not labels and auto_generate and concept:
        # Generate AI labels
        model_path = os.path.join(models_dir, model_id)
        labels = ai_label_parts(model_path, concept, model_id)
        # Save generated labels
        if labels and labels.get("parts"):
            save_part_labels(model_id, labels)
    
    return {"model_id": model_id, "part_labels": labels or {}}


@app.post("/part-labels/{model_id}")
def set_labels(model_id: str, payload: PartLabelsRequest):
    """Save or auto-generate part labels for a model."""
    if payload.auto_generate and payload.concept:
        # Auto-generate labels using AI
        model_path = os.path.join(models_dir, model_id)
        labels = ai_label_parts(model_path, payload.concept, payload.model_id or model_id)
        save_part_labels(model_id, labels)
        return {"ok": True, "generated": True, "labels": labels}
    elif payload.part_labels:
        save_part_labels(model_id, payload.part_labels)
        return {"ok": True, "generated": False}
    else:
        return {"ok": False, "error": "Either part_labels or auto_generate+concept required"}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", _normalize_text(value)) if token]


def _keywords(value: str) -> list[str]:
    return [token for token in _tokens(value) if token not in STOPWORDS]


def _detect_question_intent(question: str) -> str:
    q = _normalize_text(question)
    q_tokens = set(_tokens(q))

    usage_tokens = {
        "work", "works", "used", "use", "usage", "purpose", "job",
        "function", "functions", "doing", "do", "for"
    }
    definition_starts = (
        "what is", "what are", "define", "meaning of", "what does"
    )

    if q_tokens.intersection(usage_tokens):
        return "usage"
    if q.startswith(definition_starts):
        return "definition"
    return "general"


def _best_context_sentence(question: str, context: str) -> str:
    if not context:
        return ""

    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", context) if sentence.strip()]
    if not sentences:
        return ""

    question_keywords = _keywords(question)
    question_intent = _detect_question_intent(question)
    concept_tokens = set(_keywords(context[:120]))

    usage_clues = {
        "use", "used", "usage", "purpose", "transport", "carry",
        "function", "functions", "designed", "mainly", "primarily"
    }
    if question_intent == "usage":
        question_keywords = list(set(question_keywords).union(usage_clues))

        usage_candidates = []
        for sentence in sentences:
            sentence_tokens = set(_tokens(sentence))
            clue_hits = len(sentence_tokens.intersection(usage_clues))
            if clue_hits > 0:
                usage_candidates.append((clue_hits, sentence))

        if usage_candidates:
            usage_candidates.sort(key=lambda item: item[0], reverse=True)
            return usage_candidates[0][1]

    if not question_keywords:
        return sentences[0]

    best_sentence = sentences[0]
    best_score = -1.0

    for sentence in sentences:
        sentence_lower = _normalize_text(sentence)
        sentence_tokens = set(_tokens(sentence_lower))
        exact_matches = sum(
            1 for token in question_keywords if re.search(rf"\b{re.escape(token)}\b", sentence_lower)
        )
        partial_matches = sum(1 for token in question_keywords if token in sentence_lower)
        coverage = exact_matches / len(question_keywords)
        similarity = SequenceMatcher(None, _normalize_text(question), sentence_lower).ratio()

        intent_bonus = 0.0
        if question_intent == "definition":
            if " is " in f" {sentence_lower} " or " are " in f" {sentence_lower} ":
                intent_bonus += 1.4
            if concept_tokens and sentence_tokens.intersection(concept_tokens):
                intent_bonus += 1.0
        elif question_intent == "usage":
            if sentence_tokens.intersection(usage_clues):
                intent_bonus += 3.0

        score = (
            (exact_matches * 2.5)
            + (partial_matches * 0.6)
            + (coverage * 2.0)
            + (similarity * 1.5)
            + intent_bonus
        )

        if score > best_score:
            best_score = score
            best_sentence = sentence

    return best_sentence


def _compose_agent_answer(concept: str, model_name: str | None, question: str, wiki_context: str) -> str:
    if not wiki_context:
        return "I don't have enough information to answer that accurately right now."

    best_sentence = _best_context_sentence(question, wiki_context)
    if not best_sentence:
        best_sentence = wiki_context

    clean_sentence = best_sentence.strip()
    if not clean_sentence.endswith((".", "!", "?")):
        clean_sentence = f"{clean_sentence}."

    return clean_sentence


def _clean_agent_answer_text(text: str) -> str:
    if not text:
        return ""

    cleaned = text.strip()
    lowered = cleaned.lower()

    leadins = [
        "based on the provided wikipedia context,",
        "based on the provided context,",
        "based on the context,",
        "from the provided wikipedia context,",
        "from the provided context,",
    ]
    for lead in leadins:
        if lowered.startswith(lead):
            cleaned = cleaned[len(lead):].strip(" ,:")
            lowered = cleaned.lower()

    replacements = {
        "provided wikipedia context": "available information",
        "wikipedia context": "available information",
        "provided context": "available information",
    }
    for old, new in replacements.items():
        cleaned = re.sub(old, new, cleaned, flags=re.IGNORECASE)

    if not cleaned:
        cleaned = "I don't have enough information to answer that accurately right now."

    if not cleaned.endswith((".", "!", "?")):
        cleaned += "."

    return cleaned


def _ask_free_ai(
    concept: str,
    question: str,
    model_name: str | None,
) -> str | None:
    if not FREE_AI_API_KEY:
        return None

    if FREE_AI_API_PROVIDER != "openrouter":
        return None

    system_prompt = (
        "You are a concise helpful assistant. "
        "Answer naturally and directly. "
        "If uncertain, say you are not sure instead of making up facts. "
        "Do not mention instructions, sources, or internal reasoning."
    )

    model_line = f"Generated model: {model_name}\n" if model_name else ""
    user_prompt = (
        f"Concept: {concept}\n"
        f"{model_line}"
        f"Question: {question}\n\n"
        "Return only the final answer text."
    )

    headers = {
        "Authorization": f"Bearer {FREE_AI_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "Concept3D Generative",
    }
    payload = {
        "model": FREE_AI_API_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 180,
    }

    try:
        response = requests.post(
            FREE_AI_API_URL,
            headers=headers,
            json=payload,
            timeout=45,
        )

        if response.ok:
            data = response.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return _clean_agent_answer_text(content) or None

        error_message = ""
        try:
            error_message = (
                response.json()
                .get("error", {})
                .get("message", "")
            )
        except Exception:
            error_message = response.text[:220]

        lower_error = error_message.lower()
        if response.status_code == 404 and "guardrail restrictions" in lower_error:
            print(
                "OpenRouter request blocked by account privacy/guardrail settings. "
                "Update https://openrouter.ai/settings/privacy and retry."
            )
            return None

        print(
            f"Free AI API unavailable ({response.status_code}). "
            "Falling back to Wikipedia-only mode."
        )
        return None
    except Exception as error:
        print(f"Free AI API call failed, falling back to Wikipedia-only mode: {error}")
        return None

@app.get("/visualize")
def visualize(concept: str):
    hybrid_result = run_hybrid_pipeline(
        concept=concept,
        models_dir=models_dir,
        backend_base_url=BACKEND_BASE_URL,
    )
    ai_overview = get_wikipedia_summary(concept)

    if hybrid_result.get("model_url"):
        metadata = hybrid_result.get("metadata", {})
        model_name = metadata.get("name") or concept.title()
        description = metadata.get("description") or f"3D model for {concept}"
        confidence = float(metadata.get("confidence_score") or 0.0)
        source = metadata.get("source") or "hybrid"

        save_search_result(
            concept=concept,
            model_name=model_name,
            description=description,
            similarity_score=confidence,
            source=source,
        )

        model_payload = {
            "uid": metadata.get("name", concept.title()).replace(" ", "_").lower(),
            "name": model_name,
            "description": description,
            "viewer": hybrid_result.get("model_url"),
            "isDownloadable": True,
            "score": confidence,
        }

        return {
            "type": hybrid_result.get("type", "retrieved"),
            "model_url": hybrid_result.get("model_url"),
            "metadata": metadata,
            "data": model_payload,
            "ai_overview": ai_overview,
        }

    save_search_result(
        concept=concept,
        model_name="fallback_primitive",
        description="Geometric primitive fallback",
        similarity_score=0.0,
        source="internal",
    )

    return {
        "type": "generated",
        "model_url": None,
        "metadata": {
            "source": "primitive_fallback",
            "confidence_score": 0.0,
            "name": concept.title(),
            "description": "Primitive fallback representation",
            "tags": [],
            "format": "none",
        },
        "shapes": hybrid_result.get("shapes", generate_fallback(concept)),
        "ai_overview": ai_overview,
    }

@app.post("/upload")
async def handle_image_upload(file: UploadFile = File(...)):
    """Receives an image, runs local inference to determine the concept string, 
    and returns it so the frontend can trigger the pipeline to generate it."""
    image_bytes = await file.read()
    concept_label = classify_image(image_bytes)
    return {"concept": concept_label}


@app.post("/agent/ask")
def ask_agent(payload: AgentQuestionRequest):
    concept = (payload.concept or "").strip()
    question = (payload.question or "").strip()
    model_name = (payload.model_name or "").strip() or None

    if not concept:
        return {"answer": "Please provide a concept first.", "source": "agent"}
    if not question:
        return {"answer": "Please ask a question for the AI agent.", "source": "agent"}

    free_ai_answer = _ask_free_ai(
        concept=concept,
        question=question,
        model_name=model_name,
    )

    if free_ai_answer:
        answer = _clean_agent_answer_text(free_ai_answer)
        source = "free_ai"
    else:
        wiki_context = get_wikipedia_summary(concept, max_sentences=5)
        if not wiki_context and model_name and _normalize_text(model_name) != _normalize_text(concept):
            wiki_context = get_wikipedia_summary(model_name, max_sentences=5)
        fallback_answer = _compose_agent_answer(concept, model_name, question, wiki_context)
        answer = _clean_agent_answer_text(fallback_answer)
        source = "wikipedia_fallback"

    return {
        "answer": answer,
        "source": source,
        "used_free_ai": bool(free_ai_answer),
        "concept": concept,
        "model_name": model_name,
    }


@app.get("/ml/status")
def ml_status():
    return get_ml_status()
