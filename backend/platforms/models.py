from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid


class PlatformCreate(BaseModel):
    id: str = Field(..., description="Unique platform identifier, e.g. 'pyrates'")
    name: str = Field(..., description="Human-readable platform name")
    language: str = Field("fr", description="Default language: 'fr' or 'en'")
    description: str = Field("", description="Short platform description")
    feedback_mode: str = Field("offline", description="'offline' or 'live'")
    platform_context: Optional[str] = Field(None, description="Platform pedagogical context text")
    live_student_prompt: Optional[str] = Field(None, description="Extra prompt block for live mode")


class PlatformContextChunk(BaseModel):
    """A single document chunk to be embedded and stored in the vector store."""
    section: str = Field(
        ...,
        description=(
            "Section type: 'curriculum', 'interaction_data', 'pedagogical_guidelines', "
            "'tone_style', 'feedback_system', 'characters', 'general'"
        ),
    )
    content: str = Field(..., description="The text content of this context chunk")


class PlatformContextUpload(BaseModel):
    chunks: list[PlatformContextChunk] = Field(
        ..., description="List of context chunks to upsert for this platform"
    )
    replace_section: Optional[str] = Field(
        None,
        description="If provided, delete all existing chunks of this section before inserting",
    )


class PlatformOut(BaseModel):
    id: str
    name: str
    language: str
    description: str
    feedback_mode: str
    platform_context: Optional[str] = None
    live_student_prompt: Optional[str] = None
    created_at: str
    context_chunk_count: int = 0


class PlatformUpdate(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    description: Optional[str] = None
    feedback_mode: Optional[str] = None
    platform_context: Optional[str] = None
    live_student_prompt: Optional[str] = None


class GeneralConfigOut(BaseModel):
    general_feedback_instructions: str
    updated_at: Optional[str] = None


class GeneralConfigUpdate(BaseModel):
    general_feedback_instructions: str


class PlatformConfigCreate(BaseModel):
    name: str
    vocabulary_to_use: Optional[str] = None
    vocabulary_to_avoid: Optional[str] = None
    teacher_comments: Optional[str] = None


class PlatformConfigUpdate(BaseModel):
    name: Optional[str] = None
    vocabulary_to_use: Optional[str] = None
    vocabulary_to_avoid: Optional[str] = None
    teacher_comments: Optional[str] = None


class PlatformConfigOut(BaseModel):
    id: int
    platform_id: str
    name: str
    is_active: bool
    vocabulary_to_use: Optional[str] = None
    vocabulary_to_avoid: Optional[str] = None
    teacher_comments: Optional[str] = None
    created_at: str
    updated_at: str
