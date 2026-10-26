from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.engine import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
    )

    sessions_per_week: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )   

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ai",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
    )

    workouts: Mapped[list[Workout]] = relationship(
        back_populates="training_plan",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "year",
            "month",
            name="uq_training_plan_month",
        ),
    )


class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    training_plan_id: Mapped[int] = mapped_column(
        ForeignKey("training_plans.id"),
        nullable=False,
        index=True,
    )

    scheduled_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="planned",
        index=True,
    )

    warmup: Mapped[str | None] = mapped_column(
        String(100),
    )

    repeat: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    work: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    recovery: Mapped[str | None] = mapped_column(
        String(100),
    )

    cooldown: Mapped[str | None] = mapped_column(
        String(100),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    training_plan: Mapped[TrainingPlan] = relationship(
        back_populates="workouts",
    )

    activity_links: Mapped[list[WorkoutActivityLink]] = relationship(
        back_populates="workout",
        cascade="all, delete-orphan",
    )

    analyses: Mapped[list[WorkoutAnalysis]] = relationship(
        back_populates="workout",
        cascade="all, delete-orphan",
    )


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    endurain_activity_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        unique=True,
        index=True,
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        Float,
    )

    distance_meters: Mapped[float | None] = mapped_column(
        Float,
    )

    average_power: Mapped[float | None] = mapped_column(
        Float,
    )

    normalized_power: Mapped[float | None] = mapped_column(
        Float,
    )

    average_hr: Mapped[float | None] = mapped_column(
        Float,
    )

    max_hr: Mapped[float | None] = mapped_column(
        Float,
    )

    average_spm: Mapped[float | None] = mapped_column(
        Float,
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )

    workout_links: Mapped[list[WorkoutActivityLink]] = relationship(
        back_populates="activity",
    )

    analyses: Mapped[list[WorkoutAnalysis]] = relationship(
        back_populates="activity",
    )


class WorkoutActivityLink(Base):
    __tablename__ = "workout_activity_links"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    workout_id: Mapped[int] = mapped_column(
        ForeignKey("workouts.id"),
        nullable=False,
        index=True,
    )

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    match_score: Mapped[float | None] = mapped_column(
        Float,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )

    workout: Mapped[Workout] = relationship(
        back_populates="activity_links",
    )

    activity: Mapped[Activity] = relationship(
        back_populates="workout_links",
    )

    __table_args__ = (
        UniqueConstraint(
            "workout_id",
            "activity_id",
            name="uq_workout_activity",
        ),
    )


class WorkoutAnalysis(Base):
    __tablename__ = "workout_analyses"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    workout_id: Mapped[int | None] = mapped_column(
        ForeignKey("workouts.id"),
        index=True,
    )

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id"),
        nullable=False,
        index=True,
    )

    execution: Mapped[str | None] = mapped_column(
        String(30),
    )

    load_assessment: Mapped[str | None] = mapped_column(
        String(30),
    )

    effort: Mapped[str | None] = mapped_column(
        String(30),
    )

    progression: Mapped[str | None] = mapped_column(
        String(30),
    )

    recovery_concern: Mapped[bool | None] = mapped_column(
        Boolean,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    recommendation: Mapped[str | None] = mapped_column(
        Text,
    )

    analysis_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    prompt_version: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )

    workout: Mapped[Workout | None] = relationship(
        back_populates="analyses",
    )

    activity: Mapped[Activity] = relationship(
        back_populates="analyses",
    )

class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    iso_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    assessment: Mapped[str | None] = mapped_column(
        String(30),
    )

    trend: Mapped[str | None] = mapped_column(
        String(30),
    )

    load_assessment: Mapped[str | None] = mapped_column(
        String(30),
    )

    recovery_assessment: Mapped[str | None] = mapped_column(
        String(30),
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    review_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    prompt_version: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    input_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )



class MonthlyReview(Base):
    __tablename__ = "monthly_reviews"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    assessment: Mapped[str | None] = mapped_column(
        String(30),
    )

    trend: Mapped[str | None] = mapped_column(
        String(30),
    )

    load_assessment: Mapped[str | None] = mapped_column(
        String(30),
    )

    recovery_assessment: Mapped[str | None] = mapped_column(
        String(30),
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    review_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    prompt_version: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    input_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )


class CoachRecommendation(Base):
    __tablename__ = "coach_recommendations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    workout_id: Mapped[int | None] = mapped_column(
        ForeignKey("workouts.id"),
        index=True,
    )

    training_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_plans.id"),
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )

    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
    )

    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime,
    )

    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime,
    )


class AvailabilityPeriod(Base):
    __tablename__ = "availability_periods"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    external_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    summary: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="unavailable",
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="nextcloud",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
    )


class CalendarSync(Base):
    __tablename__ = "calendar_sync"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    workout_id: Mapped[int] = mapped_column(
        ForeignKey("workouts.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    calendar_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    calendar_href: Mapped[str | None] = mapped_column(
        Text,
    )

    calendar_etag: Mapped[str | None] = mapped_column(
        String(255),
    )

    sync_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime,
    )