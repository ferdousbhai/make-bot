import asyncio
from datetime import datetime
import functools
import logging
import os

from telegram import Update, Message
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction, ParseMode
import telegramify_markdown
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, UnexpectedModelBehavior
from sqlmodel import create_engine, Session, SQLModel, Field, select, Engine
from sqlalchemy import or_, func

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
MODEL_IDENTIFIER = os.environ['MODEL_IDENTIFIER'] 
DATABASE_URL = os.environ['DATABASE_URL']

chat_ids_str = os.getenv('ALLOWED_CHAT_IDS', '')
ALLOWED_CHAT_IDS = set(int(x.strip()) for x in chat_ids_str.strip('[]').replace(' ','').split(',') if x.strip()) if chat_ids_str else set()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class ConversationTurn(SQLModel, table=True):
    __tablename__ = "conversation_turns"
    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(index=True)
    user_message: str
    assistant_replies: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now, index=True)

class ChatDeps(BaseModel):
    telegram_message: Message
    engine: Engine
    assistant_replies: list[str]
    class Config:
        arbitrary_types_allowed = True

def is_user_authorized(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.message.chat_id
        if chat_id not in ALLOWED_CHAT_IDS:
            logger.warning(f"Unauthorized access from chat_id: {chat_id} for {func.__name__}")
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@is_user_authorized
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    message = "👋 Agent Ready! Send me a message."
    await update.message.reply_text(message)

@is_user_authorized
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    user_input = update.message.text

    logger.info(f"Received message from chat_id {chat_id}: {user_input}")

    deps = ChatDeps(telegram_message=update.message, engine=context.application.bot_data['engine'], assistant_replies=[])
    task = asyncio.create_task(process_message(context, deps))

    while not task.done():
        try:
            await update.message.chat.send_chat_action(ChatAction.TYPING)
            await asyncio.wait_for(asyncio.shield(task), timeout=4.0)
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            if not task.done(): task.cancel()
            break

    try:
        await task
    except asyncio.CancelledError as e:
        logger.warning(str(e))
        await update.message.reply_text("Sorry, there was a connection problem. Please try again.")

async def reply_to_user(ctx: RunContext[ChatDeps], message: str) -> bool | Exception:
    await ctx.deps.telegram_message.reply_text(telegramify_markdown.markdownify(message), parse_mode=ParseMode.MARKDOWN_V2)
    ctx.deps.assistant_replies.append(message)
    return True

async def get_chat_history(
    ctx: RunContext[ChatDeps],
    limit: int = 10,
    query: str | None = None,
    after_time: str | None = None,
    before_time: str | None = None,
    start_turn: int | None = None,
    end_turn: int | None = None
) -> list[dict]:
    """Get chat history with filtering capabilities.

    Args:
        limit: Maximum number of conversation turns to return (default: 10)
        query: Search term to filter messages containing this text
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
        get_chat_history(query="weather")

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
            after_dt = datetime.fromisoformat(after_time) if after_time else datetime.now()
            statement = statement.where(ConversationTurn.timestamp >= after_dt)

        if before_time:
            before_dt = datetime.fromisoformat(before_time) if before_time else datetime.now()
            statement = statement.where(ConversationTurn.timestamp <= before_dt)

        if query:
            statement = statement.where(
                or_(
                    func.to_tsvector('english', ConversationTurn.user_message).op('@@')(
                        func.plainto_tsquery('english', query)
                    ),
                    func.to_tsvector('english', func.array_to_string(ConversationTurn.assistant_replies, ' ')).op('@@')(
                        func.plainto_tsquery('english', query)
                    )
                )
            )

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


async def process_message(context: ContextTypes.DEFAULT_TYPE, deps: ChatDeps) -> None:
    try:
        await context.application.bot_data['agent'].run(deps.telegram_message.text, deps=deps)
    except UnexpectedModelBehavior as e:
        logger.info(str(e))
    except Exception as e:
        logger.error(f"Error processing message for chat {deps.telegram_message.chat.id}: {e}", exc_info=True)
        return

    with Session(deps.engine) as session:
        session.add(ConversationTurn(
            chat_id=deps.telegram_message.chat.id,
            user_message=deps.telegram_message.text,
            assistant_replies=deps.assistant_replies,
            timestamp=datetime.fromtimestamp(deps.telegram_message.date.timestamp())
        ))
        session.commit()


async def startup(application):
    logger.info("Initializing database...")
    engine = create_engine(DATABASE_URL)
    SQLModel.metadata.create_all(engine)

    system_prompt = (
        "You are a helpful AI assistant powered by a Telegram bot. "
        "Use the reply_to_user tool to send your responses via the Telegram app. "
        "Use get_chat_history to see conversation history (use it to gather context). "
        "Be conversational and helpful."
    )

    agent = Agent(
        MODEL_IDENTIFIER,
        deps_type=ChatDeps,
        system_prompt=system_prompt,
        tools=[reply_to_user, get_chat_history],
        instrument=True
    )

    # Register the engine and agent in bot_data
    application.bot_data['engine'] = engine
    application.bot_data['agent'] = agent
    logger.info("Database and agent initialized successfully.")

async def shutdown(application):
    engine = application.bot_data.get('engine')
    if engine:
        logger.info("Shutting down database...")
        engine.dispose()
        application.bot_data['engine'] = None
        logger.info("Database shut down successfully.")

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(startup).post_shutdown(shutdown).build()
    app.add_handlers([CommandHandler("start", start), MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)])
    logger.info("Starting bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling stopped.")

if __name__ == "__main__":
    main()