# Concept3D Generative

Concept3D Generative is a hybrid Concept-to-3D web app that accepts text or image input, retrieves high-quality existing 3D assets when possible, and falls back to AI generation when retrieval confidence is low. Features intelligent search powered by Gemini API, AI model part labeling, and user feedback-driven model improvement.

## Core Highlights

- **Hybrid Pipeline**: Retrieval first (BlenderKit → Sketchfab → Poly Pizza/Archive), then ML generation (Stable Diffusion + OpenLRM), finally procedural fallback
- **AI-Powered Search**: Gemini API integration for query enhancement, semantic similarity scoring, and intelligent ranking
- **Multi-Source Adapters**: BlenderKit (priority), Sketchfab, Poly Archive, Poly Pizza with source-specific optimization
- **AI Part Labeling**: Automatic 3D model part identification using Gemini API
- **User Feedback System**: 1-5 star ratings (0.5 increments) with recursive training data collection
- **Smart Caching**: High-rated models (≥3.5 stars, 3+ reviews) automatically cached for faster retrieval
- **Composite Relevance Ranking**: Multi-factor scoring (semantic 45% + token overlap 30% + phrase match 15% + quality 10%)
- **Local Backend Proxy**: Serves `.glb` files to avoid CORS issues
- **Interactive React 3D Viewer**: React Three Fiber with concept Q&A sidebar

## Repository Layout

```text
concept3d/
  backend/
    main.py                 # FastAPI endpoints
    hybrid_pipeline.py      # Search & retrieval logic
    gemini_search.py        # Gemini API integration
    model_labeling.py       # AI part labeling
    generative_stack.py     # ML generation pipeline
    database.py             # MongoDB feedback & training storage
    sketchfab_scraper.py    # Sketchfab utilities
    fallback.py             # Procedural 3D generation
    models/                 # Downloaded/generated .glb files
    ml/                     # OpenLRM and ML models
    .env                    # Environment variables
  frontend/
    package.json
    src/
      App.js                # Main React app with rating UI
      ModelViewer.js        # 3D viewer component
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm
- MongoDB (local or cloud)
- API Keys:
  - BlenderKit API key
  - Gemini API key (for AI search & labeling)
  - Sketchfab API token (optional)

## Environment Setup

Create `concept3d/backend/.env` (this file is ignored by git):

```env
# Required
BLENDERKIT_API_KEY=your_blenderkit_api_key
GEMINI_API_KEY=your_gemini_api_key
MONGO_URI=mongodb://localhost:27017/

# Optional - for OpenRouter AI agent
FREE_AI_API_PROVIDER=openrouter
FREE_AI_API_KEY=your_openrouter_key
FREE_AI_API_MODEL=openai/gpt-oss-20b:free
FREE_AI_API_URL=https://openrouter.ai/api/v1/chat/completions

# Optional - additional sources
SKETCHFAB_API_TOKEN=
POLY_ARCHIVE_FEED_URL=

# Model confidence threshold (0-1)
MODEL_CONFIDENCE_THRESHOLD=0.56

# ML Generation settings
GENERATOR_ENABLED=true
GENERATOR_DEVICE=auto
GENERATOR_MAX_SECONDS=240
SD_MODEL_ID=runwayml/stable-diffusion-v1-5
SD_NUM_STEPS=20
SD_IMAGE_WIDTH=512
SD_IMAGE_HEIGHT=512
SD_GUIDANCE_SCALE=6.5

# OpenLRM paths
OPENLRM_REPO_DIR=./ml/OpenLRM
OPENLRM_INFER_CONFIG=./configs/infer-s.yaml
OPENLRM_MODEL_NAME=zxhezexin/openlrm-obj-small-1.1
```

## Local Run (Windows)

From repository root:

### Backend terminal

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd concept3d\backend
..\..\.venv\Scripts\python.exe -m pip install -U pip
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend terminal

```powershell
cd concept3d\frontend
npm install
npm start
```

Open:

- Frontend: http://127.0.0.1:3000
- Backend docs: http://127.0.0.1:8000/docs

## API Endpoints

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/visualize?concept=<text>` | GET | Search and retrieve/generate 3D model |
| `/upload` | POST | Image upload and concept classification |
| `/agent/ask` | POST | Concept Q&A agent response |
| `/ml/status` | GET | Reports ML readiness and cache status |

### Feedback & Rating

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/feedback` | POST | Submit rating (1-5 stars, 0.5 increments) |
| `/feedback/{model_id}` | GET | Get average rating and feedback history |

### AI Part Labeling

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/part-labels/{model_id}` | GET | Get part labels (optional: `?concept=X&auto_generate=true`) |
| `/part-labels/{model_id}` | POST | Save or auto-generate labels |

## Usage Examples

### Quick Test (PowerShell)

```powershell
# Search for a 3D model
Invoke-RestMethod -Uri "http://127.0.0.1:8000/visualize?concept=red+vintage+chair" -Method Get | ConvertTo-Json -Depth 5

# Submit feedback/rating
Invoke-RestMethod -Uri "http://127.0.0.1:8000/feedback" -Method Post -ContentType "application/json" -Body '{"model_id": "chair_123", "user_id": "user1", "rating": 4.5, "comment": "Great model!"}'

# Auto-generate part labels
Invoke-RestMethod -Uri "http://127.0.0.1:8000/part-labels/chair_123?concept=red+vintage+chair&auto_generate=true" -Method Get
```

## How It Works

### Search Pipeline

1. **Query Enhancement**: Gemini API expands queries (e.g., "Solar System" → "sun", "planet", "orbit")
2. **Multi-Source Search**: Queries BlenderKit (priority), Sketchfab, Poly Archive, Poly Pizza
3. **Scoring**: Each candidate scored on semantic similarity, token overlap, phrase matching, source quality
4. **Ranking**: Top 5 candidates get Gemini-powered semantic scoring, then re-ranked
5. **Download**: Best candidate downloaded and cached

### Fallback Chain

If no suitable model found:
1. **ML Generation**: Stable Diffusion → OpenLRM → GLB
2. **Procedural Fallback**: Trimesh-generated primitives
3. **Primitive Shapes**: Basic cubes/spheres as last resort

### User Feedback & Training

- Ratings: 1-5 stars in 0.5 increments
- Auto-caching: Models with ≥3.5 average rating and 3+ reviews get cached
- Training data: All feedback stored for recursive model improvement
- Concept metrics: Historical quality tracked per concept

## Gemini API Features

- **Query Enhancement**: Expands concepts with related terms and categories
- **Semantic Scoring**: AI-powered similarity scoring for top candidates
- **Rate Limiting**: 1 second between requests with exponential backoff
- **Caching**: Similarity scores cached to reduce API calls

## Model Labeling

AI identifies and labels parts of 3D models:
- **Car**: body, wheel, door, window, headlight, bumper
- **House**: wall, roof, door, window, floor
- **Chair**: seat, backrest, leg, armrest, cushion
- **Human/Animal**: head, torso, arm, leg, etc.

## GitHub Push Readiness Checklist

- Ensure `.env` contains no placeholder secrets before running locally
- Do not commit API keys or model weights
- Confirm ignored paths are excluded:
  - `concept3d/backend/models/*.glb`
  - `concept3d/backend/ml/OpenLRM/`
  - `concept3d/backend/ml/cache/`
  - `concept3d/backend/ml/hf_cache/`

Recommended push flow:

```powershell
git status
git add .
git commit -m "feat: add Gemini search, AI labeling, user feedback"
git push origin main
```

## Installing OpenLRM (Optional - for ML generation)

```powershell
cd concept3d\backend\ml
git clone https://github.com/your-org/OpenLRM.git OpenLRM
```

Ensure paths match `.env` settings for `OPENLRM_REPO_DIR`, `OPENLRM_INFER_CONFIG`, and `OPENLRM_MODEL_NAME`.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "[Gemini] No API key configured" | Add `GEMINI_API_KEY` to `.env` |
| 429 Rate Limit errors | Gemini has rate limiting; system will retry with backoff |
| Low quality results | Increase `MODEL_CONFIDENCE_THRESHOLD` in `.env` |
| CORS errors | Backend proxy handles this; ensure backend is running |
