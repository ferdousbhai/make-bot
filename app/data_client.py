import logging
from datetime import datetime
from typing import Literal
from sqlmodel import Field, SQLModel, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

logger = logging.getLogger(__name__)

class ChatHistory(SQLModel, table=True):
    """SQLModel for chat history table."""
    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(index=True)
    role: str = Field(max_length=20)
    content: str
    timestamp: datetime = Field(default_factory=datetime.now, index=True)

class PostgreSQLDataClient:
    """PostgreSQL-based data client using SQLModel for Railway deployment."""
    def __init__(self, database_url: str):
        # Convert Railway PostgreSQL URL to SQLAlchemy async URL
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        self.database_url = database_url
        self._engine: AsyncEngine | None = None
        self._session_maker: sessionmaker | None = None

    def _parse_timestamp(self, timestamp: str | None) -> datetime:
        return datetime.fromisoformat(timestamp.replace('Z', '+00:00')) if timestamp else datetime.now()

    async def _ensure_initialized(self):
        if not self._engine:
            await self.init_pool()

    async def init_pool(self):
        if not self._engine:
            self._engine = create_async_engine(self.database_url, echo=True)
            self._session_maker = sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)
            await self._ensure_tables()

    async def close_pool(self):
        if self._engine:
            await self._engine.dispose()
            self._engine = self._session_maker = None

    async def _ensure_tables(self):
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_chat_history_content_search "
                "ON chat_history USING gin(to_tsvector('english', content))"
            ))

    async def get_chat_history(
        self,
        chat_id: int,
        limit: int = 10,
        query: str | None = None,
        after_time: str | None = None,
        before_time: str | None = None,
        start_turn: int | None = None,
        end_turn: int | None = None,
        role_filter: Literal["user", "assistant"] | None = None
    ) -> list[dict]:
        """Get chat history with advanced filtering capabilities."""
        await self._ensure_initialized()

        async with self._session_maker() as session:
            # Start with base query
            statement = select(ChatHistory).where(ChatHistory.chat_id == chat_id)

            # Add time filtering
            if after_time:
                after_dt = self._parse_timestamp(after_time)
                statement = statement.where(ChatHistory.timestamp >= after_dt)

            if before_time:
                before_dt = self._parse_timestamp(before_time)
                statement = statement.where(ChatHistory.timestamp <= before_dt)

            # Add role filtering
            if role_filter:
                statement = statement.where(ChatHistory.role == role_filter)

            # Add text search
            if query:
                statement = statement.where(ChatHistory.content.ilike(f"%{query}%"))

            # Order by timestamp
            statement = statement.order_by(ChatHistory.timestamp.asc())

            # Execute query
            result = await session.exec(statement)
            rows = result.all()

            # Convert to list of dicts
            messages = [
                {
                    "role": row.role,
                    "content": row.content,
                    "timestamp": row.timestamp.isoformat()
                }
                for row in rows
            ]

            # Apply turn-based filtering
            if start_turn is not None or end_turn is not None:
                total = len(messages)
                start_idx = max(0, min((start_turn if start_turn is not None and start_turn >= 0 else total + (start_turn or 0)), total))
                end_idx = max(start_idx, min((end_turn + 1 if end_turn is not None and end_turn >= 0 else total + (end_turn or -1) + 1) if end_turn is not None else total, total))
                messages = messages[start_idx:end_idx]

            # Apply limit
            return messages[-limit:] if limit > 0 else messages

    async def add_message(self, chat_id: int, role: str, content: str, timestamp: str | None = None) -> None:
        await self._ensure_initialized()
        async with self._session_maker() as session:
            session.add(ChatHistory(
                chat_id=chat_id, role=role, content=content, 
                timestamp=self._parse_timestamp(timestamp)
            ))
            await session.commit()

