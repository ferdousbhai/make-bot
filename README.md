# Make-Bot: Railway-Ready Telegram Bot Template with Pydantic AI

A production-ready Telegram bot template with PostgreSQL context management, designed for easy deployment on Railway with uv for project management.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/fr56p3?referralCode=JIh7xZ)



## Features

- 🤖 **AI-Powered Conversations** - Using pydantic-ai
- 💾 **PostgreSQL + SQLModel Storage** - Persistent chat history with advanced search capabilities
- 🔍 **Rich Context Management** - Search by keywords, time ranges, and turn-based filtering
- 🚀 **Railway Ready** - Optimized for Railway deployment with managed PostgreSQL
- 📦 **Modern Python** - Uses `uv` for fast dependency management and `pyproject.toml`
- 🔐 **Authorization** - Chat ID-based access control



## Quick Start

### Prerequisites

- Railway account
- Telegram bot token from [@BotFather](https://t.me/botfather)
- AI model API keys (supports any model using pydantic-ai)



## Railway Deployment

1. Click the "Deploy on Railway" button above
2. Configure required environment variables:
   - `TELEGRAM_BOT_TOKEN` - Your bot token from BotFather
   - `MODEL_IDENTIFIER` - AI model (e.g., `anthropic:claude-sonnet-4-20250514`)
   - API key for your chosen provider (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, etc.)
   - `ALLOWED_CHAT_IDS` - (optional) Comma-separated chat IDs for access control
   - `LOGFIRE_TOKEN` - (optional) For monitoring
3. Deploy!



## Local Development

### 1. Install Railway CLI

```bash
# macOS/Linux
curl -fsSL https://railway.app/install.sh | sh
```

### 2. Setup Project

```bash
# Clone and setup
git clone <your-repo-url>
cd make-bot

# Login to Railway
railway login

railway link -p <your-project-id>

```

### 3. Deploy Changes

```bash
railway up
```



## Available Tools

### 1. `get_chat_history` Tool

Context management with advanced search capabilities:

**Parameters:**
- `turns: str = "-5:"` - Python slice syntax for selecting conversation turns
- `query: list[str] | None = None` - **List of search terms** to filter messages containing any of these terms
- `days: int | None = 30` - Number of days to look back (None for all messages)

**Example Usage:**
```python
# Get last 5 turns (default)
get_chat_history()

# Get last 3 turns
get_chat_history(turns="-3:")

# Get turns 5-10
get_chat_history(turns="5:10")

# Search for pet-related conversations
get_chat_history(query=["cat", "dog", "pets", "animals"])

# Get recent 3 turns with weather mentions
get_chat_history(turns="-3:", query=["weather", "temperature", "rain"])

# Time-based search with keywords (last 7 days)
get_chat_history(
    query=["meeting", "schedule"],
    days=7
)
```

### 2. `reply_to_user` Tool

Handles all communication back to the user through Telegram:

**Features:**
- **Markdown Support** - Automatically formats messages using Telegram's MarkdownV2
- **Message Tracking** - Stores all assistant replies for context management

**Usage:**
- The agent automatically uses this tool to send responses
- Supports rich text formatting, links, and Telegram-specific features

## Project Structure

```
make-bot/
├── main.py                 # Thin wrapper entry point
├── app/                    # Application modules
│   ├── __init__.py
│   ├── auth.py            # Authorization decorator and logic
│   ├── bot.py             # Main bot setup and handlers
│   ├── models.py          # Data models (ConversationTurn, ChatDeps)
│   └── tools.py           # AI agent tools (reply_to_user, get_chat_history)
├── railway.json           # Railway deployment config
├── pyproject.toml         # Dependencies and project config
├── README.md
└── .gitignore
```

### Database Schema

The PostgreSQL client uses SQLModel and automatically creates the following table:

```python
class ConversationTurn(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(index=True)
    user_message: str
    assistant_replies: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now, index=True)
```



## License

[MIT](LICENSE)



## Support

- 📚 [Railway Documentation](https://docs.railway.app/)
- 🔧 [uv Documentation](https://docs.astral.sh/uv/)
- 🤖 [python-telegram-bot Guide](https://docs.python-telegram-bot.org/)
- 🧠 [PydanticAI Documentation](https://ai.pydantic.dev/)
