# Make Bot

This project implements a Telegram bot powered by a Pydantic-AI agent.

## Setup

1. **Create a `.env` file:** Set up your environment variables with the following required and optional values:

   **Required:**
   - `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
   - `ALLOWED_CHAT_IDS` - Comma-separated list of chat IDs allowed to use the bot
   - `ORCHESTRATOR_MODEL_IDENTIFIER` - Model identifier for the orchestrator agent (e.g., `openai:gpt-4o-mini`)
   - `EXPERT_MODEL_IDENTIFIER` - Model identifier for the expert agent (e.g., `anthropic:claude-sonnet-4-latest`)

   **Optional (with defaults):**
   - `ORCHESTRATOR_CONTEXT_LIMIT` - Context limit for orchestrator model (default: 128000)
   - `EXPERT_CONTEXT_LIMIT` - Context limit for expert model (default: 200000)
   - `DEFAULT_CONTEXT_LIMIT` - Default context limit for unknown models (default: 8192)

2. **(Optional) Configure MCP Servers:** Create or modify `mcp_servers_config.json` to define any external Multi-Channel Providers (MCPs) you want the agent to use.

## Running the Bot

To run the bot, use the following command:

```bash
uv run bot
```
