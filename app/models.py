"""SQLAlchemy 2.x ORM models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AppMeta(Base):
    """Key/value app metadata (schema version, seed flag, settings)."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="todo")  # todo|in_progress|done
    priority: Mapped[str] = mapped_column(String(16), default="medium")  # low|medium|high
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    goal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("goals.id"), nullable=True)
    color_tag: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    recur_rule: Mapped[str] = mapped_column(String(16), default="none")  # none|daily|weekly
    recur_anchor: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    estimated_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    inbox: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    goal: Mapped[Optional["Goal"]] = relationship(back_populates="tasks")

    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_due_date", "due_date"),
        Index("ix_tasks_goal_id", "goal_id"),
        Index("ix_tasks_archived", "archived"),
        Index("ix_tasks_pinned", "pinned"),
        Index("ix_tasks_priority", "priority"),
        Index("ix_tasks_recur_rule", "recur_rule"),
        Index("ix_tasks_inbox", "inbox"),
    )
    subtasks: Mapped[list["Subtask"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="Subtask.position",
    )


class Subtask(Base):
    """Checklist item belonging to a Task."""

    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    task: Mapped[Task] = relationship(back_populates="subtasks")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    target_value: Mapped[float] = mapped_column(Float, default=100.0)
    unit: Mapped[str] = mapped_column(String(64), default="units")
    daily_quota: Mapped[float] = mapped_column(Float, default=1.0)
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_goals_archived", "archived"),)

    tasks: Mapped[list[Task]] = relationship(back_populates="goal")
    logs: Mapped[list["ProgressLog"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )

    @property
    def percent_complete(self) -> float:
        if self.target_value <= 0:
            return 0.0
        return min(100.0, round(100.0 * self.current_value / self.target_value, 1))


class ProgressLog(Base):
    __tablename__ = "progress_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="")
    logged_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    goal: Mapped[Goal] = relationship(back_populates="logs")

    __table_args__ = (
        Index("ix_progress_logs_goal_id", "goal_id"),
        Index("ix_progress_logs_logged_at", "logged_at"),
    )


class RoadmapNode(Base):
    __tablename__ = "roadmap_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    x: Mapped[float] = mapped_column(Float, default=40.0)
    y: Mapped[float] = mapped_column(Float, default=40.0)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|active|done
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)


class RoadmapEdge(Base):
    __tablename__ = "roadmap_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("roadmap_nodes.id"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("roadmap_nodes.id"), nullable=False)


class TimeSession(Base):
    """Focus / Pomodoro timer session."""

    __tablename__ = "time_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    label: Mapped[str] = mapped_column(String(200), default="Фокус")
    duration_sec: Mapped[int] = mapped_column(Integer, default=25 * 60)
    remaining_sec: Mapped[int] = mapped_column(Integer, default=25 * 60)
    status: Mapped[str] = mapped_column(String(32), default="paused")  # running|paused|done
    note: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CanvasNode(Base):
    """Infinite canvas node — section MD, free note, or roadmap mirror."""

    __tablename__ = "canvas_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    kind: Mapped[str] = mapped_column(String(32), default="note")  # section|note|roadmap
    ref: Mapped[str] = mapped_column(String(255), default="")  # filename or roadmap node id
    color: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    w: Mapped[float] = mapped_column(Float, default=160.0)
    h: Mapped[float] = mapped_column(Float, default=72.0)


class CanvasEdge(Base):
    """Optional link between canvas note nodes."""

    __tablename__ = "canvas_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_node_id: Mapped[int] = mapped_column(
        ForeignKey("canvas_nodes.id", ondelete="CASCADE"), nullable=False
    )
    to_node_id: Mapped[int] = mapped_column(
        ForeignKey("canvas_nodes.id", ondelete="CASCADE"), nullable=False
    )
