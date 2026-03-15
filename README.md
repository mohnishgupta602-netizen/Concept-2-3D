# Concept3D Generative

Welcome to **Concept3D Generative** – a zero-dependency, true Generative 3D AI application powered by the BlenderKit API.

## Overview

Concept3D Generative allows users to seamlessly generate, visualize, and interact with 3D models driven by Artificial Intelligence. The platform takes simple text prompts or image uploads, converts them into detailed 3D files (like `.glb`), and provides a beautiful interface to view and interact with the resulting geometry right in the browser.

### Key Features

* **Text-to-3D Generation:** Enter a prompt (e.g., "A flying car", "Futuristic Chair"), and the system leverages the BlenderKit REST API to search for and retrieve pre-converted 3D models in real time.
* **Image-to-AI Prompting:** Upload an image (`.png`, `.jpg`, `.webp`). A lightweight Vision Transformer (`google/vit-base-patch16-224`) classifies the image and automatically feeds the inferred concept into the 3D generation pipeline.
* **Interactive 3D Viewer:** Built with React and modern 3D viewing libraries, allowing you to rotate, zoom, and explore the generated models.
* **Fallback Geometry:** If a specific model generation fails, the system provides a sleek, fallback geometric representation based on standard shapes.
* **Wikipedia Integration:** Automatically pulls contextual information and summaries about the requested concept directly from Wikipedia.
* **Audio Synthesis:** Features built-in Text-to-Speech (TTS) explanations of the generated 3D models. Supports both English (`en-US`) and Hindi (`hi-IN`).
* **Direct Downloads:** Export generated `.glb` models instantly for use in external 3D software (Blender, Unity, etc.).

## Project Structure

* **`/backend`**: Contains the core Python API (FastAPI) responsible for bridging requests to the BlenderKit API, downloading `.glb` models locally to bypass CORS, performing image classification using the HuggingFace `transformers` library, querying Wikipedia for contextual info, and handling database operations.
* **`/frontend`**: A React-based Single Page Application (SPA) offering a sleek, glassmorphic UI, model viewers, animated gradients, and seamless API communication with the backend.

## Tech Stack

* **Frontend:** React, Vanilla CSS (with modern variables & keyframes), Web Speech API.
* **Backend:** Python (FastAPI), Transformers (Vision classification), PIL, Wikipedia API.
* **3D Asset Integration:** BlenderKit API for searching and retrieving high-quality, pre-converted 3D models.

## Getting Started

### 1. Start the Backend Server (FastAPI)

Open your terminal and start the Python backend server:

```bash
# Navigate to the backend directory
cd concept3d/backend

# Activate the virtual environment (Windows)
venv\Scripts\activate

# Install any missing dependencies (if this is your first run)
pip install -r requirements.txt

# Start the server (runs on port 8000 by default)
uvicorn main:app --reload
```

### 2. Start the Frontend Server (React)

Open a **new terminal tab/window** and start the frontend development server:

```bash
# Navigate to the frontend directory
cd concept3d/frontend

# Install node dependencies (if this is your first run)
npm install

# Start the React development server
npm start
```

The application will now be running at `http://localhost:3000` and successfully communicating with your AI backend at `http://localhost:8000`.

---
*Created as a demonstration of advanced AI integrations and full-stack generative 3D capabilities.*
