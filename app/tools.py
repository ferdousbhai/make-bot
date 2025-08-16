from datetime import datetime, timedelta
from sqlmodel import Session, select
from sqlalchemy import or_, func
from pydantic_ai import RunContext
from telegram.constants import ParseMode
import telegramify_markdown
from app.models import ConversationTurn, ChatDeps


async def reply_to_user(ctx: RunContext[ChatDeps], message: str) -> bool | Exception:
    # Cancel typing indicator before sending reply
    if ctx.deps.typing_task and not ctx.deps.typing_task.done():
        ctx.deps.typing_task.cancel()

    await ctx.deps.telegram_message.reply_text(telegramify_markdown.markdownify(message), parse_mode=ParseMode.MARKDOWN_V2)
    ctx.deps.assistant_replies.append(message)
    return True


async def get_chat_history(
    ctx: RunContext[ChatDeps],
    turns: str = "-5:",
    query: list[str] | None = None,
    days: int | None = 30
) -> list[dict] | Exception:
    """Use it for chat context when relevant.

    Args:
        turns: Python slice syntax for selecting conversation turns (default: "-5:" for last 5)
        query: List of search terms to filter messages containing any of these terms
        days: Number of days to look back (default: 30, None for all messages)

    Returns:
        List of conversation turns, each containing:
        - user_message: The user's input
        - assistant_replies: List of assistant responses
        - timestamp: ISO format timestamp

    Examples:
        # Get last 5 conversation turns from last 30 days
        get_chat_history()

        # Get last 3 turns
        get_chat_history(turns="-3:")

        # Get turns 5-10
        get_chat_history(turns="5:10")

        # Search for messages containing "weather" from last 7 days
        get_chat_history(query=["weather"], days=7)

        # Search for pet-related messages from last 180 days
        get_chat_history(query=["cat", "dog", "pets"], days=180)

        # Get all messages (no time filter)
        get_chat_history(days=None)
    """
    with Session(ctx.deps.engine) as session:
        # Start with chat_id filter to match the current chat
        statement = select(ConversationTurn).where(ConversationTurn.chat_id == ctx.deps.telegram_message.chat.id)

        # Apply time filter
        if days is not None:
            after_dt = datetime.now() - timedelta(days=days)
            statement = statement.where(ConversationTurn.timestamp >= after_dt)

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

        # Apply slice-based filtering
        if turns:
            try:
                # Parse slice notation (e.g., "-5:", "2:8", ":")
                if ':' in turns:
                    parts = turns.split(':')
                    start = int(parts[0]) if parts[0] else None
                    end = int(parts[1]) if parts[1] else None
                    conversation_turns = conversation_turns[start:end]
                else:
                    # Single index
                    idx = int(turns)
                    conversation_turns = [conversation_turns[idx]]
            except (ValueError, IndexError):
                # Invalid slice syntax, return empty list
                conversation_turns = []

        return conversation_turns