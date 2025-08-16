import asyncio
from datetime import datetime
import logging
import os

import logfire
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

    logger.info("Starting agent run...")
    agent_task = asyncio.create_task(agent.run(update.message.text, deps=deps))
    typing_task = None

    while not agent_task.done():
        try:
            # Only create new typing task if none exists or current one finished naturally (not cancelled)
            if not typing_task or (typing_task.done() and not typing_task.cancelled()):
                typing_task = deps.typing_task = asyncio.create_task(update.message.chat.send_chat_action(ChatAction.TYPING))
            # Wait for either bot to finish or typing indicator to need refresh
            await asyncio.wait(
                [agent_task, typing_task],
                return_when=asyncio.FIRST_COMPLETED
            )
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            if not agent_task.done(): agent_task.cancel()
            break

    # Cancel typing indicator after agent completes
    if typing_task and not typing_task.done():
        typing_task.cancel()
    
    # Handle typing task exceptions to prevent unhandled task errors
    if typing_task and typing_task.done() and not typing_task.cancelled():
        try:
            typing_task.result()
        except Exception:
            pass  # Ignore typing indicator errors
    logger.info("Agent run completed")

    # Handle bot task result
    try:
        # Get result to ensure any exceptions are handled
        agent_task.result()
        # Save conversation to database
        with Session(deps.engine) as session:
            session.add(ConversationTurn(
                chat_id=update.message.chat.id,
                user_message=update.message.text,
                assistant_replies=deps.assistant_replies,
                timestamp=datetime.fromtimestamp(update.message.date.timestamp())
            ))
            session.commit()
    except asyncio.CancelledError:
        await update.message.reply_text("Sorry, there was a connection problem. Please try again.")
    except UnexpectedModelBehavior:
        pass # Typically empty model response, expected when agent uses tools to respond
    except Exception as e:
        logger.error(f"Error processing message for chat {update.message.chat.id}: {e}", exc_info=True)

async def startup(application):

    logfire.configure(send_to_logfire='if-token-present')
    logfire.instrument_pydantic_ai()
    engine = create_engine(DATABASE_URL)
    SQLModel.metadata.create_all(engine)

    system_prompt = (
        "You are a helpful AI assistant powered by a Telegram bot. "
        "Use the reply_to_user tool to send your responses via the Telegram app. "
        "Use get_chat_history to gather context from previous messages. "
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