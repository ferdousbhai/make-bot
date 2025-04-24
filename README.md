# Make Bot

This project implements a Telegram bot powered by a Pydantic-AI agent.

## Setup

1. **Create a `.env` file:** Copy `.env.example` to `.env` and fill in your `TELEGRAM_BOT_TOKEN`, `ALLOWED_CHAT_IDS`, and any other necessary environment variables (like API keys for models).
2. **(Optional) Configure MCP Servers:** Create or modify `mcp_servers_config.json` to define any external Multi-Channel Providers (MCPs) you want the agent to use.

## Running the Bot

To run the bot, use the following command:

```bash
uv run bot
```
