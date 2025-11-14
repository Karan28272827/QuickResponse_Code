# backend/app/models.py
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Coin(Base):
    __tablename__ = "coins"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    serial = Column(String, unique=True, nullable=True)
    short_id = Column(String, unique=True, nullable=False, index=True)
    weight = Column(Numeric, nullable=True)
    purity = Column(Numeric, nullable=True)
    mint_lot = Column(String, nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    cert_hash = Column(String, nullable=True)
    blockchain_anchor_tx = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Certificate(Base):
    __tablename__ = "certificates"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    coin_id = Column(UUID(as_uuid=True), ForeignKey("coins.id", ondelete="CASCADE"))
    storage_path = Column(String, nullable=False)
    file_hash = Column(String, nullable=True)
    issued_by = Column(String, nullable=True)
    issue_date = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSON, nullable=True)  # renamed from `metadata`
    created_at = Column(DateTime(timezone=True), server_default=func.now())
