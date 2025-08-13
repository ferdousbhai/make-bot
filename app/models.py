from datetime import datetime
from pydantic import BaseModel
from sqlmodel import SQLModel, Field
from sqlalchemy import JSON
from sqlalchemy.engine import Engine
from telegram import Message
import asyncio


class ConversationTurn(SQLModel, table=True):
    __tablename__ = "conversation_turns"
    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(index=True)
    user_message: str
    assistant_replies: list[str] = Field(default_factory=list, sa_type=JSON)
    timestamp: datetime = Field(default_factory=datetime.now, index=True)


class ChatDeps(BaseModel):
    telegram_message: Message
    engine: Engine
    assistant_replies: list[str]
    typing_task: asyncio.Task | None = None
    class Config:
        arbitrary_types_allowed = True