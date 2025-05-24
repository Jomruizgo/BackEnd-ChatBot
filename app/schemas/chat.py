# app/schemas/chat.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class ChatMessageBase(BaseModel):
    message: str

class ChatMessageCreate(ChatMessageBase):
    user_id: Optional[str] = None # Podrías obtenerlo de un token JWT en un sistema real

class ChatMessageResponse(BaseModel):
    session_id: str
    response: str
    sender: str = "assistant"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tool_used: Optional[str] = None # Para indicar si se usó una tool
    tool_input: Optional[Dict[str, Any]] = None # Argumentos de la tool

class SessionCreate(BaseModel):
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class SessionResponse(BaseModel):
    session_id: str
    user_id: Optional[str]
    created_at: datetime
    metadata: Optional[Dict[str, Any]]