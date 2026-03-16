# Concept3D Generative

Concept3D Generative is a full-stack 3D idea explorer that turns text or image concepts into interactive 3D model experiences.

It combines BlenderKit search, local model proxying, fallback geometry, Wikipedia grounding, voice narration, and a sidebar AI Q&A agent.

## Features

- Text-to-3D concept generation using BlenderKit assets
- Improved relevance scoring (less random model matches)
- Automatic fallback geometry when no strong model match exists
- Image-to-concept prompt detection using a vision classifier
- Interactive web 3D viewer with orbit controls
- Wikipedia concept overview panel
- Wikipedia-grounded Q&A sidebar agent (`/agent/ask`)
- Audio explanation (English + Hindi)
- Direct `.glb` download for generated models
- Subtle animated 3D background lighting in the UI

## Project Structure

```text
concept3d/
	backend/
		main.py              # FastAPI app + endpoints
		search.py            # BlenderKit search and ranking logic
		vision.py            # Image classification
		wikipedia_api.py     # Wikipedia summary helper
		fallback.py          # Fallback shapes
		database.py          # Optional MongoDB logging
		models/              # Downloaded .glb files served locally
	frontend/
		src/
			App.js             # Main UI + sidebar agent
			ModelViewer.js     # 3D rendering
			index.css          # Styling and background effects
```

## Tech Stack

- Frontend: React, Three.js (`@react-three/fiber`, `@react-three/drei`), CSS
- Backend: FastAPI, Requests, Transformers, Pillow, Wikipedia
- 3D Source: BlenderKit API

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm
- BlenderKit API key

## Environment Variables

Create `concept3d/backend/.env`:

```env
BLENDERKIT_API_KEY=your_blenderkit_api_key_here
MONGO_URI=mongodb://localhost:27017/
FREE_AI_API_PROVIDER=openrouter
FREE_AI_API_KEY=your_openrouter_key_here
FREE_AI_API_MODEL=openai/gpt-oss-20b:free
FREE_AI_API_URL=https://openrouter.ai/api/v1/chat/completions
```

Notes:
- `BLENDERKIT_API_KEY` is required for model search/download.
- MongoDB is optional; app runs without it.
- `FREE_AI_API_KEY` enables free-tier AI answers in `/agent/ask`.
- If free AI is unavailable, backend automatically falls back to Wikipedia-only answer logic.

## Quick Start (Windows)

If you only want to run the project quickly, do this from the repo root:

### Terminal 1 (Backend)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd concept3d\backend
..\..\.venv\Scripts\python.exe -m pip install -U pip
..\..\.venv\Scripts\python.exe -m pip install fastapi uvicorn requests pymongo wikipedia transformers pillow python-multipart python-dotenv torch
..\..\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

### Terminal 2 (Frontend)

```powershell
cd concept3d\frontend
npm install
npm start
```

Open:
- Frontend: http://127.0.0.1:3000
- Backend docs: http://127.0.0.1:8000/docs

If both open successfully, the project is running.

## Setup & Run (Windows)

From repository root (`Concept-2-3D`):

### 1) Create/activate Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install backend dependencies

```powershell
cd concept3d\backend
..\..\.venv\Scripts\python.exe -m pip install -U pip
..\..\.venv\Scripts\python.exe -m pip install fastapi uvicorn requests pymongo wikipedia transformers pillow python-multipart python-dotenv torch
```

### 3) Start backend

```powershell
cd concept3d\backend
..\..\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Backend URL: `http://127.0.0.1:8000`
Docs: `http://127.0.0.1:8000/docs`

### 4) Install frontend dependencies

Open a new terminal:

```powershell
cd concept3d\frontend
npm install
```

### 5) Start frontend

```powershell
cd concept3d\frontend
npm start
```

Frontend URL: `http://127.0.0.1:3000`

## API Endpoints

- `GET /visualize?concept=<text>`
	- Returns either a model payload or fallback geometry
	- Includes `ai_overview` text from Wikipedia

- `POST /upload`
	- Multipart image upload
	- Returns detected concept label

- `POST /agent/ask`
	- Wikipedia-grounded Q&A endpoint
	- Uses free AI API (when configured) + strict context grounding
	- Returns `used_free_ai: true|false` to indicate if free API answered
	- Body:
		```json
		{
			"concept": "car",
			"question": "what is the work of a car?",
			"model_name": "Covered Car"
		}
		```

## Search Relevance Behavior

`backend/search.py` uses scoring to reduce random results:

- token matching on name/description/tags/category
- phrase and similarity boosts
- strict filtering for multi-word prompts
- fallback response when no relevant GLTF candidate is found

This avoids returning unrelated 3D assets for specific concepts.

## Troubleshooting

- `401` from BlenderKit:
	- Verify `BLENDERKIT_API_KEY` in `concept3d/backend/.env`

- Backend starts but no model appears:
	- Query may fail strict relevance; fallback geometry is expected behavior

- `/upload` returns weak concept:
	- Ensure `torch` + `transformers` installed in `.venv`

- Frontend source-map warnings:
	- Non-blocking warnings from third-party packages

- Port already in use:
	- Stop existing process on `8000`/`3000` and restart services

- Free AI API returns fallback only (`used_free_ai=false`):
	- Verify `FREE_AI_API_KEY` is valid
	- Check OpenRouter account privacy/guardrail settings
	- Restart backend after `.env` changes

## Future Improvements

- Add concept synonym expansion (`auto` → `car`, etc.)
- Persist Q&A conversation history by concept
- Add model quality metadata in UI

---

Built as a creative AI + 3D exploration project with FastAPI and React.
