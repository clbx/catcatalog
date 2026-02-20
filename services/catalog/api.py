"""FastAPI service for the cat catalog."""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError

from ..storage import get_bucket, get_s3_client
from .models import Cat, ProcessedClip, Sighting, create_tables, get_session_factory

Session = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global Session
    create_tables()
    Session = get_session_factory()
    print(f"Catalog service ready (version: {os.environ.get('VERSION', 'dev')})")
    yield


app = FastAPI(title="Cat Catalog — Catalog Service", lifespan=lifespan)


# --- Request/Response models ---


class CatCreate(BaseModel):
    name: str | None = None
    notes: str | None = None


class CatUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None


class SightingCreate(BaseModel):
    cat_id: int | None = None
    confidence: float
    source_key: str | None = None
    crop_key: str | None = None
    frame_timestamp: float | None = None


class SightingUpdate(BaseModel):
    cat_id: int | None = None


# --- Health ---


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Cat endpoints ---


@app.post("/cats")
def create_cat(req: CatCreate):
    with Session() as session:
        cat = Cat(name=req.name, notes=req.notes)
        session.add(cat)
        session.commit()
        session.refresh(cat)
        return _cat_to_dict(cat)


@app.get("/cats")
def list_cats(limit: int = 50, offset: int = 0):
    with Session() as session:
        cats = (
            session.query(Cat)
            .filter(Cat.deleted_at.is_(None))
            .order_by(desc(Cat.last_seen))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_cat_to_dict(c) for c in cats]


@app.get("/cats/deleted")
def list_deleted_cats():
    with Session() as session:
        cats = (
            session.query(Cat)
            .filter(Cat.deleted_at.isnot(None))
            .order_by(desc(Cat.deleted_at))
            .all()
        )
        return [
            {**_cat_to_dict(c), "deleted_at": c.deleted_at.isoformat()} for c in cats
        ]


@app.get("/cats/{cat_id}")
def get_cat(cat_id: int):
    with Session() as session:
        cat = _get_active_cat(session, cat_id)
        if not cat:
            return JSONResponse(status_code=404, content={"error": "Cat not found"})
        return _cat_to_dict(cat)


@app.patch("/cats/{cat_id}")
def update_cat(cat_id: int, req: CatUpdate):
    with Session() as session:
        cat = _get_active_cat(session, cat_id)
        if not cat:
            return JSONResponse(status_code=404, content={"error": "Cat not found"})
        if req.name is not None:
            cat.name = req.name
        if req.notes is not None:
            cat.notes = req.notes
        session.commit()
        session.refresh(cat)
        return _cat_to_dict(cat)


@app.delete("/cats/{cat_id}")
def delete_cat(cat_id: int):
    with Session() as session:
        cat = _get_active_cat(session, cat_id)
        if not cat:
            return JSONResponse(status_code=404, content={"error": "Cat not found"})
        cat.deleted_at = datetime.now(timezone.utc)
        session.commit()
        return {"deleted": cat_id}


@app.get("/cats/{cat_id}/sightings")
def get_cat_sightings(cat_id: int, limit: int = 50, offset: int = 0):
    with Session() as session:
        cat = _get_active_cat(session, cat_id)
        if not cat:
            return JSONResponse(status_code=404, content={"error": "Cat not found"})
        sightings = (
            session.query(Sighting)
            .filter(Sighting.cat_id == cat_id, Sighting.deleted_at.is_(None))
            .order_by(desc(Sighting.timestamp))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_sighting_to_dict(s) for s in sightings]


# --- Sighting endpoints ---


@app.post("/sightings")
def create_sighting(req: SightingCreate):
    with Session() as session:
        sighting = Sighting(
            cat_id=req.cat_id,
            confidence=req.confidence,
            source_key=req.source_key,
            crop_key=req.crop_key,
            frame_timestamp=req.frame_timestamp,
        )
        session.add(sighting)

        # Update cat stats if linked
        if req.cat_id:
            cat = session.get(Cat, req.cat_id)
            if cat:
                cat.total_sightings += 1
                cat.last_seen = datetime.now(timezone.utc)

        session.commit()
        session.refresh(sighting)
        return _sighting_to_dict(sighting)


@app.get("/sightings")
def list_sightings(
    limit: int = 50,
    offset: int = 0,
    unassigned: bool = False,
):
    with Session() as session:
        q = session.query(Sighting).filter(Sighting.deleted_at.is_(None))
        if unassigned:
            q = q.filter(Sighting.cat_id.is_(None))
        sightings = (
            q.order_by(desc(Sighting.timestamp)).offset(offset).limit(limit).all()
        )
        return [_sighting_to_dict(s) for s in sightings]


@app.get("/sightings/deleted")
def list_deleted_sightings():
    with Session() as session:
        sightings = (
            session.query(Sighting)
            .filter(Sighting.deleted_at.isnot(None))
            .order_by(desc(Sighting.deleted_at))
            .all()
        )
        return [
            {**_sighting_to_dict(s), "deleted_at": s.deleted_at.isoformat()}
            for s in sightings
        ]


@app.get("/sightings/{sighting_id}")
def get_sighting(sighting_id: int):
    with Session() as session:
        sighting = session.get(Sighting, sighting_id)
        if not sighting:
            return JSONResponse(
                status_code=404, content={"error": "Sighting not found"}
            )
        return _sighting_to_dict(sighting)


@app.patch("/sightings/{sighting_id}")
def update_sighting(sighting_id: int, req: SightingUpdate):
    with Session() as session:
        sighting = session.get(Sighting, sighting_id)
        if not sighting:
            return JSONResponse(
                status_code=404, content={"error": "Sighting not found"}
            )

        old_cat_id = sighting.cat_id
        new_cat_id = req.cat_id

        # Update the assignment
        sighting.cat_id = new_cat_id

        # Decrement old cat's count
        if old_cat_id and old_cat_id != new_cat_id:
            old_cat = session.get(Cat, old_cat_id)
            if old_cat:
                old_cat.total_sightings = max(0, old_cat.total_sightings - 1)

        # Increment new cat's count
        if new_cat_id and new_cat_id != old_cat_id:
            new_cat = session.get(Cat, new_cat_id)
            if new_cat:
                new_cat.total_sightings += 1
                new_cat.last_seen = datetime.now(timezone.utc)

        session.commit()
        session.refresh(sighting)
        return _sighting_to_dict(sighting)


@app.delete("/sightings/{sighting_id}")
def delete_sighting(sighting_id: int):
    with Session() as session:
        sighting = session.get(Sighting, sighting_id)
        if not sighting:
            return JSONResponse(
                status_code=404, content={"error": "Sighting not found"}
            )
        if sighting.cat_id:
            cat = session.get(Cat, sighting.cat_id)
            if cat:
                cat.total_sightings = max(0, cat.total_sightings - 1)
        sighting.deleted_at = datetime.now(timezone.utc)
        session.commit()
        return {"deleted": sighting_id}


# --- Clip processing ---


class ClipLockRequest(BaseModel):
    source_key: str
    worker_id: str


class ClipCompleteRequest(BaseModel):
    source_key: str
    detections: int = 0
    error: str | None = None


@app.get("/clips/status")
def clip_status(source_key: str):
    """Check if a clip has been processed or is in progress."""
    with Session() as session:
        clip = (
            session.query(ProcessedClip)
            .filter(ProcessedClip.source_key == source_key)
            .first()
        )
        if not clip:
            return {"status": "new"}
        return {
            "status": clip.status,
            "worker_id": clip.worker_id,
            "started_at": clip.started_at.isoformat() if clip.started_at else None,
            "completed_at": clip.completed_at.isoformat()
            if clip.completed_at
            else None,
            "detections": clip.detections,
        }


@app.post("/clips/lock")
def clip_lock(req: ClipLockRequest):
    """Attempt to lock a clip for processing. Always returns 200 with lock result."""
    with Session() as session:
        existing = (
            session.query(ProcessedClip)
            .filter(ProcessedClip.source_key == req.source_key)
            .first()
        )
        if existing:
            return {
                "locked": False,
                "status": existing.status,
                "worker_id": existing.worker_id,
            }
        try:
            clip = ProcessedClip(
                source_key=req.source_key,
                status="processing",
                worker_id=req.worker_id,
            )
            session.add(clip)
            session.commit()
            return {"locked": True, "status": "processing"}
        except IntegrityError:
            session.rollback()
            return {"locked": False, "status": "processing"}


@app.post("/clips/complete")
def clip_complete(req: ClipCompleteRequest):
    """Mark a clip as done or errored."""
    with Session() as session:
        clip = (
            session.query(ProcessedClip)
            .filter(ProcessedClip.source_key == req.source_key)
            .first()
        )
        if not clip:
            return JSONResponse(status_code=404, content={"error": "Clip not found"})
        clip.status = "error" if req.error else "done"
        clip.completed_at = datetime.now(timezone.utc)
        clip.detections = req.detections
        session.commit()
        return {"status": clip.status}


# --- Restore / Cleanup ---


@app.post("/cats/{cat_id}/restore")
def restore_cat(cat_id: int):
    with Session() as session:
        cat = session.get(Cat, cat_id)
        if not cat or cat.deleted_at is None:
            return JSONResponse(
                status_code=404, content={"error": "No deleted cat found"}
            )
        cat.deleted_at = None
        session.commit()
        session.refresh(cat)
        return _cat_to_dict(cat)


@app.post("/sightings/{sighting_id}/restore")
def restore_sighting(sighting_id: int):
    with Session() as session:
        sighting = session.get(Sighting, sighting_id)
        if not sighting or sighting.deleted_at is None:
            return JSONResponse(
                status_code=404, content={"error": "No deleted sighting found"}
            )
        sighting.deleted_at = None
        if sighting.cat_id:
            cat = session.get(Cat, sighting.cat_id)
            if cat:
                cat.total_sightings += 1
        session.commit()
        session.refresh(sighting)
        return _sighting_to_dict(sighting)


@app.delete("/admin/deleted")
def purge_deleted():
    with Session() as session:
        # Purge deleted sightings
        deleted_sightings = (
            session.query(Sighting).filter(Sighting.deleted_at.isnot(None)).count()
        )
        session.query(Sighting).filter(Sighting.deleted_at.isnot(None)).delete()

        # Purge deleted cats
        deleted_cats = session.query(Cat).filter(Cat.deleted_at.isnot(None)).all()
        cats_count = len(deleted_cats)
        for cat in deleted_cats:
            session.query(Sighting).filter(Sighting.cat_id == cat.id).update(
                {"cat_id": None}
            )
            session.delete(cat)
        session.commit()
        return {"purged_cats": cats_count, "purged_sightings": deleted_sightings}


# --- Stats ---


@app.get("/stats")
def stats():
    with Session() as session:
        return {
            "total_cats": session.query(Cat).filter(Cat.deleted_at.is_(None)).count(),
            "total_sightings": session.query(Sighting)
            .filter(Sighting.deleted_at.is_(None))
            .count(),
            "unassigned_sightings": session.query(Sighting)
            .filter(Sighting.cat_id.is_(None), Sighting.deleted_at.is_(None))
            .count(),
        }


# --- S3 proxy ---


@app.get("/crops/{key:path}")
def get_crop(key: str):
    """Proxy a crop image from S3."""
    s3 = get_s3_client()
    try:
        resp = s3.get_object(Bucket=get_bucket(), Key=key)
        data = resp["Body"].read()
        content_type = resp.get("ContentType", "image/jpeg")
        return Response(content=data, media_type=content_type)
    except Exception:
        return Response(status_code=404, content=b"Not found")


@app.get("/videos/{key:path}")
def get_video(key: str):
    """Proxy a video file from S3."""
    s3 = get_s3_client()
    try:
        resp = s3.get_object(Bucket=get_bucket(), Key=key)
        data = resp["Body"].read()
        content_type = resp.get("ContentType", "video/mp4")
        return Response(content=data, media_type=content_type)
    except Exception:
        return Response(status_code=404, content=b"Not found")


# --- Query helpers ---


def _get_active_cat(session, cat_id):
    cat = session.get(Cat, cat_id)
    if cat and cat.deleted_at is not None:
        return None
    return cat


# --- Serialization helpers ---


def _cat_to_dict(cat):
    return {
        "id": cat.id,
        "name": cat.name,
        "notes": cat.notes,
        "first_seen": cat.first_seen.isoformat() if cat.first_seen else None,
        "last_seen": cat.last_seen.isoformat() if cat.last_seen else None,
        "total_sightings": cat.total_sightings,
    }


def _sighting_to_dict(sighting):
    return {
        "id": sighting.id,
        "cat_id": sighting.cat_id,
        "timestamp": sighting.timestamp.isoformat() if sighting.timestamp else None,
        "confidence": sighting.confidence,
        "source_key": sighting.source_key,
        "crop_key": sighting.crop_key,
        "frame_timestamp": sighting.frame_timestamp,
    }
