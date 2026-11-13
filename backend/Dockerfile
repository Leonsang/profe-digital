FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8080
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY profe ./profe
COPY main.py .
# Cloud Run: GOOGLE_API_KEY como secreto, ALLOWED_ORIGINS con el dominio del frontend
CMD ["sh", "-c", "uvicorn main:api --host 0.0.0.0 --port ${PORT}"]
