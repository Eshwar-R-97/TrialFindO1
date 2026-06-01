# Stage 1 — build React UI (Vite bakes VITE_* vars in at build time)
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
RUN npm run build

# Stage 2 — Flask + gunicorn
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PORT=8080

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py db.py cron.py ./
COPY assets/ ./assets/
COPY static/ ./static/
COPY templates/ ./templates/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8080
CMD gunicorn -k gthread --threads 8 --workers 1 --timeout 300 -b 0.0.0.0:${PORT} app:app
