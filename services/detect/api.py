"""Minimal health/status API for the detection worker."""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .worker import start_worker, status


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the worker in a background thread
    thread = threading.Thread(target=start_worker, daemon=True)
    thread.start()
    yield


app = FastAPI(title="Cat Catalog — Detection Worker", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "worker_state": status["state"]}


@app.get("/status")
def get_status():
    return status
