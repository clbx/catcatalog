"""SQLAlchemy models for the cat catalog."""

import os
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Cat(Base):
    __tablename__ = "cats"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    first_seen = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    total_sightings = Column(Integer, default=0)
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)

    sightings = relationship(
        "Sighting", back_populates="cat", order_by="desc(Sighting.timestamp)"
    )


class Sighting(Base):
    __tablename__ = "sightings"

    id = Column(Integer, primary_key=True)
    cat_id = Column(Integer, ForeignKey("cats.id"), nullable=True)
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    confidence = Column(Float, nullable=False)
    source_key = Column(String(500), nullable=True)  # S3 key of source image/video
    crop_key = Column(String(500), nullable=True)  # S3 key of cropped image
    frame_timestamp = Column(Float, nullable=True)  # for video: seconds into clip
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)

    cat = relationship("Cat", back_populates="sightings")


class ProcessedClip(Base):
    __tablename__ = "processed_clips"

    id = Column(Integer, primary_key=True)
    source_key = Column(String(500), nullable=False, unique=True, index=True)
    status = Column(
        String(20), nullable=False, default="processing"
    )  # processing, done, error
    worker_id = Column(String(100), nullable=True)
    started_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    detections = Column(Integer, default=0)


def get_engine():
    url = os.environ.get(
        "DATABASE_URL", "postgresql://catcatalog:catcatalog@localhost:5432/catcatalog"
    )
    return create_engine(url)


def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine)


def create_tables():
    engine = get_engine()
    Base.metadata.create_all(engine)
    _run_migrations(engine)


def _run_migrations(engine):
    with engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE cats ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ DEFAULT NULL"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_cats_deleted_at ON cats (deleted_at)")
        )
        conn.execute(
            text(
                "ALTER TABLE sightings ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ DEFAULT NULL"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_sightings_deleted_at ON sightings (deleted_at)"
            )
        )
        conn.commit()
