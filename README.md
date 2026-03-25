# Concept-2-3D

Concept-2-3D is a hybrid Concept-to-3D platform that accepts text or image input, searches multiple 3D sources, and falls back to generated procedural blueprints when retrieval confidence is low.

It combines:

- FastAPI backend for search, ranking, feedback, and model serving
- React frontend for interactive 3D viewing
- Gemini-assisted query enhancement and labeling support
- Feedback + RAG-based improvement pipeline

## Repository Layout

This repository currently contains three top-level folders. The main Concept-2-3D app is under `Concept-2-3D/concept3d`.

```text
.
|- Concept-2-3D/
|  |- concept3d/
|  |  |- backend/
|  |  |- frontend/
|- 3d-models/
|- target-repo/
```

## Core Features

- Hybrid retrieval plus fallback generation pipeline
- Multi-source model search and scoring
- Local model proxying via `/models/*` to avoid CORS issues
- User feedback endpoints and rating-aware caching
- RAG-assisted enhancement endpoints for future search decisions
- AI part labeling support for model components

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- npm
- API keys (as needed): Gemini, BlenderKit, optional Sketchfab

## Environment Setup

Create a backend environment file at `Concept-2-3D/concept3d/backend/.env`.

Example:

```env
BLENDERKIT_API_KEY=your_blenderkit_api_key
GEMINI_API_KEY=your_gemini_api_key

# Optional AI provider for /agent/ask style workflows
FREE_AI_API_PROVIDER=openrouter
FREE_AI_API_KEY=your_api_key
FREE_AI_API_MODEL=openai/gpt-oss-20b:free
FREE_AI_API_URL=https://openrouter.ai/api/v1/chat/completions

# Optional tokens
SKETCHFAB_API_TOKEN=
```

## Run Locally (macOS/Linux)

Backend:

```bash
cd Concept-2-3D/concept3d/backend
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirement.txt
uvicorn main:app --host 0.0.0.0 --port 8010 --reload
```

Frontend:

```bash
cd Concept-2-3D/concept3d/frontend
npm install
npm start
```

Open:

- Frontend: http://localhost:3000
- Backend docs: http://localhost:8010/docs

## Main API Endpoints

- `GET /visualize?concept=<text>`
- `POST /upload`
- `POST /feedback`
- `GET /feedback/{model_id}`
- `GET /part-labels/{model_id}`
- `POST /part-labels/{model_id}`
- `GET /rag/enhance/{concept}`
- `POST /rag/feedback`

## Notes

- `requirement.txt` (singular) is the backend dependency file in this project.
- Large generated files, model caches, and virtual environments are excluded via `.gitignore`.
- If a model is missing, the fallback pipeline may return primitive blueprint-style output.

## Troubleshooting

- If frontend cannot reach backend, verify backend port and update any base URL config.
- If AI features are unavailable, confirm environment keys are set in backend `.env`.
- If model files fail to load, ensure backend is running and `/models/*` paths are accessible.
