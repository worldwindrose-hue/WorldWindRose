FROM python:3.11-slim

LABEL maintainer="ROSA OS" description="Rosa — Autonomous AI Assistant"

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional deps (best effort — non-fatal)
RUN pip install --no-cache-dir \
    pyngrok \
    pywebpush \
    py_vapid \
    qrcode[pil] \
    pdfplumber \
    python-docx \
    pandas \
    openai-whisper \
    yt-dlp \
    ebooklib \
    beautifulsoup4 \
    pytesseract \
    chromadb \
    2>/dev/null || true

# App code
COPY . .

# Create data directories
RUN mkdir -p memory/backups memory/chroma memory/uploads experimental scripts/logs

# Non-root user for security
RUN useradd -m -u 1000 rosa && chown -R rosa:rosa /app
USER rosa

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "core.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
