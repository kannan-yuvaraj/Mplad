# Hugging Face Space (Docker SDK) — the WHOLE product in one container.
#
# React frontend + FastAPI + pre-built artifacts. One service, one URL, one deploy:
#   - no CORS, because the browser never makes a cross-origin request;
#   - no build-time API base to get wrong — the frontend uses same-origin relative paths,
#     exactly as it does in local development.
#
# Artifacts are BAKED IN rather than generated during the build: the pipeline already ran,
# and the container serves exactly the artifacts that were tested. No Dataset/, no
# scikit-learn, no lifelines. PyTorch (CPU build) is present only because Docling needs it
# to read documents; nothing loads it until a document is uploaded.
#
# Deploy with scripts/deploy_hf_space.py, which uploads only what this file copies.

# ---------------------------------------------------------------- stage 1: frontend
FROM node:20-slim AS frontend

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- stage 2: runtime
FROM python:3.11-slim

# OpenCV (used by RapidOCR and Docling) needs these two system libraries, which the slim
# image leaves out. Installed as root, before switching to the Space's user.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Spaces run as uid 1000. Create the user before anything is copied, so the audit log and
# field verification records can actually be written at run time.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    MPLADS_OCR_ENGINES=rapidocr

WORKDIR $HOME/app

COPY --chown=user requirements-serve.txt ./
RUN pip install --no-cache-dir --user -r requirements-serve.txt

# OCR: PyTorch's CPU build first (~200 MB) so Docling does not drag in the CUDA build.
COPY --chown=user requirements-ocr.txt ./
RUN pip install --no-cache-dir --user --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision \
 && pip install --no-cache-dir --user -r requirements-ocr.txt

COPY --chown=user pyproject.toml ./
COPY --chown=user src/ ./src/
RUN pip install --no-cache-dir --user --no-deps -e .

# Pre-built artifacts. config resolves these relative to the repo root, which is this dir.
# .dockerignore keeps out the verification and audit databases, uploaded photos and
# documents, and the OCR benchmark — they are created fresh, empty, at run time.
COPY --chown=user data/artifacts/ ./data/artifacts/

# The Salesforce CRM mirror the Case Tracking screen reads.
COPY --chown=user salesforce_export/ ./salesforce_export/

# The built React app. app.py mounts /assets and serves index.html for client-side routes
# when this directory exists, and serves the API alone when it does not.
COPY --from=frontend --chown=user /build/dist ./frontend/dist

# Hugging Face routes to app_port (8080, in the Space README); other hosts inject $PORT.
EXPOSE 8080

# One worker: the corpus is held in memory and the SQLite audit chain is append-only, so a
# second worker would double the memory and could interleave writes into the chain.
CMD ["sh", "-c", "uvicorn mplads.api.app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
