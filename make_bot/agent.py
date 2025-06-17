import logging
import json
import os
from typing import Optional, Callable, Any, Awaitable, List, Dict
from dataclasses import dataclass

import logfire
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPServerStdio
from dotenv import load_dotenv
from telegramify_markdown import telegramify
from telegram.constants import ParseMode

from .chat_history import (
    get_chat_history, add_messages_to_history, get_chat_context, set_chat_context,
    search_chat_history_keywords, get_chat_history_range, get_chat_history_by_time
)
from .context_manager import ensure_context_fits
from .prompt_loader import get_system_prompt, ModelType


load_dotenv()
ORCHESTRATOR_MODEL_IDENTIFIER = os.getenv('ORCHESTRATOR_MODEL_IDENTIFIER', 'groq:llama-3.1-8b-instant')
EXPERT_MODEL_IDENTIFIER = os.getenv('EXPERT_MODEL_IDENTIFIER', 'anthropic:claude-sonnet-4-latest')

logger = logging.getLogger(__name__)


@dataclass
class ChatDeps:
    chat_id: int
    reply_text: Callable[[str], Awaitable[Any]]
    mcp_servers_config: Dict[str, Any]


# =============================================================================
# AGENT TOOLS - All tools available to the AI model (excluding MCP servers)
# =============================================================================

async def reply_to_user(ctx: RunContext[ChatDeps], message: str):
    """Send a message to the user via Telegram.
    Use this tool to send responses directly to the user in markdown format.
    The message will be automatically formatted and chunked for Telegram.
    """
    try:
        chunks = await telegramify(message)
        for chunk in chunks:
            await ctx.deps.reply_text(chunk.content, parse_mode=ParseMode.MARKDOWN_V2)
        return "Message sent to user successfully"
    except Exception as e:
        logger.error(f"Error sending message to user: {e}", exc_info=True)
        return f"Failed to send message: {str(e)}"


def update_chat_context(ctx: RunContext[ChatDeps], context: str):
    """Update the conversation context for the current chat.

    Use this tool to maintain a running summary of the conversation. Set context
    to empty string to start a completely new conversation (clears history).

    Args:
        context: The context/summary to store. Use "" to clear and start fresh.
    """
    logger.info(f"Updating chat context for chat_id: {ctx.deps.chat_id}")
    set_chat_context(ctx.deps.chat_id, context)
    current_context = get_chat_context(ctx.deps.chat_id)
    return f"Context updated. Current context: {current_context[:200]}{'...' if len(current_context) > 200 else ''}"




async def get_expert_response(ctx: RunContext[ChatDeps], query: str, context: str = "", mcp_servers: List[str] = None):
    """Consult a more powerful expert model for complex tasks and analysis.

    Use this tool when you encounter queries that require:
    - Deep domain expertise
    - Complex mathematical or scientific analysis
    - Extensive research or knowledge synthesis
    - Creative tasks requiring sophisticated reasoning
    - Technical questions beyond your current capabilities

    Args:
        query: The specific question or task to ask the expert model
        context: Additional context or background information for the expert
        mcp_servers: List of MCP server names to provide to the expert. Choose based on task requirements:
            - "run-python": For tasks requiring Python code execution, data analysis, calculations, 
              scientific computing, chart generation, or any programming tasks
            - "investor": For investment analysis, financial planning, market research, 
              stock analysis, or economic questions
            - "brave-search": For current events, recent information, web research, 
              fact-checking, or when up-to-date information is needed
            If None or empty list, expert will work without external tools.
            Use list_available_mcp_servers() to see currently configured servers.
    
    Examples:
        - For data analysis: mcp_servers=["run-python"]
        - For investment questions: mcp_servers=["investor"] 
        - For current events: mcp_servers=["brave-search"]
        - For complex research: mcp_servers=["brave-search", "run-python"]
        - For pure reasoning: mcp_servers=[] or mcp_servers=None
    """
    logger.info(f"Consulting expert model for chat_id {ctx.deps.chat_id}: {query[:100]}...")

    try:
        expert_prompt = get_system_prompt(ModelType.EXPERT, context=context)

        # Create MCP servers for expert agent based on requested servers
        if mcp_servers is None:
            mcp_servers = []
        
        available_servers = ctx.deps.mcp_servers_config
        selected_mcp_servers = []
        
        for server_name in mcp_servers:
            if server_name in available_servers and available_servers[server_name].get('command'):
                config = available_servers[server_name]
                selected_mcp_servers.append(
                    MCPServerStdio(config['command'], args=config.get('args', []), env=config.get('env'))
                )
                logger.info(f"Adding MCP server '{server_name}' to expert agent")
            else:
                logger.warning(f"Requested MCP server '{server_name}' not found or not configured")
        
        logger.info(f"Expert agent will use {len(selected_mcp_servers)} MCP servers: {mcp_servers}")

        # Expert agent has selected MCP servers but no custom tools
        if selected_mcp_servers:
            expert_agent = Agent(
                EXPERT_MODEL_IDENTIFIER,
                system_prompt=expert_prompt,
                mcp_servers=selected_mcp_servers
            )
        else:
            # No MCP servers requested, create agent without them
            expert_agent = Agent(
                EXPERT_MODEL_IDENTIFIER,
                system_prompt=expert_prompt
            )

        # Ensure expert query fits within expert model limits
        _, compressed_query_list = ensure_context_fits(
            system_prompt=expert_prompt,
            context="",
            chat_history=[query],  # Treat query as single message
            user_input="",
            model_identifier=EXPERT_MODEL_IDENTIFIER
        )

        # Use compressed query if compression was applied
        final_query = compressed_query_list[0] if compressed_query_list else query

        # Run expert agent (with or without MCP servers)
        if selected_mcp_servers:
            async with expert_agent.run_mcp_servers():
                result = await expert_agent.run(final_query)
        else:
            result = await expert_agent.run(final_query)

        logger.info(f"Expert consultation completed for chat_id {ctx.deps.chat_id}")
        return f"Expert Response:\n\n{result.output}"

    except Exception as e:
        logger.error(f"Error consulting expert model: {e}", exc_info=True)
        return f"Expert consultation failed: {str(e)}"


def list_available_mcp_servers(ctx: RunContext[ChatDeps]) -> str:
    """List all available MCP servers that can be provided to the expert model.
    
    Use this tool to see what MCP servers are available before calling get_expert_response.
    """
    if not ctx.deps.mcp_servers_config:
        return "No MCP servers are configured."
    
    server_list = []
    for name, config in ctx.deps.mcp_servers_config.items():
        if config.get('command'):
            # Try to infer purpose from server name
            if 'python' in name.lower():
                purpose = "Python code execution and data analysis"
            elif 'search' in name.lower() or 'brave' in name.lower():
                purpose = "Web search and current information lookup"
            elif 'investor' in name.lower() or 'finance' in name.lower():
                purpose = "Investment, finance, and market analysis"
            else:
                purpose = "General purpose tool"
            
            server_list.append(f"- {name}: {purpose}")
    
    return "Available MCP servers:\n" + "\n".join(server_list)


def search_chat_history_tool(
    ctx: RunContext[ChatDeps],
    keywords: List[str] = None,
    start_turn: int = None,
    end_turn: int = None,
    minutes_ago_start: int = None,
    minutes_ago_end: int = None,
    max_results: int = 10
):
    """Search and retrieve chat history using flexible criteria.

    This tool combines keyword search, turn-based lookup, and time-based retrieval.
    Choose the appropriate parameters based on what you're looking for:

    - For keyword search: Use 'keywords' parameter
    - For turn-based lookup: Use 'start_turn' and 'end_turn' parameters
    - For time-based lookup: Use 'minutes_ago_start' and optionally 'minutes_ago_end'
    - Combine parameters as needed

    Args:
        keywords: List of keywords to search for (case-insensitive OR search)
        start_turn: Starting turn (negative numbers count from end, e.g., -30 = 30 turns ago)
        end_turn: Ending turn (negative numbers count from end, e.g., -1 = most recent)
        minutes_ago_start: How many minutes back to start looking (older boundary)
        minutes_ago_end: How many minutes back to stop looking (newer boundary, default: 0 = now)
        max_results: Maximum number of matching messages to return (default: 10)

    Examples:
        - search_chat_history_tool(keywords=["python", "coding", "programming"])
        - search_chat_history_tool(start_turn=-20, end_turn=-10)  # Turns 20-10 ago
        - search_chat_history_tool(minutes_ago_start=30)  # Last 30 minutes
        - search_chat_history_tool(minutes_ago_start=60, minutes_ago_end=30)  # 60-30 minutes ago
        - search_chat_history_tool(keywords=["API"], start_turn=-50, end_turn=-30)  # Keyword + range
        - search_chat_history_tool(keywords=["bug"], minutes_ago_start=120, minutes_ago_end=60)  # Keyword + time range
    """
    chat_id = ctx.deps.chat_id

    # Determine search method based on parameters
    if keywords and (start_turn is not None or end_turn is not None):
        # Combined keyword + turn range search
        if start_turn is None:
            start_turn = -30
        if end_turn is None:
            end_turn = -1

        # Get messages in range first
        range_messages = get_chat_history_range(chat_id, start_turn, end_turn)

        # Then filter by keywords
        keywords_lower = [kw.lower() for kw in keywords]
        matches = []
        for msg in range_messages:
            msg_str = str(msg).lower()
            if any(keyword in msg_str for keyword in keywords_lower):
                matches.append(str(msg))
                if len(matches) >= max_results:
                    break

        if not matches:
            return f"No messages found containing {keywords} in turns {start_turn} to {end_turn}"
        return f"Found {len(matches)} messages containing {keywords} in turns {start_turn} to {end_turn}:\n\n" + "\n".join(f"- {msg}" for msg in matches)

    elif keywords and minutes_ago_start is not None:
        # Combined keyword + time search
        minutes_ago_end_val = minutes_ago_end if minutes_ago_end is not None else 0
        time_messages = get_chat_history_by_time(chat_id, minutes_ago_start, minutes_ago_end_val)

        # Filter by keywords
        keywords_lower = [kw.lower() for kw in keywords]
        matches = []
        for msg in time_messages:
            msg_str = str(msg).lower()
            if any(keyword in msg_str for keyword in keywords_lower):
                matches.append(str(msg))
                if len(matches) >= max_results:
                    break

        time_desc = f"{minutes_ago_start} minutes ago" if minutes_ago_end_val == 0 else f"{minutes_ago_start}-{minutes_ago_end_val} minutes ago"
        if not matches:
            return f"No messages found containing {keywords} from {time_desc}"
        return f"Found {len(matches)} messages containing {keywords} from {time_desc}:\n\n" + "\n".join(f"- {msg}" for msg in matches)

    elif keywords:
        # Pure keyword search
        results = search_chat_history_keywords(chat_id, keywords, max_results)
        if not results:
            return f"No messages found containing any of: {keywords}"
        return f"Found {len(results)} messages containing {keywords}:\n\n" + "\n".join(f"- {msg}" for msg in results)

    elif start_turn is not None or end_turn is not None:
        # Pure turn range search
        if start_turn is None:
            start_turn = -30
        if end_turn is None:
            end_turn = -1

        messages = get_chat_history_range(chat_id, start_turn, end_turn)
        if not messages:
            return f"No messages found in turn range {start_turn} to {end_turn}"
        return f"Messages from turns {start_turn} to {end_turn} ({len(messages)} messages):\n\n" + "\n".join(f"- {msg}" for msg in messages[:max_results])

    elif minutes_ago_start is not None:
        # Pure time search
        minutes_ago_end_val = minutes_ago_end if minutes_ago_end is not None else 0
        messages = get_chat_history_by_time(chat_id, minutes_ago_start, minutes_ago_end_val)

        time_desc = (
            f"last {minutes_ago_start} minutes"
            if minutes_ago_end_val == 0
            else f"{minutes_ago_start}-{minutes_ago_end_val} minutes ago"
        )
        return (
            f"No messages found from {time_desc}"
            if not messages
            else f"Messages from {time_desc} ({len(messages)} messages):\n\n"
            + "\n".join(f"- {msg}" for msg in messages[:max_results])
        )

    else:
        return "Please specify search criteria: keywords, turn range (start_turn/end_turn), or time period (minutes_ago_start/minutes_ago_end)"


# =============================================================================
# END AGENT TOOLS
# =============================================================================

class AgentService:
    """Manages the lifecycle and interactions of the Pydantic-AI Orchestrator Agent.
    
    The orchestrator agent (Dan) has access to custom tools only.
    Expert model access is provided through the get_expert_response tool which creates
    a separate expert agent with MCP servers but no custom tools.
    """

    def __init__(self):
        self.agent: Optional[Agent] = None
        self._is_initialized = False
        self.mcp_servers_config = {}

    async def initialize(self):
        """Initializes the orchestrator agent with custom tools only."""
        if self._is_initialized:
            logger.warning("Agent service already initialized.")
            return

        logger.info("Initializing AgentService...")
        try:
            # Load MCP server configurations for expert model
            try:
                with open('mcp_servers_config.json', 'r') as f:
                    self.mcp_servers_config = json.load(f).get('mcpServers', {})
                logger.info(f"Loaded {len(self.mcp_servers_config)} MCP server configurations from mcp_servers_config.json")
            except FileNotFoundError:
                logger.warning("mcp_servers_config.json not found. No external MCP servers will be loaded for expert model.")
                self.mcp_servers_config = {}
            except json.JSONDecodeError:
                logger.error("Error decoding mcp_servers_config.json. Please check the file format.")
                self.mcp_servers_config = {}

            logfire.configure()

            # Get the orchestrator system prompt
            system_prompt = get_system_prompt(ModelType.ORCHESTRATOR)

            # Orchestrator agent (Dan) - only has custom tools, no MCP servers
            self.agent = Agent(
                ORCHESTRATOR_MODEL_IDENTIFIER,
                deps_type=ChatDeps,
                system_prompt=system_prompt,
                tools=[update_chat_context, reply_to_user, get_expert_response, search_chat_history_tool, list_available_mcp_servers],
                instrument=True
            )

            self._is_initialized = True
            logger.info("AgentService initialized (orchestrator agent with custom tools only).")

        except Exception as e:
            logger.error(f"Failed to initialize AgentService: {e}", exc_info=True)
            await self.shutdown()
            raise

    async def shutdown(self):
        """Cleans up the agent service."""
        if not self._is_initialized:
            logger.warning("Agent service not running or already shut down.")
            return

        logger.info("Shutting down AgentService...")
        try:
            self.agent = None
            self._is_initialized = False
            logger.info("AgentService shut down.")
        except Exception as e:
            logger.error(f"Error shutting down AgentService: {e}", exc_info=True)

    async def process_message(self, chat_id: int, user_input: str, reply_text_func: Callable[[str], Awaitable[Any]], message_timestamp: float) -> str:
        """Processes a user message using the agent."""
        if not self.agent or not self._is_initialized:
            logger.error("Agent service not initialized. Cannot process message.")
            return "Sorry, the agent is not ready. Please try again later."

        current_chat_history = get_chat_history(chat_id)
        current_context = get_chat_context(chat_id)
        deps = ChatDeps(chat_id=chat_id, reply_text=reply_text_func, mcp_servers_config=self.mcp_servers_config)

        try:
            # Get context-aware system prompt
            system_prompt = get_system_prompt(ModelType.ORCHESTRATOR, context=current_context)

            # Ensure context fits within model limits before proceeding
            compressed_context, compressed_history = ensure_context_fits(
                system_prompt=system_prompt,
                context=current_context,
                chat_history=current_chat_history,
                user_input=user_input,
                model_identifier=ORCHESTRATOR_MODEL_IDENTIFIER
            )

            # Update context if it was compressed
            if compressed_context != current_context:
                logger.info(f"Context was compressed for chat_id {chat_id}")
                set_chat_context(chat_id, compressed_context)

            logger.debug(f"Running agent for chat_id {chat_id}...")
            result = await self.agent.run(
                user_input,
                deps=deps,
                message_history=compressed_history
            )
            logger.debug(f"Agent response received for chat_id {chat_id}.")

            new_messages = result.new_messages()
            add_messages_to_history(chat_id, new_messages, message_timestamp)
            logger.debug(f"Added {len(new_messages)} messages to history for chat_id {chat_id}")

            return result.output

        except Exception as e:
            logger.error(f"Error processing message for chat {chat_id}: {e}", exc_info=True)
            return "Sorry, I encountered an error while processing your request."