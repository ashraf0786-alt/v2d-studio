# Multi-stage: build the React UI, then bundle it with the FastAPI backend.
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
ENV NODE_OPTIONS=--max-old-space-size=4096
# Ad config is baked into the JS at build time. Supply ca-pub-... when available;
# without it the app renders self-hosted sponsor slots.
ARG VITE_ADSENSE_ID=""
ARG VITE_AD_LINK="https://example.com/sponsor"
ARG VITE_AD_TEXT="Supported by our sponsor"
ENV VITE_ADSENSE_ID=$VITE_ADSENSE_ID
ENV VITE_AD_LINK=$VITE_AD_LINK
ENV VITE_AD_TEXT=$VITE_AD_TEXT
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /build/frontend/dist /frontend/dist

ENV DATABASE_URL=sqlite:////data/app.db
ENV STORAGE_DIR=/data/storage
ENV PUBLIC_BASE_URL=http://localhost:8000
ENV PORT=8000
VOLUME /data
EXPOSE 8000

# Bind to $PORT (Render injects it). Tables are created by app startup
# (init_db), which avoids SQLite lock contention during zero-downtime deploys.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\""]
