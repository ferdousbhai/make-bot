# import os
import logging
import json
from typing import Optional
from contextlib import AsyncExitStack

from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPServerStdio
from dotenv import load_dotenv
# from pydantic_ai.models.openai import OpenAIModel
# from pydantic_ai.providers.openai import OpenAIProvider

from .chat_history import clear_chat, get_chat_history, add_messages_to_history


load_dotenv()

# XAI_API_KEY = os.getenv('XAI_API_KEY')
# if not XAI_API_KEY:
#     raise ValueError("XAI_API_KEY environment variable not set.")

logger = logging.getLogger(__name__)


def start_new_chat(ctx: RunContext[int]):
    """Start a new chat when a conversation topic is changed."""
    clear_chat(ctx.deps)


class AgentService:
    """Manages the lifecycle and interactions of the Pydantic-AI Agent using run_mcp_servers."""

    def __init__(self):
        self.agent: Optional[Agent] = None
        self._mcp_stack: Optional[AsyncExitStack] = None
        self._is_initialized = False

    async def initialize(self):
        """Initializes the agent and enters the run_mcp_servers context."""
        if self._is_initialized:
            logger.warning("Agent service already initialized.")
            return

        logger.info("Initializing AgentService...")
        try:
            # Load MCP server configurations from JSON file
            try:
                with open('mcp_servers_config.json', 'r') as f:
                    mcp_config = json.load(f)
                mcp_servers_config = mcp_config.get('mcpServers', {})
                logger.info(f"Loaded {len(mcp_servers_config)} MCP server configurations from mcp_servers_config.json")
            except FileNotFoundError:
                logger.warning("mcp_servers_config.json not found. No external MCP servers will be loaded.")
                mcp_servers_config = {}
            except json.JSONDecodeError:
                logger.error("Error decoding mcp_servers_config.json. Please check the file format.")
                mcp_servers_config = {}


            # Create MCPServer instances from the loaded configuration
            mcp_servers = []
            for name, config in mcp_servers_config.items():
                command = config.get('command')
                args = config.get('args', [])
                env = config.get('env') # Get environment variables if specified
                if command:
                    server = MCPServerStdio(
                        command, # Pass command as the first positional argument
                        args=args,
                        env=env # Pass environment variables
                    )
                    mcp_servers.append(server)
                    logger.debug(f"Created MCPServerStdio instance for server: {name}")
                else:
                    logger.warning(f"Skipping server '{name}' due to missing 'command' field in configuration.")

            # provider = OpenAIProvider(base_url='https://api.x.ai/v1', api_key=XAI_API_KEY)
            # model = OpenAIModel('grok-3-mini-beta', provider=provider)
            self.agent = Agent(
                'openai:o4-mini',
                deps_type=int,
                tools=[start_new_chat],
                mcp_servers=mcp_servers # Use the dynamically loaded servers
            )

            self._mcp_stack = AsyncExitStack()
            logger.info("Starting MCP servers via context manager...")
            await self._mcp_stack.enter_async_context(self.agent.run_mcp_servers())
            self._is_initialized = True
            logger.info("AgentService initialized and MCP servers started.")

        except Exception as e:
            logger.error(f"Failed to initialize AgentService: {e}", exc_info=True)
            await self.shutdown()
            raise

    async def shutdown(self):
        """Exits the run_mcp_servers context and cleans up."""
        if not self._mcp_stack:
            # If stack doesn't exist, it's either not initialized or already shut down.
            logger.warning("Agent service not running or already shut down.")
            return

        logger.info("Shutting down AgentService...")
        try:
            await self._mcp_stack.aclose()
            logger.info("MCP servers stopped via context manager.")
        except Exception as e:
            logger.error(f"Error shutting down MCP servers: {e}", exc_info=True)
        finally:
            self.agent = None
            self._mcp_stack = None
            self._is_initialized = False
            logger.info("AgentService shut down.")

    async def process_message(self, chat_id: int, user_input: str) -> str:
        """Processes a user message using the agent."""
        if not self.agent or not self._is_initialized:
            logger.error("Agent service not initialized. Cannot process message.")
            return "Sorry, the agent is not ready. Please try again later."

        current_chat_history = get_chat_history(chat_id)

        try:
            logger.debug(f"Running agent for chat_id {chat_id}...")
            result = await self.agent.run(
                user_input,
                deps=chat_id,
                message_history=current_chat_history
            )
            logger.debug(f"Agent response received for chat_id {chat_id}.")

            new_messages = result.new_messages()
            add_messages_to_history(chat_id, new_messages)
            logger.debug(f"Added {len(new_messages)} messages to history for chat_id {chat_id}")

            return result.output

        except Exception as e:
            logger.error(f"Error processing message for chat {chat_id}: {e}", exc_info=True)
            return "Sorry, I encountered an error while processing your request."