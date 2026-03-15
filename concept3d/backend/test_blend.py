import requests
import os
import subprocess
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('BLENDERKIT_API_KEY')
headers = {'Authorization': f'Bearer {API_KEY}'}

# Get Cartoon Car model
search_url = 'https://www.blenderkit.com/api/v1/search/?query=cartoon+wagon+car+is_free:true&asset_type=model'
data = requests.get(search_url, headers=headers).json()['results'][0]

# Find the .blend file
blend_file = next(f for f in data['files'] if f['fileType'] == 'blend')
dl_url = f"https://www.blenderkit.com/api/v1/downloads/{blend_file['id']}/?scene_uuid=00000000-0000-0000-0000-000000000000"

print("Requesting .blend download URL...")
dl_res = requests.get(dl_url, headers=headers).json()
file_path = dl_res['filePath']

print(f"Downloading .blend file from {file_path[:30]}...")
blend_bin = requests.get(file_path).content
with open("test.blend", "wb") as f:
    f.write(blend_bin)
    
print("Downloaded test.blend. Running conversion...")
blender_exe = r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
subprocess.run([blender_exe, "-b", "test.blend", "--python", "export_glb.py", "--", "test.glb"], check=True)
print("Conversion complete.")
