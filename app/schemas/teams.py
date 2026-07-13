from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("Team name cannot be empty or whitespace only")
        return name


class TeamMemberResponse(BaseModel):
    id: int
    user_id: str
    team_id: int
    role: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    owner_id: str
    created_at: datetime
    updated_at: datetime
    memberships: Optional[List[TeamMemberResponse]] = []

    model_config = ConfigDict(from_attributes=True)


class TeamMemberAdd(BaseModel):
    user_id: str
    role: Optional[str] = "member"

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        user_id = v.strip()
        if not user_id:
            raise ValueError("user_id cannot be empty")
        return user_id

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if v not in {"admin", "member", "viewer"}:
                raise ValueError("Role must be one of 'admin', 'member', or 'viewer'")
        return v


class TeamMemberUpdate(BaseModel):
    role: str


class InvitationCreate(BaseModel):
    email: str = Field(..., max_length=255)
    role: str = "member"

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        email = v.strip()
        if not email or "@" not in email:
            raise ValueError("Invalid email format")
        return email

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        role = v.strip()
        if role not in {"admin", "member", "viewer"}:
            raise ValueError("Role must be one of 'admin', 'member', or 'viewer'")
        return role


class InvitationResponse(BaseModel):
    id: int
    team_id: int
    email: str
    role: str
    token: str
    status: str
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvitationAccept(BaseModel):
    token: str



