"""SQLAlchemy ORM models."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from db.database import Base


def _now():
    return datetime.utcnow()


def _uuid():
    return str(uuid.uuid4())


class PlatformRecord(Base):
    __tablename__ = "platforms"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    language = Column(String, nullable=False, default="fr")
    description = Column(Text, nullable=False, default="")
    feedback_mode = Column(String, nullable=False, default="offline")  # offline | live
    platform_context = Column(Text, nullable=True)
    live_student_prompt = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class GeneralConfig(Base):
    __tablename__ = "general_config"

    id = Column(Integer, primary_key=True, default=1)
    general_feedback_instructions = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class PlatformConfig(Base):
    __tablename__ = "platform_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    vocabulary_to_use = Column(Text, nullable=True)
    vocabulary_to_avoid = Column(Text, nullable=True)
    teacher_comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)



class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(String, nullable=False, default="algopython", index=True)
    exercise_id = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    exercise_type = Column(String, nullable=False)  # console | design | robot
    robot_map = Column(JSON, nullable=True)          # list[list[str]], only for robot type
    possible_solutions = Column(JSON, nullable=False, default=list)  # list[str]
    kc_names = Column(JSON, nullable=False, default=list)  # list[str] — KC name identifiers
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class KnowledgeComponent(Base):
    __tablename__ = "knowledge_components"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(String, nullable=False, default="algopython", index=True)
    name = Column(String, nullable=False, index=True)        # e.g. FO.4.2.1
    description = Column(Text, nullable=False)
    series = Column(String, nullable=True)                   # A–G curriculum series
    created_at = Column(DateTime, default=_now)


class ErrorEntry(Base):
    __tablename__ = "error_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_id = Column(String, nullable=False, default="algopython", index=True)
    tag = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    related_kc_names = Column(JSON, nullable=False, default=list)  # list[str]
    created_at = Column(DateTime, default=_now)


class FeedbackRecord(Base):
    __tablename__ = "feedback_records"

    id = Column(String, primary_key=True, default=_uuid)
    platform_id = Column(String, nullable=False, index=True)
    exercise_id = Column(String, nullable=True)
    kc_name = Column(String, nullable=False)
    kc_description = Column(Text, nullable=True)
    mode = Column(String, nullable=False)
    level = Column(String, nullable=False)
    language = Column(String, nullable=False)
    characteristics = Column(JSON, nullable=False)           # list[str]
    request_payload = Column(JSON, nullable=True)
    result_xml = Column(Text, nullable=True)
    total_iterations = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending | completed | failed
    validation_status = Column(String, nullable=False, default="generated")  # generated | validé
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, index=True)

    logs = relationship("AgentLog", back_populates="record", cascade="all, delete-orphan",
                        order_by="AgentLog.step_number")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    feedback_record_id = Column(String, ForeignKey("feedback_records.id"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    agent = Column(String, nullable=False)          # orchestrator | mistral | claude | simulator | gemini
    role = Column(String, nullable=True)            # planning | generation | evaluation | relevance | simulation | assembly
    tool_name = Column(String, nullable=True)
    characteristic = Column(String, nullable=True)
    attempt = Column(Integer, nullable=True)
    verdict = Column(String, nullable=True)         # passed | failed | regenerating | accepted | rejected
    notes = Column(Text, nullable=True)             # Claude reasoning / critique text
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_now)

    record = relationship("FeedbackRecord", back_populates="logs")
