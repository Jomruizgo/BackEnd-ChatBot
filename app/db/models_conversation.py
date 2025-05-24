# app/db/models_conversation.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import BaseConversation

class ChatSession(BaseConversation):
    __tablename__ = "chat_sessions"
    id = Column(String(36), primary_key=True, index=True) # UUID o similar
    user_id = Column(String(255), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    session_data = Column(Text, nullable=True) # RENAMED: Used to be 'metadata'

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(BaseConversation):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False)
    sender = Column(String(50), nullable=False)  # "user" o "assistant"
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    # tool_calls = Column(Text, nullable=True) # JSON string de tool calls si el modelo pidió una
    # tool_responses = Column(Text, nullable=True) # JSON string de las respuestas de las tools

    session = relationship("ChatSession", back_populates="messages")