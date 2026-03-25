# ML Workspace

This folder stores local ML assets for generative fallback:

- `OpenLRM/` cloned repo and checkpoints
- `cache/images/` text-to-image outputs
- `cache/clean/` background-removed images
- `cache/openlrm/` mesh outputs

Environment knobs (set in `backend/.env`):

- `GENERATOR_ENABLED=true`
- `SD_MODEL_ID=runwayml/stable-diffusion-v1-5`
- `GENERATOR_DEVICE=auto`
- `GENERATOR_MAX_SECONDS=240`
- `OPENLRM_REPO_DIR=./ml/OpenLRM`
- `OPENLRM_INFER_CONFIG=./configs/infer-s.yaml`
- `OPENLRM_MODEL_NAME=zxhezexin/openlrm-obj-small-1.1`
