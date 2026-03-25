# Concept3D: AI-Powered 3D Model Generation Pipeline

Concept3D is an intelligent system that bridges abstract text concepts with spatial reality. It provides a real-time, three-column interface for generating, searching, and exploring 3D models with an integrated AI Design Assistant.

## 🚀 Features

- **Multi-Source 3D Search**: Integrated with Tripo3D (Generative AI), Sketchfab, and Poly Haven.
- **Smart Ranking System**: Automatically sorts models based on quality, popularity (likes/views), and AI confidence.
- **2D Concept Fallback**: If no 3D model is found, the system generates a high-fidelity 2D concept illustration using Gemini and Pollinations AI.
- **AI Design Assistant**: A Groq-powered chatbot (Llama 3.3) that helps you analyze and interact with the current 3D model.
- **Modern Three-Column Layout**: 
  - **Left**: Model selection and search results.
  - **Center**: High-performance 3D viewer (React Three Fiber).
  - **Right**: AI Chat interface for context-aware support.

## 🛠️ Setup Instructions

### Prerequisites
- Python 3.9+
- Node.js 18+
- API Keys: Gemini, Groq, Tripo3D (optional), Sketchfab (optional).

### Backend Setup
1. Navigate to the `backend` directory.
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: .\venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file based on `.env.example` (or the values provided in this setup) and add your API keys.
5. Start the server:
   ```bash
   python main.py
   ```

### Frontend Setup
1. Navigate to the `frontend` directory.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```

## 🧪 Tech Stack

- **Frontend**: Vite, React, React Three Fiber, Tailwind CSS, Lucide React.
- **Backend**: FastAPI, Groq SDK, Gemini (Google Generative AI), ChromaDB (Vector Search).
- **APIs**: Tripo3D, Sketchfab, Poly Haven, Pollinations AI.

---
Created with ❤️ for the 3D Generation Community.



Use these on macOS (open 2 terminal tabs/windows):

1. Backend (Terminal 1)

cd "/Users/ishniaizhar/Documents/mnnit project/3d-models/backend"
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt

Then create your .env file in backend and add keys (Gemini, Groq, etc.), then run:

python3 main.py

2. Frontend (Terminal 2)

cd "/Users/ishniaizhar/Documents/mnnit project/3d-models/frontend"
npm install
npm run dev

3. Open app

Frontend: http://localhost:5173  
Backend (default FastAPI): http://localhost:8000

Mac-specific note:
The activation command on macOS is:
source venv/bin/activate

(Windows uses .\venv\Scripts\activate, so you can ignore that line in the README.)