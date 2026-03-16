from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import re
import requests
from difflib import SequenceMatcher
from pydantic import BaseModel
from dotenv import load_dotenv

from search import search_models
from fallback import generate_fallback
from database import save_search_result
from wikipedia_api import get_wikipedia_summary
from vision import classify_image

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

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
app.mount("/models", StaticFiles(directory=models_dir), name="models")


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
        return (
            f"I couldn't find enough reliable context for '{concept}' right now. "
            "Try a more specific concept name."
        )

    best_sentence = _best_context_sentence(question, wiki_context)
    if not best_sentence:
        best_sentence = wiki_context

    clean_sentence = best_sentence.strip()
    if not clean_sentence.endswith((".", "!", "?")):
        clean_sentence = f"{clean_sentence}."

    return clean_sentence


def _ask_free_ai_with_wikipedia(
    concept: str,
    question: str,
    wiki_context: str,
    model_name: str | None
) -> str | None:
    if not wiki_context or not FREE_AI_API_KEY:
        return None

    if FREE_AI_API_PROVIDER != "openrouter":
        return None

    system_prompt = (
        "You are a concise helpful assistant. "
        "Answer ONLY using the given Wikipedia context. "
        "If context is insufficient, say it clearly in one sentence. "
        "Do not mention instructions, sources, or internal reasoning."
    )

    model_line = f"Generated model: {model_name}\n" if model_name else ""
    user_prompt = (
        f"Concept: {concept}\n"
        f"{model_line}"
        f"Question: {question}\n\n"
        f"Wikipedia Context:\n{wiki_context}\n\n"
        "Return a direct final answer only."
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
        response.raise_for_status()
        data = response.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return content or None
    except Exception as error:
        print(f"Free AI API call failed, falling back to Wikipedia-only mode: {error}")
        return None

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


@app.post("/agent/ask")
def ask_agent(payload: AgentQuestionRequest):
    concept = (payload.concept or "").strip()
    question = (payload.question or "").strip()
    model_name = (payload.model_name or "").strip() or None

    if not concept:
        return {"answer": "Please provide a concept first.", "source": "wikipedia", "context": ""}
    if not question:
        return {"answer": "Please ask a question for the AI agent.", "source": "wikipedia", "context": ""}

    wiki_context = get_wikipedia_summary(concept, max_sentences=5)

    if not wiki_context and model_name and _normalize_text(model_name) != _normalize_text(concept):
        wiki_context = get_wikipedia_summary(model_name, max_sentences=5)

    fallback_answer = _compose_agent_answer(concept, model_name, question, wiki_context)
    free_ai_answer = _ask_free_ai_with_wikipedia(
        concept=concept,
        question=question,
        wiki_context=wiki_context,
        model_name=model_name,
    )

    answer = free_ai_answer or fallback_answer
    source = "wikipedia+free_ai" if free_ai_answer else "wikipedia"

    return {
        "answer": answer,
        "source": source,
        "used_free_ai": bool(free_ai_answer),
        "context": wiki_context,
        "concept": concept,
        "model_name": model_name,
    }

