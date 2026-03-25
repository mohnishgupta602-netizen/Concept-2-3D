# 3D Generation Improvements & Troubleshooting Guide

## Summary of Changes Made

### 1. ✅ Lowered Confidence Threshold (0.40 → 0.25)
- **File**: `hybrid_pipeline.py` line 48
- **Impact**: More retrieval candidates will pass the quality filter instead of falling back to ML
- **Why**: 40% was too strict; models with 25% match might still be useful

### 2. ✅ Enhanced Stable Diffusion Settings
- **File**: `.env`
- **Changes**:
  - `SD_NUM_STEPS`: 20 → 30 (better image quality)
  - `SD_IMAGE_WIDTH/HEIGHT`: 512 → 768 (higher resolution = better OpenLRM conversion)
  - `SD_GUIDANCE_SCALE`: 6.5 → 7.5 (better concept adherence)
  - `GENERATOR_MAX_SECONDS`: 240 → 300 (more time for slow GPUs)
  - `SKETCHFAB_API_MAX_CALLS`: 3 → 8 (more retrieval chances)

### 3. ✅ Added Comprehensive Debug Logging
- **Files**: `generative_stack.py`
- **Output**: You'll now see detailed logs like:
  ```
  [ML] Generating 3D model for 'chair' (device=cuda)
  [ML] ✓ Generated image: /path/to/image.png
  [ML] ✓ Removed background: /path/to/clean.png
  [OpenLRM] Running command (timeout=300s): ...
  [OpenLRM] ✓ Success: mesh generated in /path/to/output
  ```
  This helps identify exactly WHERE it's failing.

### 4. ✅ Added Diagnostics Endpoint
- **URL**: `http://localhost:8000/ml/diagnostics`
- **Purpose**: Check if your ML pipeline is properly configured
- **Returns**: All missing packages, configuration issues, GPU status

---

## Quick Diagnostic Steps

### Step 1: Check ML Pipeline Health
Visit in your browser:
```
http://localhost:8000/ml/diagnostics
```

Look for:
1. **Device**: Should be `cuda` (GPU) or `cpu`
2. **torch_available**: Must be True
3. **cuda_available**: True if you have GPU (recommended)
4. **openlrm_repo_exists**: Must be True
5. **openlrm_launch_exists**: Must be True
6. **Issues**: Read any listed issues

### Step 2: Check Backend Logs
When you run a search, look at your backend terminal for logs like:
```
[Gemini] Enhancing search for: chair
[ML] Generating 3D model for 'chair' (device=cuda)
[ML] ✓ Generated image: ...
[ML] ✓ Removed background: ...
[OpenLRM] Running command ...
```

**If it stops at any step**, you found the problem (see troubleshooting below).

### Step 3: Test ML Generation Directly (Python)
```python
from generative_stack import generate_ml_glb
result = generate_ml_glb("chair", "./concept3d/backend/models")
print(result)
```

---

## Common Failure Points & Fixes

### ❌ Problem: "launch.py not found"
**Diagnosis logs**: `[OpenLRM] ERROR: launch.py not found at ...`

**Causes**:
- OpenLRM repo not cloned
- Wrong path in `OPENLRM_REPO_DIR`

**Fix**:
```bash
cd concept3d/backend/ml
git clone https://github.com/your-org/OpenLRM.git
# Or if you have the repo elsewhere:
# Set in .env: OPENLRM_REPO_DIR=/path/to/OpenLRM
```

---

### ❌ Problem: "No module named 'openlrm'"
**Diagnosis logs**: `[OpenLRM] EXCEPTION: No module named 'openlrm'`

**Causes**:
- OpenLRM not installed as Python package
- Wrong Python environment

**Fix**:
```bash
cd concept3d/backend/ml/OpenLRM
pip install -e .
```

---

### ❌ Problem: CUDA out of memory / CUDA error
**Diagnosis logs**: `[OpenLRM] FAILED ... cuda ... memory`

**Causes**:
- GPU memory insufficient
- Another process using GPU memory

**Fixes**:
1. Use smaller model: Change `.env`
   ```
   OPENLRM_MODEL_NAME=zxhezexin/openlrm-obj-small-1.1  # Already using small
   ```

2. If still failing, fall back to CPU:
   ```
   GENERATOR_DEVICE=cpu
   GENERATOR_MAX_SECONDS=600  # CPU is slower
   ```

3. Or reduce image resolution:
   ```
   SD_IMAGE_WIDTH=512
   SD_IMAGE_HEIGHT=512
   ```

---

### ❌ Problem: "No mesh files found"
**Diagnosis logs**: `[OpenLRM] ERROR: No mesh files (.glb/.obj/.ply) found in output dir`

**Causes**:
- OpenLRM generated nothing (bad image input)
- OpenLRM crashed silently
- Wrong output directory setting

**Fixes**:
1. Check if model downloaded:
   ```bash
   huggingface-cli whoami  # Login to HuggingFace
   huggingface-cli download zxhezexin/openlrm-obj-small-1.1
   ```

2. Test with a known-good image:
   ```python
   # Use a real photo instead of SD-generated image
   image = Image.open("test_photo.jpg")
   image.save("concept3d/backend/ml/cache/clean/test.png")
   # Then test OpenLRM with this image
   ```

---

### ❌ Problem: Slow generation (timeout)
**Diagnosis logs**: `[OpenLRM] TIMEOUT after 300s`

**Causes**:
- GPU too slow
- First run (downloads large models)
- CPU-based generation

**Fixes**:
1. Increase timeout (only first run downloads models):
   ```
   GENERATOR_MAX_SECONDS=600
   ```

2. Check HuggingFace cache was created:
   ```bash
   ls -lh concept3d/backend/ml/hf_cache/
   # Should contain model files after first run
   ```

3. If first run still fails, it's likely model download failed. Check:
   ```bash
   # Diagnose HF issues
   python -c "from transformers import AutoModel; AutoModel.from_pretrained('zxhezexin/openlrm-obj-small-1.1')"
   ```

---

## When to Use Fallback vs. ML Generation

The system tries in this order:

1. **Best**: Retrieval from BlenderKit/Sketchfab/Poly Pizza
   - Fast, real models, high quality
   - Requires internet and API keys working

2. **Good**: ML Generation (Stable Diffusion + OpenLRM)
   - User's concept might not exist in databases
   - Works offline once models are cached
   - Takes 2-5 minutes per search

3. **Last**: Procedural fallback (simple shapes)
   - Only used if ML generation completely fails
   - Low quality but always works

---

## Further Optimizations (Optional)

If you want even better 3D generation:

### Option A: Use Better Stable Diffusion Model
```env
# Try SDXL for better quality (requires more VRAM)
SD_MODEL_ID=stabilityai/stable-diffusion-xl-base-1.0
SD_GUIDANCE_SCALE=7.5
```

### Option B: Use Better OpenLRM Model
```env
# Try medium model (slower but better quality)
OPENLRM_MODEL_NAME=zxhezexin/openlrm-obj-medium-1.1
```

### Option C: Add Pre-Processing Stack
The code already has:
- ✓ Prompt optimization for OpenLRM
- ✓ Background removal
- ✓ Image size optimization

Consider adding:
- Edge enhancement before OpenLRM
- Multiple view generation
- Mesh smoothing/decimation post-processing

---

## API Endpoints for Testing

```bash
# Check ML system health
curl http://localhost:8000/ml/status
curl http://localhost:8000/ml/diagnostics

# Test generation directly (backend will log details)
curl -X POST http://localhost:8000/visualize?concept=chair

# Watch logs while testing
# Terminal: tail -f backend.log
```

---

## Summary Checklist

- [ ] Restarted backend server (to load new .env settings)
- [ ] Checked `/ml/diagnostics` endpoint - all green?
- [ ] Tried a search and watched backend logs
- [ ] If failure: Identified which step failed
- [ ] Applied fix for that step
- [ ] Tested again

If you're still stuck, share the logs from `/ml/diagnostics` and the backend terminal output when a search fails.
