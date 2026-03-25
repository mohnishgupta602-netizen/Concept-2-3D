# Production Deployment Guide

This guide deploys the full stack (frontend + backend + persistence) using Docker Compose.

## Architecture

- `web` service: Nginx serving Vite build and reverse-proxying `/api` and `/models` to backend
- `backend` service: FastAPI app via Gunicorn+Uvicorn workers
- Persistent data on host:
  - `backend/chroma_db_final`
  - `backend/models`
  - `backend/reviews.db`

## 1) Server prerequisites

Install Docker and Docker Compose plugin on your VPS.

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Log out/in after adding yourself to docker group.

## 2) Clone and configure

```bash
git clone <your-repo-url>
cd 3d-models
cp .env.production.example .env
cp backend/.env.example backend/.env
```

Update values in:

- `.env`:
  - `ALLOWED_ORIGINS=https://your-domain.com`
  - `APP_PORT=80`
- `backend/.env`:
  - `GROQ_API_KEY`
  - `GEMINI_API_KEY` (optional)
  - `SKETCHFAB_API_TOKEN`
  - `TRIPO3D_API_KEY` (optional)

## 3) Ensure index and persistence files exist

Make sure these exist before first boot:

- `backend/models/high_probability_model_index.json`
- `backend/reviews.db` (will auto-create if missing)

Build or refresh the index if needed:

```bash
cd backend
python3 build_category_model_index.py --target 3000 --per-query 48
cd ..
```

## 4) Launch

```bash
docker compose --env-file .env up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f web
```

## 5) Verify

- Open `http://<server-ip>`
- API health check:

```bash
curl -s -X POST "http://<server-ip>/api/intent" \
  -H "Content-Type: application/json" \
  -d '{"query":"solar system"}'
```

## 6) TLS (recommended)

Use Cloudflare proxy or add host-level Nginx/Caddy with Let's Encrypt in front of this stack.

## 7) Updates

```bash
git pull
docker compose --env-file .env up -d --build
```

## 8) Backups

Backup regularly:

- `backend/reviews.db`
- `backend/chroma_db_final/`
- `backend/models/high_probability_model_index.json`

Example:

```bash
tar -czf backup-$(date +%F).tar.gz backend/reviews.db backend/chroma_db_final backend/models/high_probability_model_index.json
```
