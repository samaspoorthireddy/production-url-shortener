from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        content = v.strip()
        if not content:
            raise ValueError("Comment content cannot be empty or whitespace only")
        return content


class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        content = v.strip()
        if not content:
            raise ValueError("Comment content cannot be empty or whitespace only")
        return content


class CommentResponse(BaseModel):
    id: int
    thread_id: int
    user_id: str
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ThreadCreate(BaseModel):
    target_type: str
    target_id: int


class ThreadResponse(BaseModel):
    id: int
    target_type: str
    target_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

