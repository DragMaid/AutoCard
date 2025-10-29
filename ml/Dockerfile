# Dockerfile
FROM python:3.11-slim

# Install dependencies in a single layer for caching
RUN pip install --no-cache-dir mlflow psycopg2-binary

WORKDIR /app

# Expose MLflow port
EXPOSE 5000
