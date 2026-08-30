"""
Authentication models for access codes and sessions.
"""

from typing import Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class AccessCodeInfo(BaseModel):
    """Access code information"""
    access_code: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    enabled: bool = True
    last_used: Optional[datetime] = None
    usage_count: int = 0
    max_conversations: Optional[int] = None  # Access code maximum conversation limit, None means unlimited
    conversation_count: int = 0  # Number of conversations used with this access code

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class AuthConfig(BaseModel):
    """Server authentication configuration"""
    version: str = "1.0"
    access_codes: Dict[str, AccessCodeInfo] = Field(default_factory=dict)
    settings: Dict = Field(default_factory=lambda: {
        "session_timeout_minutes": 60,
        "max_sessions_per_user": 10
    })

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class SessionInfo(BaseModel):
    """Session information"""
    session_id: str
    user_id: str
    created_at: datetime
    last_accessed: datetime
    message_count: int = 0

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }