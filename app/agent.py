import os
import logging
from typing import Literal
from dataclasses import dataclass
from dotenv import load_dotenv

from pydantic_ai import Agent, RunContext, UnexpectedModelBehavior
from telegram import Message
from telegram.constants import ParseMode
import telegramify_markdown

from .data_client import PostgreSQLDataClient

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class ChatDeps:
    chat_id: int
    telegram_message: Message
    data_client: PostgreSQLDataClient


model_identifier = os.getenv('MODEL_IDENTIFIER')
if not model_identifier:
    raise ValueError("MODEL_IDENTIFIER environment variable not set")

system_prompt = (
    "You are a helpful AI assistant powered by a Telegram bot. "
    "Use the reply_to_user tool to send your responses via the Telegram app. "
    "Use get_chat_history to see conversation history (use it to gather context). "
    "Be conversational and helpful."
)

agent = Agent(
    model_identifier,
    deps_type=ChatDeps,
    system_prompt=system_prompt,
    instrument=True
)


@agent.tool
async def reply_to_user(ctx: RunContext[ChatDeps], message: str):
    try:
        formatted_message = telegramify_markdown.markdownify(message)
        await ctx.deps.telegram_message.reply_text(formatted_message, parse_mode=ParseMode.MARKDOWN_V2)
        await ctx.deps.data_client.add_message(ctx.deps.chat_id, "assistant", message)
        return "Message sent to user successfully"
    except Exception as e:
        logger.error(f"Error sending message to user: {e}", exc_info=True)
        return f"Failed to send message: {str(e)}"


@agent.tool
async def get_chat_history(
    ctx: RunContext[ChatDeps],
    limit: int = 10,
    query: str | None = None,
    after_time: str | None = None,
    before_time: str | None = None,
    start_turn: int | None = None,
    end_turn: int | None = None,
    role_filter: Literal["user", "assistant"] | None = None
) -> list[dict]:
    return await ctx.deps.data_client.get_chat_history(
        chat_id=ctx.deps.chat_id,
        limit=limit,
        query=query,
        after_time=after_time,
        before_time=before_time,
        start_turn=start_turn,
        end_turn=end_turn,
        role_filter=role_filter
    )


class AgentService:

    def __init__(self, database_url: str):
        self.agent = agent  # Use the global agent instance
        self.database_url = database_url
        self.data_client = None
        self._is_initialized = False

    async def initialize(self):
        if self._is_initialized:
            logger.warning("Agent service already initialized.")
            return

        logger.info("Initializing AgentService...")
        try:
            # Initialize database client
            self.data_client = PostgreSQLDataClient(self.database_url)
            await self.data_client.init_pool()

            self._is_initialized = True
            logger.info("AgentService initialized successfully.")

        except Exception as e:
            logger.error(f"Failed to initialize AgentService: {e}", exc_info=True)
            await self.shutdown()
            raise

    async def shutdown(self):
        if not self._is_initialized:
            logger.warning("Agent service not running or already shut down.")
            return

        logger.info("Shutting down AgentService...")
        try:
            # Close database client
            if self.data_client:
                await self.data_client.close_pool()
                self.data_client = None

            self._is_initialized = False
            logger.info("AgentService shut down successfully.")
        except Exception as e:
            logger.error(f"Error shutting down AgentService: {e}", exc_info=True)

    async def process_message(self, chat_id: int, user_input: str, telegram_message: Message, message_timestamp: float) -> str:
        if not self._is_initialized:
            logger.error("Agent service not initialized. Cannot process message.")
            return "Sorry, the agent is not ready. Please try again later."

        await self.data_client.add_message(chat_id, "user", user_input)

        deps = ChatDeps(chat_id=chat_id, telegram_message=telegram_message, data_client=self.data_client)

        try:
            pass

            logger.debug(f"Running agent for chat_id {chat_id}...")
            result = await self.agent.run(
                user_input,
                deps=deps
            )
            logger.debug(f"Agent response received for chat_id {chat_id}.")

            logger.debug(f"Messages added to history via reply_to_user tool for chat_id {chat_id}")

            return result.output

        except UnexpectedModelBehavior as e:
                logger.info(f"Tool-only response: {e}")
                return

        except Exception as e:
            logger.error(f"Error processing message for chat {chat_id}: {e}", exc_info=True)
            return "Sorry, I encountered an error while processing your request."