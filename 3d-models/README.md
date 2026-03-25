# Concept3D

Concept3D is a full-stack text-to-3D exploration app with multi-source model search, quality ranking, realistic fallback generation, labeling, narration, chat, and reviews.

## Project Structure

- `frontend/`: React + Vite UI
- `backend/`: FastAPI APIs for intent parsing, search/ranking, fallback, chat, and reviews

## Local Development

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill API keys in .env
python3 main.py
```

Backend runs at `http://127.0.0.1:8000`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://127.0.0.1:5173`.

## Deployment

Production deployment files are included:

- `docker-compose.yml`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `DEPLOYMENT.md`

Use `DEPLOYMENT.md` for complete deployment instructions.

## Notes

- `backend/models/high_probability_model_index.json` is used for category-index retrieval quality.
- Reviews are stored in `backend/reviews.db` (local persistence).
- Cache is stored in backend Chroma directories.