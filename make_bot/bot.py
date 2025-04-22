import logging
import os
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction

from .agent import AgentService

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set.")


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Create a single instance of AgentService
agent_service = AgentService()


# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text("👋 Agent Ready! Send me a message.")

# Message handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to the user message using the agent."""
    chat_id = update.message.chat_id
    user_input = update.message.text
    if not user_input:
        return

    logger.info(f"Received message from chat_id {chat_id}: {user_input}")

    # Indicate activity
    await update.message.chat.send_action(ChatAction.TYPING)

    # Process the message using the agent service instance
    agent_response = await agent_service.process_message(chat_id, user_input)
    await update.message.reply_text(agent_response)


async def post_init_callback(application: Application):
    """Callback function to initialize the agent after the application starts."""
    logger.info("Bot started, initializing agent service...")
    await agent_service.initialize() # Call initialize on the instance
    logger.info("Agent service initialized.")

async def post_shutdown_callback(application: Application):
    """Callback function to shut down the agent before the application stops."""
    logger.info("Bot shutting down, stopping agent service...")
    await agent_service.shutdown() # Call shutdown on the instance
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting bot polling...")
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling stopped.") # when Ctrl-C is pressed


if __name__ == "__main__":
    main()