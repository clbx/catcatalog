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
    animal = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=False)
    bbox = Column(String(100), nullable=True)  # stored as "x1,y1,x2,y2"
    source_key = Column(String(500), nullable=True)  # S3 key of source image/video
    crop_key = Column(String(500), nullable=True)  # S3 key of cropped image
    frame_timestamp = Column(Float, nullable=True)  # for video: seconds into clip

    cat = relationship("Cat", back_populates="sightings")


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
