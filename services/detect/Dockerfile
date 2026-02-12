FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/detect/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "from ultralytics import YOLO; YOLO('yolov8m.pt')"

COPY services/__init__.py ./services/
COPY services/storage.py ./services/
COPY services/detect/ ./services/detect/

ARG VERSION=dev
ENV VERSION=${VERSION}
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "services.detect.api:app", "--host", "0.0.0.0", "--port", "8000"]
