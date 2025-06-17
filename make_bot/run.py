import logging
import asyncio
import functools

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction, ParseMode
import telegramify_markdown

from .agent import AgentService
from .chat_history import set_chat_context
from .config import CONFIG

# Setup logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

agent_service = AgentService()

def is_user_authorized(func):
    """Decorator to check if user is authorized to use the bot."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.message.chat_id
        if chat_id not in CONFIG.bot.allowed_chat_ids:
            logger.warning(f"Unauthorized access from chat_id: {chat_id} for {func.__name__}")
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@is_user_authorized
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    message = ("👋 Agent Ready! Send me a message.\n\n"
              "Note: Chat history is maintained only for the current session and is not stored permanently. "
              "The agent has no long-term memory across sessions or restarts.")
    await update.message.reply_text(message)

@is_user_authorized
async def start_new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /new command - clear chat history and context."""
    chat_id = update.message.chat_id
    logger.info(f"Received /new command from chat_id {chat_id}. Clearing context and history.")
    set_chat_context(chat_id, "")  # Empty context triggers history clearing

    message = ("🧹 New chat started! Your previous conversation history and context are cleared.\n\n")
    await update.message.reply_text(message)

@is_user_authorized
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user messages with agent processing."""
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    user_input = update.message.text
    message_timestamp = update.message.date.timestamp()

    logger.info(f"Received message from chat_id {chat_id}: {user_input}")

    # Create reply wrapper
    async def reply_wrapper(text: str, **kwargs):
        return await update.message.reply_text(text, **kwargs)

    # Process message with typing indicators
    agent_task = asyncio.create_task(
        agent_service.process_message(chat_id, user_input, reply_wrapper, message_timestamp)
    )

    # Send typing indicators while processing
    while not agent_task.done():
        try:
            await update.message.chat.send_chat_action(ChatAction.TYPING)
            await asyncio.wait_for(asyncio.shield(agent_task), timeout=4.0)
        except asyncio.TimeoutError:
            continue  # Keep showing typing
        except Exception as e:
            logger.error(f"Error during processing or typing indicator: {e}", exc_info=True)
            if not agent_task.done():
                agent_task.cancel()
            break

    # Wait for final result
    try:
        await agent_task
    except asyncio.CancelledError:
        logger.warning("Agent task was cancelled.")
        await update.message.reply_text("Sorry, the request was cancelled.")
    except Exception as e:
        logger.error(f"Error during agent processing: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I encountered an error while processing your request.")

async def initialize_agent_service(application: Application):
    """Initialize agent service after bot starts."""
    await agent_service.initialize()

async def shutdown_agent_service(application: Application):
    """Shutdown agent service before bot stops."""
    logger.info("Bot shutting down, stopping agent service...")
    await agent_service.shutdown()
    logger.info("Agent service shut down.")

def main() -> None:
    """Start the bot."""
    application = (
        Application.builder()
        .token(CONFIG.bot.bot_token)
        .post_init(initialize_agent_service)
        .post_shutdown(shutdown_agent_service)
        .build()
    )

    # Add handlers
    handlers = [
        CommandHandler("start", start),
        CommandHandler("new", start_new_chat),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    ]

    for handler in handlers:
        application.add_handler(handler)

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling stopped.")

if __name__ == "__main__":
    main()