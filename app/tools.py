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
    limit: int = 5,
    query: list[str] | None = None,
    days: int | None = 30,
    start_turn: int | None = None,
    end_turn: int | None = None
) -> list[dict] | Exception:
    """Use it for chat context when relevant.

    Args:
        limit: Maximum number of conversation turns to return (default: 5)
        query: List of search terms to filter messages containing any of these terms
        days: Number of days to look back (default: 30, None for all messages)
        start_turn: Starting turn index (0-based, supports negative indexing)
        end_turn: Ending turn index (0-based, supports negative indexing)

    Returns:
        List of conversation turns, each containing:
        - user_message: The user's input
        - assistant_replies: List of assistant responses
        - timestamp: ISO format timestamp

    Examples:
        # Get last 5 conversation turns from last 30 days
        get_chat_history()

        # Search for messages containing "weather" from last 7 days
        get_chat_history(query=["weather"], days=7)

        # Search for pet-related messages from last 180 days
        get_chat_history(query=["cat", "dog", "pets"], days=180)

        # Get messages from last day
        get_chat_history(days=1)

        # Get all messages (no time filter)
        get_chat_history(days=None)

        # Get turns 5-10 (0-based indexing)
        get_chat_history(start_turn=5, end_turn=10)

        # Get last 3 turns using negative indexing
        get_chat_history(start_turn=-3)
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

        # Apply turn-based filtering
        if start_turn is not None or end_turn is not None:
            total = len(conversation_turns)
            start_idx = max(0, min((start_turn if start_turn is not None and start_turn >= 0 else total + (start_turn or 0)), total))
            end_idx = max(start_idx, min((end_turn + 1 if end_turn is not None and end_turn >= 0 else total + (end_turn or -1) + 1) if end_turn is not None else total, total))
            conversation_turns = conversation_turns[start_idx:end_idx]

        # Apply limit
        return conversation_turns[-limit:] if limit > 0 else conversation_turns