import requests
import os
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

BLENDERKIT_API_KEY = os.getenv("BLENDERKIT_API_KEY")

def search_models(query):
    # This now ACTS as the BlenderKit search engine instead of Tripo3D.
    print(f"Requesting BlenderKit to find: {query}")
    
    headers = {
        "Authorization": f"Bearer {BLENDERKIT_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        # Step 1: Search the BlenderKit Library
        query_encoded = urllib.parse.quote(f"{query}+is_free:true")
        search_url = f"https://www.blenderkit.com/api/v1/search/?query={query_encoded}&asset_type=model"
        
        res = requests.get(search_url, headers=headers)
        res.raise_for_status()
        results = res.json().get("results", [])
        
        if not results:
            print("No results found on BlenderKit.")
            return []
            
        # Step 2: Find the top match that has a WebGL ready (.glb/.gltf) format
        top_match = None
        target_gltf_file = None
        
        for result in results:
            for fileinfo in result.get("files", []):
                if fileinfo.get("fileType") in ["gltf", "gltf_godot"]:
                    top_match = result
                    target_gltf_file = fileinfo
                    break
            if top_match:
                break
                
        if not top_match or not target_gltf_file:
            print(f"BlenderKit has models for '{query}', but none are in GLTF/GLB web-browser format yet.")
            return []
            
        # Step 3: Fetch the direct download URL for the GLTF
        download_id = target_gltf_file.get("id")
        
        # A scene_uuid is strictly required by BlenderKit API.
        import uuid
        dummy_scene_uuid = str(uuid.uuid4())
        download_endpoint = f"https://www.blenderkit.com/api/v1/downloads/{download_id}/?scene_uuid={dummy_scene_uuid}"
        
        print(f"Found GLB on BlenderKit (ID {download_id}). Requesting download URL...")
        dl_res = requests.get(download_endpoint, headers=headers)
        dl_res.raise_for_status()
        dl_data = dl_res.json()
        
        final_file_url = dl_data.get("filePath")
        if not final_file_url:
            print("BlenderKit did not return a valid file path for the model.")
            return []
            
        MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
        os.makedirs(MODELS_DIR, exist_ok=True)
        
        uid = top_match.get("id")
        model_filename = f"{uid}.glb"
        model_path = os.path.join(MODELS_DIR, model_filename)
        
        if not os.path.exists(model_path):
            print(f"Downloading model locally to bypass CORS -> {model_filename}")
            model_bin = requests.get(final_file_url).content
            with open(model_path, "wb") as f:
                f.write(model_bin)
        
        print(f"Success! Proxied and downloaded BlenderKit model.")
        
        # Return the unified format that app expects
        return [{
            "uid": uid,
            "name": top_match.get("name", query.title()),
            "description": top_match.get("description", f"BlenderKit Asset: {query.title()}"),
            "viewer": f"http://localhost:8000/models/{model_filename}",
            "isDownloadable": top_match.get("isFree", True),
            "score": 1.0 # Force Top 1 pick
        }]
        
    except Exception as e:
        print(f"BlenderKit API Error: {e}")
        return []

