# Imagen de producción: compila el frontend y lo sirve desde el backend (mismo dominio que el WebSocket).
# Hugging Face Spaces (sdk: docker) la construye tal cual; escucha en el puerto 7860.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PORT=7860 \
    STATIC_DIR=/app/static \
    PROFE_STORE=firestore
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/profe ./profe
COPY backend/main.py .
COPY --from=web /web/dist ./static
# Spaces ejecuta el contenedor con el usuario 1000.
RUN useradd -m -u 1000 user && chown -R user /app
USER user
EXPOSE 7860
CMD ["sh", "-c", "uvicorn main:api --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
