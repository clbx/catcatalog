FROM python:3.11-slim

WORKDIR /app

COPY services/notify/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py ./services/
COPY services/notify/ ./services/notify/

ARG VERSION=dev
ENV VERSION=${VERSION}
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "services.notify.main"]
