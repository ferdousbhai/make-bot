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

### 1. Connect Repository

1. Visit [Railway](https://railway.app)
2. Create new project → Deploy from GitHub repo
3. Select your forked repository

### 2. Add PostgreSQL Database

1. In Railway dashboard → Add Service → Database → PostgreSQL
2. Railway automatically provides `DATABASE_URL` environment variable (used by SQLModel)
3. Connect your bot service to the database by setting `DATABASE_URL` environment variable to `${{ Postgres.DATABASE_URL }}`

### 3. Configure Environment Variables

Add the following environment variables in Railway dashboard for your bot service:

- `TELEGRAM_BOT_TOKEN` - Your bot token from BotFather
- `MODEL_IDENTIFIER` - AI model provider name and model name separated by colon (e.g., `anthropic:claude-sonnet-4-20250514`)
- `ANTHROPIC_API_KEY` - (Optional) Your Anthropic API key (if using Claude). Alternatively, use `OPENAI_API_KEY` for OpenAI model, `GOOGLE_API_KEY` for Google model etc (see pydantic-ai documentation for other models).
- `ALLOWED_CHAT_IDS` - (Optional) Comma-separated chat IDs (e.g., `123456789,987654321`). If not set, allows all users.
- `LOGFIRE_TOKEN` - (Optional) For monitoring and logging AI model inference (get this from your Logfire project settings → Write tokens)


### 4. Deploy

Railway automatically deploys when you push to your connected branch.

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

# Link to your Railway project
railway link -p <your-project-id>

```

### 3. Deploy Changes

```bash
# Deploy directly via CLI
railway up

## Available Tools

### 1. `get_chat_history` Tool

Context management with advanced search capabilities:

**Parameters:**
- `limit: int = 10` - Maximum number of conversation turns to return
- `query: list[str] | None = None` - **List of search terms** to filter messages containing any of these terms
- `days: int | None = 30` - Number of days to look back (None for all messages)
- `start_turn: int | None = None` - Starting turn index (supports negative indexing)
- `end_turn: int | None = None` - Ending turn index (supports negative indexing)

**Key Features:**
- **Multi-term Search** - Search for multiple keywords at once (e.g., `["cat", "dog", "pets"]`)
- **Full-text Search** - Uses PostgreSQL's advanced text search on both user messages and assistant replies
- **Flexible Filtering** - Combine time-based, turn-based, and keyword filters
- **Smart Indexing** - Supports negative indexing for recent conversations

**Example Usage:**
```python
# Search for pet-related conversations
get_chat_history(query=["cat", "dog", "pets", "animals"])

# Get recent 5 turns with weather mentions
get_chat_history(limit=5, query=["weather", "temperature", "rain"])

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
- **Error Handling** - Graceful handling of message delivery issues

**Usage:**
- The agent automatically uses this tool to send responses
- Supports rich text formatting, links, and Telegram-specific features

## Project Structure

```
make-bot/
├── run.py                  # Main entry point and bot setup
├── app/                    # Application modules
│   ├── __init__.py
│   ├── auth.py            # Authorization decorator and logic
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


**Features:**
- **Type Safety**: SQLModel provides full type safety with Pydantic validation
- **Auto-migration**: Tables and indexes are created automatically on startup
- **Full-text Search**: PostgreSQL text search vectors for efficient content searching

```


## License

[MIT](LICENSE)

## Support

- 📚 [Railway Documentation](https://docs.railway.app/)
- 🔧 [uv Documentation](https://docs.astral.sh/uv/)
- 🤖 [python-telegram-bot Guide](https://docs.python-telegram-bot.org/)
- 🧠 [PydanticAI Documentation](https://ai.pydantic.dev/)

---

## Template Deployment

This project is configured as a Railway template for one-click deployment.

### Deploy Your Own Bot

1. **Fork this repository** to your GitHub account
2. **Deploy to Railway** using the template:
   - Visit [Railway](https://railway.app)
   - Create new project → Deploy from GitHub repo
   - Select your forked repository
   - Railway will automatically set up PostgreSQL and configure the bot