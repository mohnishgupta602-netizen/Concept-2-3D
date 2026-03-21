# Concept3D Generative

Concept3D Generative is a hybrid Concept-to-3D web app. It accepts text or image input, retrieves high-quality existing assets when possible, and falls back to generation when retrieval confidence is low.

## Core Highlights

- Hybrid pipeline: retrieval first, generation fallback
- Multi-source adapters: BlenderKit, Sketchfab, Poly-compatible archives
- Composite relevance ranking (semantic + token + phrase + quality)
- Local backend proxy serving `.glb` to avoid CORS issues
- ML fallback pipeline support: Stable Diffusion + OpenLRM bridge
- Interactive React 3D viewer + concept Q&A sidebar

## Repository Layout

```text
concept3d/
  backend/
    main.py
    hybrid_pipeline.py
    generative_stack.py
    requirements.txt
    requirement.txt
    models/
    ml/
  frontend/
    package.json
    src/
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm
- BlenderKit API key

## Environment Setup

Create `concept3d/backend/.env` (this file is ignored by git):

```env
BLENDERKIT_API_KEY=your_blenderkit_api_key
MONGO_URI=mongodb://localhost:27017/

FREE_AI_API_PROVIDER=openrouter
FREE_AI_API_KEY=your_openrouter_key
FREE_AI_API_MODEL=openai/gpt-oss-20b:free
FREE_AI_API_URL=https://openrouter.ai/api/v1/chat/completions

SKETCHFAB_API_TOKEN=
POLY_ARCHIVE_FEED_URL=
MODEL_CONFIDENCE_THRESHOLD=0.56

GENERATOR_ENABLED=true
GENERATOR_DEVICE=auto
GENERATOR_MAX_SECONDS=240
SD_MODEL_ID=runwayml/stable-diffusion-v1-5
SD_NUM_STEPS=20
SD_IMAGE_WIDTH=512
SD_IMAGE_HEIGHT=512
SD_GUIDANCE_SCALE=6.5

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

- `GET /visualize?concept=<text>`
  - Returns `type: retrieved | generated`
  - Returns `model_url`, `metadata`, and `data.viewer` for frontend compatibility
- `POST /upload`
  - Image upload and concept classification
- `POST /agent/ask`
  - Concept Q&A agent response
- `GET /ml/status`
  - Reports ML readiness and cache status

## Requirement Files

- `concept3d/backend/requirements.txt` is the canonical backend dependency file.
- `concept3d/backend/requirement.txt` is kept in sync for compatibility with earlier scripts.

## GitHub Push Readiness Checklist

- Ensure `.env` contains no placeholder secrets before running locally.
- Do not commit API keys or model weights.
- Confirm ignored heavy paths are excluded:
  - `concept3d/backend/models/*.glb`
  - `concept3d/backend/ml/OpenLRM/`
  - `concept3d/backend/ml/cache/`
  - `concept3d/backend/ml/hf_cache/`

Recommended push flow:

```powershell
git status
git add .
git commit -m "docs: update README and backend requirements for hybrid+ML pipeline"
git push origin main
```

## How to Use & Run

- **Quickstart (development)**: start the backend and frontend as shown in the "Local Run (Windows)" section. Once both are running, open the frontend at `http://127.0.0.1:3000` and use the UI to submit text or image concepts.

- **API quick test (PowerShell)** — get a visualization for a concept:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/visualize?concept=red+vintage+chair" -Method Get | ConvertTo-Json -Depth 5
```

- **Download generated GLB (example)** — the API response includes `model_url`. Use the URL to download the `.glb`:

```powershell
#$resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/visualize?concept=red+vintage+chair"
#Invoke-WebRequest -Uri $resp.model_url -OutFile generated.glb
```

## Installing / Cloning OpenLRM into `ml`

The backend expects an OpenLRM working copy inside the `concept3d/backend/ml` directory. Clone the repository into that folder and follow any OpenLRM-specific setup instructions (models, configs) there.

Replace `<OPENLRM_REPO_URL>` with the official OpenLRM GitHub URL you intend to use.

```powershell
cd concept3d\backend\ml
git clone <OPENLRM_REPO_URL> OpenLRM
# Example (replace with the correct upstream URL):
# git clone https://github.com/your-org/OpenLRM.git OpenLRM

# After cloning, ensure the repo and model paths match the .env settings, e.g.:
# OPENLRM_REPO_DIR=./ml/OpenLRM
# OPENLRM_INFER_CONFIG=./configs/infer-s.yaml
# OPENLRM_MODEL_NAME=zxhezexin/openlrm-obj-small-1.1
```

Notes:
- Do not commit the OpenLRM model weights or large cache files into git. Keep them under `concept3d/backend/ml` which is ignored by the repository.
- If you need to fetch pretrained OpenLRM weights from Hugging Face or another remote, follow the OpenLRM repository instructions and set `OPENLRM_MODEL_NAME` in `.env` accordingly.
