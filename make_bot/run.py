import logging
import os
import asyncio
import functools
from dotenv import load_dotenv

from telegramify_markdown import markdownify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction, ParseMode

from .agent import AgentService
from .chat_history import set_chat_context

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set.")

# Load and parse allowed chat IDs
ALLOWED_CHAT_IDS_STR = os.getenv('ALLOWED_CHAT_IDS', '')
ALLOWED_CHAT_IDS = set()
if ALLOWED_CHAT_IDS_STR:
    try:
        ALLOWED_CHAT_IDS = set(int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_STR.split(','))
        if not ALLOWED_CHAT_IDS:
            logging.warning("ALLOWED_CHAT_IDS is set but empty. No users will be allowed.")
        else:
            logging.info(f"Allowed chat IDs: {ALLOWED_CHAT_IDS}")
    except ValueError:
        logging.error("Invalid format for ALLOWED_CHAT_IDS. Please provide a comma-separated list of integers.", exc_info=True)
        # Keep ALLOWED_CHAT_IDS empty, effectively blocking everyone if the format is wrong
else:
    logging.warning("ALLOWED_CHAT_IDS environment variable not set. No users will be allowed.")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

agent_service = AgentService()

# --- Decorator for authorization ---
def authorized_only(func):
    """Decorator to check if the user is authorized before running the handler."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.message.chat_id
        if chat_id not in ALLOWED_CHAT_IDS:
            logger.warning(f"Unauthorized access attempt from chat_id: {chat_id} for {func.__name__}")
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return

        # If authorized, run the original handler function
        return await func(update, context, *args, **kwargs)
    return wrapper

# Command handlers
@authorized_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    message = "👋 Agent Ready! Send me a message.\n\n_(Note: Chat history is maintained only for the current session and is not stored permanently. The agent has no long-term memory across sessions or restarts.)_"
    await update.message.reply_text(markdownify(message), parse_mode=ParseMode.MARKDOWN_V2)

@authorized_only
async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clears the chat history and context for the user."""
    chat_id = update.message.chat_id
    logger.info(f"Received /new command from chat_id {chat_id}. Clearing context and history.")
    set_chat_context(chat_id, "")  # Empty context will trigger history clearing
    message = "🧹 New chat started! Your previous conversation history and context are cleared.\n\n_(Note: Chat history is maintained only for the current session and is not stored permanently. The agent has no long-term memory across sessions or restarts.)_"
    await update.message.reply_text(markdownify(message), parse_mode=ParseMode.MARKDOWN_V2)

# Message handlers
@authorized_only
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to the user message using the agent."""
    if not update.message or not update.message.text:
        return
    chat_id = update.message.chat_id
    user_input = update.message.text
    message_timestamp = update.message.date.timestamp()

    logger.info(f"Received message from chat_id {chat_id}: {user_input}")

    # Create a wrapper function for reply_text that matches the expected signature
    async def reply_text_wrapper(text: str, **kwargs):
        return await update.message.reply_text(text, **kwargs)

    agent_task = asyncio.create_task(agent_service.process_message(chat_id, user_input, reply_text_wrapper, message_timestamp))

    # Send typing indicator periodically while the agent is working
    while not agent_task.done():
        try:
            await update.message.chat.send_chat_action(ChatAction.TYPING)
            await asyncio.wait_for(asyncio.shield(agent_task), timeout=4.0) # Check agent task completion
        except asyncio.TimeoutError:
            pass # Agent task hasn't finished, continue loop
        except Exception as e:
            logger.error(f"Error during agent processing or typing indicator: {e}", exc_info=True)
            if not agent_task.done():
                agent_task.cancel()
            break # Exit the typing loop

    try:
        await agent_task # Wait for completion, agent handles its own responses
    except asyncio.CancelledError:
        logger.warning("Agent task was cancelled.")
        await update.message.reply_text("Sorry, the request was cancelled.")
    except Exception as e:
        logger.error(f"Error during agent processing: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I encountered an error while processing your request.")

async def post_init_callback(application: Application):
    """Callback function to initialize the agent after the application starts."""
    logger.info("Bot started, initializing agent service...")
    await agent_service.initialize()
    logger.info("Agent service initialized.")

async def post_shutdown_callback(application: Application):
    """Callback function to shut down the agent before the application stops."""
    logger.info("Bot shutting down, stopping agent service...")
    await agent_service.shutdown()
    logger.info("Agent service shut down.")

def main() -> None:
    """Start the bot."""
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init_callback)
        .post_shutdown(post_shutdown_callback)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_chat))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES) # Run the bot
    logger.info("Bot polling stopped.")

if __name__ == "__main__":
    main()