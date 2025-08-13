import asyncio
from datetime import datetime
import logging
import os

from pydantic_ai import Agent, UnexpectedModelBehavior
from sqlmodel import create_engine, Session, SQLModel
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ChatAction

from app.models import ConversationTurn, ChatDeps
from app.tools import reply_to_user, get_chat_history
from app.auth import is_user_authorized


BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
MODEL_IDENTIFIER = os.environ['MODEL_IDENTIFIER']
DATABASE_URL = os.environ['DATABASE_URL']


logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@is_user_authorized
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("👋 Agent Ready! Send me a message.")

@is_user_authorized
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    logger.info(f"Received message from chat_id {update.message.chat_id}: {update.message.text}")

    deps = ChatDeps(telegram_message=update.message, engine=context.application.bot_data['engine'], assistant_replies=[])
    agent = context.application.bot_data['agent']
    bot_task = asyncio.create_task(handle_message(deps, agent))
    typing_task = asyncio.create_task(update.message.chat.send_chat_action(ChatAction.TYPING))

    while not bot_task.done():
        try:
            # Wait for either bot to finish or typing indicator to need refresh
            done, _ = await asyncio.wait(
                [bot_task, typing_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # If typing task completed but bot still running, send new typing indicator
            if typing_task in done and not bot_task.done():
                typing_task = asyncio.create_task(update.message.chat.send_chat_action(ChatAction.TYPING))

        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            if not bot_task.done(): bot_task.cancel()
            break

    # Cancel any pending typing indicator
    if typing_task and not typing_task.done():
        typing_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError as e:
        logger.warning(str(e))
        await update.message.reply_text("Sorry, there was a connection problem. Please try again.")

async def handle_message(deps: ChatDeps, agent) -> None:
    try:
        logger.info("Running agent")
        await agent.run(deps.telegram_message.text, deps=deps) # agent uses provided tool to reply to the user
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

    application.bot_data['engine'] = engine
    application.bot_data['agent'] = agent
    logger.info("Database and agent initialized successfully.")

async def shutdown(application):
    engine = application.bot_data.get('engine')
    if engine:
        engine.dispose()
        logger.info("Database connection closed.")

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(startup).post_shutdown(shutdown).build()
    app.add_handlers([CommandHandler("start", start), MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)])
    logger.info("Starting bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling stopped.")

if __name__ == "__main__":
    main()