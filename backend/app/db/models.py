from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResearchRunRow(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        CheckConstraint(
            "workflow_status IN ('running','succeeded','failed')",
            name="ck_research_runs_workflow_status",
        ),
        CheckConstraint(
            "research_status IS NULL OR research_status IN ('informational','review','insufficient_data','failed')",
            name="ck_research_runs_research_status",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_research_runs_completed_after_started",
        ),
        Index(
            "ix_research_runs_user_created_id",
            "user_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        {"schema": "vantage_app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        nullable=False,
        unique=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_status: Mapped[str] = mapped_column(Text, nullable=False)
    research_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    as_of: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reasons: Mapped[list[Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    metrics: Mapped[list[Any]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    data_quality: Mapped[dict[str, Any] | None] = mapped_column(
        postgresql.JSONB, nullable=True
    )
    warnings: Mapped[list[str]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    interpretation: Mapped[dict[str, Any] | None] = mapped_column(
        postgresql.JSONB, nullable=True
    )
    model_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_version: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_version: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    code_version: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message_safe: Mapped[str | None] = mapped_column(Text, nullable=True)

    snapshot: Mapped["ResearchSnapshotRow | None"] = relationship(
        back_populates="run",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ResearchSnapshotRow(Base):
    __tablename__ = "research_snapshots"
    __table_args__ = (
        CheckConstraint(
            "window_end >= window_start",
            name="ck_research_snapshots_window_order",
        ),
        Index("ix_research_snapshots_run_id", "run_id"),
        Index("ix_research_snapshots_user_id", "user_id"),
        {"schema": "vantage_app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        nullable=False,
        unique=True,
        default=uuid4,
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vantage_app.research_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    market_provider: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    market_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    news_provider: Mapped[str] = mapped_column(Text, nullable=False)
    news_retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    news_coverage_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    news_coverage_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    news_quality: Mapped[str] = mapped_column(Text, nullable=False)
    news_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_bars: Mapped[list[Any]] = mapped_column(postgresql.JSONB, nullable=False)
    quality: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)

    run: Mapped["ResearchRunRow"] = relationship(back_populates="snapshot")
    sources: Mapped[list["ResearchSourceRow"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="ResearchSourceRow.id",
    )


class ResearchSourceRow(Base):
    __tablename__ = "research_sources"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "evidence_id",
            name="uq_research_sources_snapshot_evidence",
        ),
        Index("ix_research_sources_snapshot_id", "snapshot_id"),
        {"schema": "vantage_app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vantage_app.research_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    snapshot: Mapped["ResearchSnapshotRow"] = relationship(back_populates="sources")
