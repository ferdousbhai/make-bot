import os
import logging
import asyncio
import functools
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction

from app.agent import AgentService

load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MODEL_IDENTIFIER = os.getenv('MODEL_IDENTIFIER')
DATABASE_URL = os.getenv('DATABASE_URL')

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
if not MODEL_IDENTIFIER:
    raise ValueError("MODEL_IDENTIFIER environment variable not set")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

ALLOWED_CHAT_IDS_STR = os.getenv('ALLOWED_CHAT_IDS', '')
ALLOWED_CHAT_IDS = set()
if ALLOWED_CHAT_IDS_STR:
    try:
        clean_str = ALLOWED_CHAT_IDS_STR.strip('[]').replace(' ', '')
        ALLOWED_CHAT_IDS = set(int(chat_id.strip()) for chat_id in clean_str.split(',') if chat_id.strip())
    except ValueError:
        raise ValueError("Invalid format for ALLOWED_CHAT_IDS. Use comma-separated integers (brackets optional).")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

agent_service = None

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
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = "👋 Agent Ready! Send me a message."
    await update.message.reply_text(message)

@is_user_authorized
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    user_input = update.message.text
    message_timestamp = update.message.date.timestamp()

    logger.info(f"Received message from chat_id {chat_id}: {user_input}")

    agent_task = asyncio.create_task(
        agent_service.process_message(chat_id, user_input, update.message, message_timestamp)
    )

    while not agent_task.done():
        try:
            await update.message.chat.send_chat_action(ChatAction.TYPING)
            await asyncio.wait_for(asyncio.shield(agent_task), timeout=4.0)
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.error(f"Error during processing or typing indicator: {e}", exc_info=True)
            if not agent_task.done():
                agent_task.cancel()
            break

    try:
        await agent_task
    except asyncio.CancelledError:
        logger.warning("Agent task was cancelled.")
        await update.message.reply_text("Sorry, the request was cancelled.")
    except Exception as e:
        logger.error(f"Error during agent processing: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I encountered an error while processing your request.")

async def initialize_agent_service(application: Application):
    global agent_service
    agent_service = AgentService(DATABASE_URL)
    await agent_service.initialize()

async def shutdown_agent_service(application: Application):
    if agent_service:
        await agent_service.shutdown()

def main() -> None:
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(initialize_agent_service)
        .post_shutdown(shutdown_agent_service)
        .build()
    )

    handlers = [
        CommandHandler("start", start),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    ]

    for handler in handlers:
        application.add_handler(handler)

    logger.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling stopped.")

if __name__ == "__main__":
    main()