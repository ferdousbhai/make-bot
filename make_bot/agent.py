import logging
from typing import Callable, Any, Awaitable
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPServerStdio
from telegram.constants import ParseMode
import telegramify_markdown

from .chat_history import (
    get_chat_history, add_turn_to_history, get_chat_context, set_chat_context,
    search_chat_history_keywords, get_chat_history_range, get_chat_history_by_time
)
from .context_manager import create_context_compression_processor
from .prompt_loader import get_system_prompt, ModelType
from .config import CONFIG

logger = logging.getLogger(__name__)


@dataclass
class ChatDeps:
    chat_id: int
    reply_text: Callable[[str], Awaitable[Any]]
    mcp_servers_config: dict[str, Any]


# =============================================================================
# AGENT TOOLS - All tools available to the AI model (excluding MCP servers)
# =============================================================================

async def reply_to_user(ctx: RunContext[ChatDeps], message: str):
    """Send a message to the user via Telegram.
    Use this tool to send responses directly to the user in markdown format.
    """
    try:
        # Convert raw markdown to Telegram's MarkdownV2 format
        formatted_message = telegramify_markdown.markdownify(message)
        await ctx.deps.reply_text(formatted_message, parse_mode=ParseMode.MARKDOWN_V2)
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

async def get_expert_response(ctx: RunContext[ChatDeps], query: str, context: str = "", mcp_servers: list[str] = None):
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
        mcp_servers: List of MCP server names to provide to the expert. Available servers: {available_servers}
            If None or empty list, expert will work without external tools.

    Examples:
        - For data analysis: mcp_servers=["run-python"]
        - For investment questions: mcp_servers=["investor"]
        - For current events: mcp_servers=["brave-search"]
        - For complex research: mcp_servers=["brave-search", "run-python"]
        - For pure reasoning: mcp_servers=[] or mcp_servers=None
    """.format(available_servers=", ".join(ctx.deps.mcp_servers_config.keys()) if ctx.deps.mcp_servers_config else "None configured")

    logger.info(f"Consulting expert model for chat_id {ctx.deps.chat_id}: {query}...")

    try:
        expert_prompt = get_system_prompt(ModelType.EXPERT, context=context)

        # Setup MCP servers if requested
        selected_mcp_servers = []
        if mcp_servers:
            available_servers = ctx.deps.mcp_servers_config
            for server_name in mcp_servers:
                config = available_servers.get(server_name, {})
                if config.get('command'):
                    selected_mcp_servers.append(
                        MCPServerStdio(config['command'], args=config.get('args', []), env=config.get('env'))
                    )
                    logger.info(f"Adding MCP server '{server_name}' to expert agent")
                else:
                    logger.warning(f"Requested MCP server '{server_name}' not found or not configured")

        logger.info(f"Expert agent will use {len(selected_mcp_servers)} MCP servers: {mcp_servers or []}")

        # Create expert agent (with or without MCP servers)
        agent_kwargs = {
            'model': CONFIG.models.expert_model_identifier,
            'system_prompt': expert_prompt
        }
        if selected_mcp_servers:
            agent_kwargs['mcp_servers'] = selected_mcp_servers

        # Add history processor for expert agent too
        expert_history_processor = create_context_compression_processor(
            model_identifier=CONFIG.models.expert_model_identifier,
            system_prompt=expert_prompt
        )
        agent_kwargs['history_processors'] = [expert_history_processor]

        expert_agent = Agent(**agent_kwargs)

        # Run expert agent (no manual compression needed - handled by history processor)
        if selected_mcp_servers:
            async with expert_agent.run_mcp_servers():
                result = await expert_agent.run(query)
        else:
            result = await expert_agent.run(query)

        logger.info(f"Expert consultation completed for chat_id {ctx.deps.chat_id}")
        return f"Expert Response:\n\n{result.output}"

    except Exception as e:
        logger.error(f"Error consulting expert model: {e}", exc_info=True)
        return f"Expert consultation failed: {str(e)}"


def search_chat_history_tool(
    ctx: RunContext[ChatDeps],
    keywords: list[str] = None,
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
    has_keywords = keywords and len(keywords) > 0
    has_turn_range = start_turn is not None or end_turn is not None
    has_time_range = minutes_ago_start is not None

    # Helper function to filter messages by keywords
    def filter_messages_by_keywords(messages, keyword_list, max_results):
        if not keyword_list:
            return messages[:max_results]
        keywords_lower = [kw.lower() for kw in keyword_list]
        matches = []
        for msg in messages:
            if any(kw in str(msg).lower() for kw in keywords_lower) and len(matches) < max_results:
                matches.append(str(msg))
        return matches

    # Helper function to format results
    def format_search_results(messages, search_description, keyword_list=None):
        if not messages:
            keyword_part = f" containing {keyword_list}" if keyword_list else ""
            return f"No messages found{keyword_part} {search_description}"
        keyword_part = f" containing {keyword_list}" if keyword_list else ""
        return f"Found {len(messages)} messages{keyword_part} {search_description}:\n\n" + "\n".join(f"- {msg}" for msg in messages)

    # No search criteria provided
    if not (has_keywords or has_turn_range or has_time_range):
        return "Please specify search criteria: keywords, turn range (start_turn/end_turn), or time period (minutes_ago_start/minutes_ago_end)"

    # Get base messages based on range type
    if has_turn_range:
        start_turn = start_turn or -30
        end_turn = end_turn or -1
        messages = get_chat_history_range(chat_id, start_turn, end_turn)
        search_description = f"in turns {start_turn} to {end_turn}"
    elif has_time_range:
        minutes_ago_end_val = minutes_ago_end or 0
        messages = get_chat_history_by_time(chat_id, minutes_ago_start, minutes_ago_end_val)
        search_description = f"from last {minutes_ago_start} minutes" if minutes_ago_end_val == 0 else f"from {minutes_ago_start}-{minutes_ago_end_val} minutes ago"
    else:
        # Pure keyword search
        results = search_chat_history_keywords(chat_id, keywords, max_results)
        return format_search_results(results, "", keywords)

    # Apply keyword filter if needed and format results
    filtered_messages = filter_messages_by_keywords(messages, keywords if has_keywords else None, max_results)
    return format_search_results(filtered_messages, search_description, keywords if has_keywords else None)


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
        self.agent: Agent | None = None
        self._is_initialized = False

    async def initialize(self):
        """Initializes the orchestrator agent with custom tools only."""
        if self._is_initialized:
            logger.warning("Agent service already initialized.")
            return

        logger.info("Initializing AgentService...")
        try:
            # Get available MCP server names
            available_mcp_servers = list(CONFIG.mcp_servers.keys()) if CONFIG.mcp_servers else []
            mcp_servers_str = ", ".join(available_mcp_servers) if available_mcp_servers else "None configured"

            # Create orchestrator agent with custom tools only
            system_prompt = get_system_prompt(ModelType.ORCHESTRATOR, available_mcp_servers=mcp_servers_str)
            custom_tools = [update_chat_context, reply_to_user, get_expert_response, search_chat_history_tool]

            # Create history processor for automatic compression
            history_compression_processor = create_context_compression_processor(
                model_identifier=CONFIG.models.orchestrator_model_identifier,
                system_prompt=system_prompt
            )

            self.agent = Agent(
                CONFIG.models.orchestrator_model_identifier,
                deps_type=ChatDeps,
                system_prompt=system_prompt,
                tools=custom_tools,
                history_processors=[history_compression_processor],
                instrument=True
            )

            self._is_initialized = True
            tool_names = [tool.__name__ for tool in custom_tools]
            logger.info(f"Orchestrator agent initialize dwith custom tools: {', '.join(tool_names)}")

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
        deps = ChatDeps(chat_id=chat_id, reply_text=reply_text_func, mcp_servers_config=CONFIG.mcp_servers)

        try:
            # Get available MCP server names for context-aware system prompt
            available_mcp_servers = list(CONFIG.mcp_servers.keys()) if CONFIG.mcp_servers else []
            mcp_servers_str = ", ".join(available_mcp_servers) if available_mcp_servers else "None configured"

            # Get context-aware system prompt
            system_prompt = get_system_prompt(ModelType.ORCHESTRATOR, context=current_context, available_mcp_servers=mcp_servers_str)

            logger.debug(f"Running agent for chat_id {chat_id}...")
            result = await self.agent.run(
                user_input,
                deps=deps,
                message_history=current_chat_history
            )
            logger.debug(f"Agent response received for chat_id {chat_id}.")

            new_messages = result.new_messages()
            add_turn_to_history(chat_id, new_messages, message_timestamp)
            logger.debug(f"Added {len(new_messages)} messages to history for chat_id {chat_id}")

            return result.output

        except Exception as e:
            logger.error(f"Error processing message for chat {chat_id}: {e}", exc_info=True)
            return "Sorry, I encountered an error while processing your request."