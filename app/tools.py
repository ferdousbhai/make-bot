from datetime import datetime
from sqlmodel import Session, select
from sqlalchemy import or_, func
from pydantic_ai import RunContext
from telegram.constants import ParseMode
import telegramify_markdown
from app.models import ConversationTurn, ChatDeps


async def reply_to_user(ctx: RunContext[ChatDeps], message: str) -> bool | Exception:
    await ctx.deps.telegram_message.reply_text(telegramify_markdown.markdownify(message), parse_mode=ParseMode.MARKDOWN_V2)
    ctx.deps.assistant_replies.append(message)
    return True


async def get_chat_history(
    ctx: RunContext[ChatDeps],
    limit: int = 10,
    query: list[str] | None = None,
    after_time: str | None = None,
    before_time: str | None = None,
    start_turn: int | None = None,
    end_turn: int | None = None
) -> list[dict] | Exception:
    """Get chat history with filtering capabilities.

    Args:
        limit: Maximum number of conversation turns to return (default: 10)
        query: List of search terms to filter messages containing any of these terms
        after_time: ISO format datetime string to get messages after this time
        before_time: ISO format datetime string to get messages before this time
        start_turn: Starting turn index (0-based, supports negative indexing)
        end_turn: Ending turn index (0-based, supports negative indexing)

    Returns:
        List of conversation turns, each containing:
        - user_message: The user's input
        - assistant_replies: List of assistant responses
        - timestamp: ISO format timestamp

    Examples:
        # Get last 5 conversation turns
        get_chat_history(limit=5)

        # Search for messages containing "weather"
        get_chat_history(query=["weather"])

        # Search for pet-related messages
        get_chat_history(query=["cat", "dog", "pets"])

        # Get messages from the last hour
        get_chat_history(after_time="2024-01-01T12:00:00")

        # Get messages between specific times
        get_chat_history(after_time="2024-01-01T09:00:00", before_time="2024-01-01T17:00:00")

        # Get turns 5-10 (0-based indexing)
        get_chat_history(start_turn=5, end_turn=10)

        # Get last 3 turns using negative indexing
        get_chat_history(start_turn=-3)
    """
    with Session(ctx.deps.engine) as session:
        # Start with chat_id filter to match the current chat
        statement = select(ConversationTurn).where(ConversationTurn.chat_id == ctx.deps.telegram_message.chat.id)

        if after_time:
            after_dt = datetime.fromisoformat(after_time)
            statement = statement.where(ConversationTurn.timestamp >= after_dt)

        if before_time:
            before_dt = datetime.fromisoformat(before_time)
            statement = statement.where(ConversationTurn.timestamp <= before_dt)

        if query:
            # Create search conditions for each query term
            search_conditions = []
            for term in query:
                term_condition = or_(
                    func.to_tsvector('english', ConversationTurn.user_message).op('@@')(
                        func.plainto_tsquery('english', term)
                    ),
                    func.to_tsvector('english', func.array_to_string(ConversationTurn.assistant_replies, ' ')).op('@@')(
                        func.plainto_tsquery('english', term)
                    )
                )
                search_conditions.append(term_condition)

            # Combine all search conditions with OR (match any term)
            statement = statement.where(or_(*search_conditions))

        statement = statement.order_by(ConversationTurn.timestamp.asc())

        # Execute query
        result = session.exec(statement)
        rows = result.all()

        # Convert to list of dicts
        conversation_turns = []
        for row in rows:
            turn = {
                "user_message": row.user_message,
                "assistant_replies": row.assistant_replies,
                "timestamp": row.timestamp.isoformat()
            }
            conversation_turns.append(turn)

        # Apply turn-based filtering
        if start_turn is not None or end_turn is not None:
            total = len(conversation_turns)
            start_idx = max(0, min((start_turn if start_turn is not None and start_turn >= 0 else total + (start_turn or 0)), total))
            end_idx = max(start_idx, min((end_turn + 1 if end_turn is not None and end_turn >= 0 else total + (end_turn or -1) + 1) if end_turn is not None else total, total))
            conversation_turns = conversation_turns[start_idx:end_idx]

        # Apply limit
        return conversation_turns[-limit:] if limit > 0 else conversation_turns