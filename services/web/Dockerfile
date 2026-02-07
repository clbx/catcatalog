FROM python:3.11-slim

WORKDIR /app

COPY services/web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py ./services/
COPY services/storage.py ./services/
COPY services/web/ ./services/web/

ENV PYTHONUNBUFFERED=1

EXPOSE 3000
CMD ["uvicorn", "services.web.app:app", "--host", "0.0.0.0", "--port", "3000"]
