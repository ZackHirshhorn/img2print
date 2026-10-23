# The img2print web app: the FastAPI backend serving the built React frontend.
#   docker build -t img2print .
#   docker run -p 8000:8000 img2print
# PDF input is off by default: PyMuPDF is AGPL, which matters when hosting publicly.
# Build with --build-arg WITH_PDF=1 to include it.

# 1. Build the frontend into src/img2print/web/static
FROM node:22-slim AS frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci
COPY web/ ./
RUN npm run build

# 2. Install the Python package with the built frontend inside it
FROM python:3.12-slim
ARG WITH_PDF=0
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY --from=frontend /app/src/img2print/web/static/ src/img2print/web/static/
RUN pip install ".[web]" && if [ "$WITH_PDF" = "1" ]; then pip install pymupdf; fi \
    && useradd --create-home app
USER app
EXPOSE 8000
# Render (and similar hosts) set PORT; it falls back to 8000.
CMD ["sh", "-c", "exec uvicorn img2print.web.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
