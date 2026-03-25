# MNNIT Project Workspace

This repository contains three project folders in a single monorepo-style structure:

- `3d-models`
- `Concept-2-3D`
- `target-repo`

## Notes

- Local virtual environments, node modules, caches, and large generated model artifacts are excluded from git via `.gitignore`.
- Deployment and project-specific instructions are available inside each folder.

## Quick Start (example)

### 3d-models backend

```bash
cd 3d-models/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### 3d-models frontend

```bash
cd 3d-models/frontend
npm install
npm run dev
```
