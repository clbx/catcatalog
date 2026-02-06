"""FastAPI service for the cat catalog."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc

from .models import Cat, Sighting, create_tables, get_session_factory

Session = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global Session
    create_tables()
    Session = get_session_factory()
    print("Catalog service ready")
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
    animal: str
    confidence: float
    bbox: list[int] | None = None
    source_key: str | None = None
    crop_key: str | None = None
    frame_timestamp: float | None = None


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
            .order_by(desc(Cat.last_seen))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_cat_to_dict(c) for c in cats]


@app.get("/cats/{cat_id}")
def get_cat(cat_id: int):
    with Session() as session:
        cat = session.get(Cat, cat_id)
        if not cat:
            return JSONResponse(status_code=404, content={"error": "Cat not found"})
        return _cat_to_dict(cat)


@app.patch("/cats/{cat_id}")
def update_cat(cat_id: int, req: CatUpdate):
    with Session() as session:
        cat = session.get(Cat, cat_id)
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
        cat = session.get(Cat, cat_id)
        if not cat:
            return JSONResponse(status_code=404, content={"error": "Cat not found"})
        session.delete(cat)
        session.commit()
        return {"deleted": cat_id}


@app.get("/cats/{cat_id}/sightings")
def get_cat_sightings(cat_id: int, limit: int = 50, offset: int = 0):
    with Session() as session:
        cat = session.get(Cat, cat_id)
        if not cat:
            return JSONResponse(status_code=404, content={"error": "Cat not found"})
        sightings = (
            session.query(Sighting)
            .filter(Sighting.cat_id == cat_id)
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
            animal=req.animal,
            confidence=req.confidence,
            bbox=",".join(str(x) for x in req.bbox) if req.bbox else None,
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
def list_sightings(limit: int = 50, offset: int = 0, animal: str | None = None):
    with Session() as session:
        q = session.query(Sighting)
        if animal:
            q = q.filter(Sighting.animal == animal)
        sightings = (
            q.order_by(desc(Sighting.timestamp)).offset(offset).limit(limit).all()
        )
        return [_sighting_to_dict(s) for s in sightings]


@app.get("/sightings/{sighting_id}")
def get_sighting(sighting_id: int):
    with Session() as session:
        sighting = session.get(Sighting, sighting_id)
        if not sighting:
            return JSONResponse(
                status_code=404, content={"error": "Sighting not found"}
            )
        return _sighting_to_dict(sighting)


# --- Stats ---


@app.get("/stats")
def stats():
    with Session() as session:
        return {
            "total_cats": session.query(Cat).count(),
            "total_sightings": session.query(Sighting).count(),
        }


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
        "animal": sighting.animal,
        "confidence": sighting.confidence,
        "bbox": [int(x) for x in sighting.bbox.split(",")] if sighting.bbox else None,
        "source_key": sighting.source_key,
        "crop_key": sighting.crop_key,
        "frame_timestamp": sighting.frame_timestamp,
    }
