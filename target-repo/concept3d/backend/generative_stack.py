import glob
import hashlib
import os
import shlex
import shutil
import subprocess
import sys
from typing import Any


try:
    import torch
except Exception:
    torch = None

try:
    from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline, EulerDiscreteScheduler
except Exception:
    StableDiffusionPipeline = None
    StableDiffusionXLPipeline = None
    EulerDiscreteScheduler = None
try:
    from diffusers import DPMSolverMultistepScheduler
except Exception:
    DPMSolverMultistepScheduler = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    from rembg import remove
except Exception:
    remove = None

try:
    import trimesh
except Exception:
    trimesh = None


_BACKEND_DIR = os.path.dirname(__file__)
_ML_DIR = os.path.join(_BACKEND_DIR, "ml")
_CACHE_DIR = os.path.join(_ML_DIR, "cache")
_IMAGE_DIR = os.path.join(_CACHE_DIR, "images")
_CLEAN_DIR = os.path.join(_CACHE_DIR, "clean")
_OPENLRM_DIR = os.path.join(_CACHE_DIR, "openlrm")
_HF_CACHE_DIR = os.path.join(_ML_DIR, "hf_cache")

os.environ.setdefault("HF_HOME", _HF_CACHE_DIR)
os.environ.setdefault("TRANSFORMERS_CACHE", _HF_CACHE_DIR)
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", _HF_CACHE_DIR)

_SD_PIPE = None
_SD_MODEL_ID_LOADED = None
_SD_MODEL_TYPE = None  # 'sd' or 'sdxl'


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _ensure_dirs() -> None:
    os.makedirs(_ML_DIR, exist_ok=True)
    os.makedirs(_CACHE_DIR, exist_ok=True)
    os.makedirs(_HF_CACHE_DIR, exist_ok=True)
    os.makedirs(_IMAGE_DIR, exist_ok=True)
    os.makedirs(_CLEAN_DIR, exist_ok=True)
    os.makedirs(_OPENLRM_DIR, exist_ok=True)


def _cache_key(prompt: str, model_id: str, steps: int, width: int, height: int) -> str:
    payload = f"{_normalize_text(prompt)}|{model_id}|{steps}|{width}|{height}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _resolve_device() -> str:
    configured = os.getenv("GENERATOR_DEVICE", "auto").strip().lower()
    if configured in {"cuda", "cpu"}:
        return configured

    if torch is not None and getattr(torch, "cuda", None) and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _get_sd_pipeline(model_id: str, device: str):
    global _SD_PIPE, _SD_MODEL_ID_LOADED, _SD_MODEL_TYPE

    if (StableDiffusionPipeline is None and StableDiffusionXLPipeline is None) or torch is None:
        return None

    if _SD_PIPE is not None and _SD_MODEL_ID_LOADED == model_id:
        return _SD_PIPE

    # Detect if using SDXL
    is_sdxl = "xl" in model_id.lower() or "sdxl" in model_id.lower()
    _SD_MODEL_TYPE = "sdxl" if is_sdxl else "sd"

    dtype = torch.float16 if device == "cuda" else torch.float32

    # Load appropriate pipeline
    if is_sdxl and StableDiffusionXLPipeline is not None:
        print(f"[SD] Loading SDXL model: {model_id}")
        pipe = StableDiffusionXLPipeline.from_pretrained(
            model_id,
            torch_dtype=dtype,
            use_safetensors=True,
            variant="fp16" if device == "cuda" else None
        )
    else:
        print(f"[SD] Loading SD 1.5 model: {model_id}")
        pipe = StableDiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=dtype,
            use_safetensors=True,
            safety_checker=None,
            requires_safety_checker=False
        )

    # Use EulerDiscreteScheduler for better quality
    try:
        if EulerDiscreteScheduler is not None and hasattr(pipe, 'scheduler'):
            pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config)
            print("[SD] Using EulerDiscreteScheduler for better quality")
    except Exception as e:
        print(f"[SD] Could not set Euler scheduler: {e}")
        # Fallback to DPM
        try:
            if DPMSolverMultistepScheduler is not None and hasattr(pipe, 'scheduler'):
                pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
        except Exception:
            pass

    # Memory optimizations
    if hasattr(pipe, "enable_attention_slicing"):
        pipe.enable_attention_slicing()
    if hasattr(pipe, "enable_vae_slicing"):
        pipe.enable_vae_slicing()
    if hasattr(pipe, "enable_xformers_memory_efficient_attention"):
        try:
            pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            pass

    if device == "cuda":
        if hasattr(pipe, "enable_model_cpu_offload"):
            pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to(device)
    else:
        pipe = pipe.to("cpu")

    _SD_PIPE = pipe
    _SD_MODEL_ID_LOADED = model_id
    return _SD_PIPE


def _generate_image(prompt: str, key: str) -> str | None:
    model_id = os.getenv("SD_MODEL_ID", "stabilityai/stable-diffusion-xl-base-1.0").strip()
    steps = int(os.getenv("SD_NUM_STEPS", "40"))
    width = int(os.getenv("SD_IMAGE_WIDTH", "768"))
    height = int(os.getenv("SD_IMAGE_HEIGHT", "768"))
    guidance_scale = float(os.getenv("SD_GUIDANCE_SCALE", "8.0"))
    
    # Enhanced negative prompt for 3D generation
    negative_prompt = os.getenv(
        "SD_NEGATIVE_PROMPT", 
        "text, watermark, logo, signature, low quality, blurry, deformed, cartoon, anime, painting, drawing, sketch, illustration, distorted, ugly, duplicate, multiple objects, cropped, out of frame, worst quality, low resolution"
    ).strip()
    
    num_candidates = int(os.getenv("SD_NUM_CANDIDATES", "2"))
    sd_seed = os.getenv("SD_SEED", "").strip()
    
    # OpenLRM-specific optimizations
    openlrm_optimized = _env_bool("SD_OPENLRM_OPTIMIZED", True)

    image_path = os.path.join(_IMAGE_DIR, f"{key}.png")
    if os.path.exists(image_path):
        return image_path

    device = _resolve_device()
    pipe = _get_sd_pipeline(model_id=model_id, device=device)
    if pipe is None:
        return None

    # Enhanced prompt engineering for 3D model generation
    if openlrm_optimized:
        # OpenLRM works best with clean, centered objects on neutral backgrounds
        prompt_final = (
            f"{prompt}, professional product photography, centered composition, "
            "clean white background, soft studio lighting from 45 degrees, "
            "photorealistic 3D render, high detail, sharp focus, "
            "ambient occlusion, physically based rendering, material definition, "
            "single object, isolated on white, orthographic perspective"
        )
    else:
        prompt_final = (
            f"{prompt}, highly detailed 3D model, photorealistic render, PBR materials, crisp geometry, "
            "studio lighting, 3/4 view and front view, neutral background, no text, no watermark"
        )

    # Prepare generator/seed
    generator = None
    try:
        if sd_seed:
            seed = int(sd_seed)
            gen_device = "cuda" if device == "cuda" else "cpu"
            generator = torch.Generator(device=gen_device)
            generator.manual_seed(seed)
    except Exception:
        generator = None

    # Use autocast on CUDA for faster mixed-precision inference
    images = None
    try:
        if device == "cuda":
            with torch.autocast("cuda"):
                output = pipe(
                    prompt=prompt_final,
                    negative_prompt=negative_prompt,
                    num_inference_steps=steps,
                    guidance_scale=guidance_scale,
                    width=width,
                    height=height,
                    num_images_per_prompt=num_candidates,
                    generator=generator,
                )
        else:
            output = pipe(
                prompt=prompt_final,
                negative_prompt=negative_prompt,
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height,
                num_images_per_prompt=num_candidates,
                generator=generator,
            )
        images = output.images
    except Exception as e:
        print(f"Stable Diffusion generation failed: {e}")
        return None

    # Pick first non-None image
    image = None
    if images:
        image = images[0]
    if image is None:
        return None
    image.save(image_path)
    return image_path


def _remove_background(image_path: str, key: str) -> str:
    clean_path = os.path.join(_CLEAN_DIR, f"{key}.png")
    if os.path.exists(clean_path):
        return clean_path

    if Image is None:
        return image_path

    if remove is None:
        shutil.copyfile(image_path, clean_path)
        return clean_path

    source_image = Image.open(image_path)
    clean_image = remove(source_image)
    clean_image.save(clean_path)
    return clean_path


def _run_openlrm(clean_image_path: str, key: str) -> str | None:
    repo_dir_env = os.getenv("OPENLRM_REPO_DIR", "").strip()
    if repo_dir_env:
        if os.path.isabs(repo_dir_env):
            repo_dir = repo_dir_env
        else:
            repo_dir = os.path.normpath(os.path.join(_BACKEND_DIR, repo_dir_env))
    else:
        repo_dir = os.path.join(_ML_DIR, "OpenLRM")

    launch_py = os.path.join(repo_dir, "openlrm", "launch.py")
    if not os.path.exists(launch_py):
        return None

    output_dir = os.path.join(_OPENLRM_DIR, key)
    os.makedirs(output_dir, exist_ok=True)

    infer_config = os.getenv("OPENLRM_INFER_CONFIG", "./configs/infer-s.yaml").strip()
    model_name = os.getenv(
        "OPENLRM_MODEL_NAME",
        "zxhezexin/openlrm-obj-small-1.1",
    ).strip()

    command = [
        os.getenv("PYTHON_EXECUTABLE", sys.executable),
        "-m",
        "openlrm.launch",
        "infer.lrm",
        "--infer",
        infer_config,
        f"model_name={model_name}",
        f"image_input={clean_image_path}",
        "export_video=false",
        "export_mesh=true",
        f"mesh_dump={output_dir}",
    ]

    timeout_s = int(os.getenv("GENERATOR_MAX_SECONDS", "240"))

    try:
        result = subprocess.run(
            command,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        if result.returncode != 0:
            print(f"OpenLRM failed: {result.stderr[-400:]}")
            return None
    except Exception as error:
        print(f"OpenLRM execution error: {error}")
        return None

    candidates = []
    candidates.extend(glob.glob(os.path.join(output_dir, "**", "*.glb"), recursive=True))
    candidates.extend(glob.glob(os.path.join(output_dir, "**", "*.obj"), recursive=True))
    candidates.extend(glob.glob(os.path.join(output_dir, "**", "*.ply"), recursive=True))

    if not candidates:
        return None

    candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return candidates[0]


def _convert_mesh_to_glb(mesh_path: str, destination_glb_path: str) -> bool:
    if mesh_path.lower().endswith(".glb"):
        shutil.copyfile(mesh_path, destination_glb_path)
        return True

    if trimesh is None:
        return False

    try:
        mesh = trimesh.load(mesh_path)
        mesh.export(destination_glb_path)
        return True
    except Exception as error:
        print(f"Mesh conversion failed: {error}")
        return False


def generate_ml_glb(concept: str, models_dir: str) -> dict[str, Any] | None:
    if not _env_bool("GENERATOR_ENABLED", True):
        return None

    _ensure_dirs()

    model_id = os.getenv("SD_MODEL_ID", "runwayml/stable-diffusion-v1-5").strip()
    steps = int(os.getenv("SD_NUM_STEPS", "20"))
    width = int(os.getenv("SD_IMAGE_WIDTH", "512"))
    height = int(os.getenv("SD_IMAGE_HEIGHT", "512"))

    key = _cache_key(concept, model_id, steps, width, height)

    os.makedirs(models_dir, exist_ok=True)
    model_filename = f"mlgen_{key}.glb"
    model_path = os.path.join(models_dir, model_filename)

    if os.path.exists(model_path):
        return {
            "filename": model_filename,
            "source": "ml_cache",
            "details": {
                "sd_model": model_id,
                "device": _resolve_device(),
            },
        }

    image_path = _generate_image(concept, key)
    if not image_path:
        return None

    clean_image_path = _remove_background(image_path, key)
    mesh_path = _run_openlrm(clean_image_path, key)
    if not mesh_path:
        return None

    success = _convert_mesh_to_glb(mesh_path, model_path)
    if not success:
        return None

    return {
        "filename": model_filename,
        "source": "ml_openlrm",
        "details": {
            "sd_model": model_id,
            "device": _resolve_device(),
            "mesh_path": mesh_path,
        },
    }


def get_ml_status() -> dict[str, Any]:
    _ensure_dirs()

    openlrm_repo = os.path.join(_ML_DIR, "OpenLRM")
    openlrm_launch = os.path.join(openlrm_repo, "openlrm", "launch.py")

    return {
        "generator_enabled": _env_bool("GENERATOR_ENABLED", True),
        "device": _resolve_device(),
        "sd_model_id": os.getenv("SD_MODEL_ID", "runwayml/stable-diffusion-v1-5").strip(),
        "openlrm_repo_exists": os.path.isdir(openlrm_repo),
        "openlrm_launch_exists": os.path.isfile(openlrm_launch),
        "openlrm_model_name": os.getenv(
            "OPENLRM_MODEL_NAME",
            "zxhezexin/openlrm-obj-small-1.1",
        ).strip(),
        "openlrm_infer_config": os.getenv("OPENLRM_INFER_CONFIG", "./configs/infer-s.yaml").strip(),
        "hf_cache_dir": _HF_CACHE_DIR,
        "hf_cache_files": len(glob.glob(os.path.join(_HF_CACHE_DIR, "**", "*"), recursive=True)),
        "cache_dirs": {
            "images": _IMAGE_DIR,
            "clean": _CLEAN_DIR,
            "openlrm": _OPENLRM_DIR,
        },
    }
