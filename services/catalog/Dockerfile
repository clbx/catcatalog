FROM python:3.11-slim

WORKDIR /app

COPY services/catalog/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py ./services/
COPY services/storage.py ./services/
COPY services/catalog/ ./services/catalog/

ENV PYTHONUNBUFFERED=1

EXPOSE 8001
CMD ["uvicorn", "services.catalog.api:app", "--host", "0.0.0.0", "--port", "8001"]
