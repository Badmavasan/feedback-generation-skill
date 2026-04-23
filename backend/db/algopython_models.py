"""Read-only ORM models reflecting the AlgoPython source database schema (MySQL)."""
from sqlalchemy import Column, Integer, String, Text, Enum, ForeignKey
from sqlalchemy.orm import relationship

from db.algopython_db import AlgoPythonBase

_STATUS = Enum('pending_review', 'approved', 'rejected', 'withdrawn', name='status')


class AlgoError(AlgoPythonBase):
    """Maps to the `Error` table."""
    __tablename__ = "Error"

    id = Column(Integer, primary_key=True)
    error_tag = Column(String(191), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(_STATUS, nullable=False)
    project_id = Column(Integer, nullable=True)


class AlgoExercise(AlgoPythonBase):
    """Maps to the `Exercise` table."""
    __tablename__ = "Exercise"

    id = Column(Integer, primary_key=True)
    title = Column(String(191), nullable=False)
    description = Column(Text, nullable=True)
    correct_codes = Column(Text, nullable=True)   # JSON array of solution strings
    exercise_type = Column(String(50), nullable=True)  # Console | Design | Robot
    platform_exercise_id = Column(Integer, nullable=True, index=True)
    status = Column(_STATUS, nullable=False)
    project_id = Column(Integer, nullable=True)

    task_type_associations = relationship(
        "AlgoTaskTypeExerciseAssociation",
        back_populates="exercise",
        lazy="selectin",
    )


class AlgoTaskType(AlgoPythonBase):
    """Maps to the `TaskType` table."""
    __tablename__ = "TaskType"

    id = Column(Integer, primary_key=True)
    task_code = Column(String(191), nullable=False)
    task_name = Column(String(191), nullable=False)
    status = Column(_STATUS, nullable=False)
    project_id = Column(Integer, nullable=True)


class AlgoTaskTypeExerciseAssociation(AlgoPythonBase):
    """Maps to the `TaskTypeExerciseAssociation` join table."""
    __tablename__ = "TaskTypeExerciseAssociation"

    exercise_id = Column(Integer, ForeignKey("Exercise.id"), primary_key=True)
    task_type_id = Column(Integer, ForeignKey("TaskType.id"), primary_key=True)

    exercise = relationship("AlgoExercise", back_populates="task_type_associations")
    task_type = relationship("AlgoTaskType", lazy="selectin")
