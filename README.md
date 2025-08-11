# Make-Bot: Railway-Ready Telegram Bot Template with Pydantic AI

A production-ready Telegram bot template with PostgreSQL context management, designed for easy deployment on Railway with uv for project management.

## Features

- 🤖 **AI-Powered Conversations** - Using pydantic-ai
- 💾 **PostgreSQL Storage** - Persistent chat history with advanced search capabilities
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
2. Railway automatically provides `DATABASE_URL` environment variable
3. Connect our service from step 1 to the database by `DATABASE_URL` environment variable in our service where the value is set to `${{ Postgres.DATABASE_URL }}`

### 3. Configure Environment Variables

Add the following environment variables in Railway dashboard for our service:

**Required:**
- `TELEGRAM_BOT_TOKEN` - Your bot token from BotFather
- `MODEL_IDENTIFIER` - AI model provider name and model name separated by colon (e.g., `anthropic:claude-sonnet-4-20250514`)
- `ALLOWED_CHAT_IDS` - Comma-separated chat IDs (e.g., `123456789,987654321`)
- `LOGFIRE_WRITE_TOKEN` - For monitoring and logging AI model inference

**AI Model API Keys** (choose based on your model):
- `ANTHROPIC_API_KEY` - Your Anthropic API key (if using Claude)
- ALternatively, use `OPENAI_API_KEY` for OpenAI model, `GOOGLE_API_KEY` for Google model etc (see pydantic-ai documentation for more info)


### 4. Deploy

Railway automatically deploys when you push to your connected branch.

## Core Features

### Chat History Management

The bot provides sophisticated context management capabilities through an internal `get_chat_history` tool:

- **Recent Message Retrieval** - Access the most recent conversation history
- **Keyword Search** - Find messages containing specific terms or phrases
- **Time-based Filtering** - Retrieve messages from specific time periods
- **Turn-based Navigation** - Access conversation history by turn ranges (supports negative indexing)
- **Role Filtering** - Filter messages by role (user/assistant)
- **Combined Filtering** - Use multiple filters together for precise context retrieval

### Reply to user

The agent uses `reply_to_user` tool to respond to user via the telegram app.

## Project Structure

```
make-bot/
├── app/
│   ├── __init__.py
│   ├── agent.py            # AI agent service and tools
│   ├── data_client.py      # PostgreSQL data client
├── run.py                  # Main bot runner
├── railway.json            # Railway deployment config
├── pyproject.toml          # Dependencies and project config
├── README.md               # This file
└── .gitignore
```

### Database Schema

The PostgreSQL client uses SQLModel and automatically creates the following table:

```python
class ChatHistory(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(index=True)
    role: str = Field(max_length=20)
    content: str
    timestamp: datetime = Field(default_factory=datetime.now, index=True)
```


**Features:**
- **Type Safety**: SQLModel provides full type safety with Pydantic validation
- **Auto-migration**: Tables and indexes are created automatically on startup
- **Full-text Search**: PostgreSQL GIN index for efficient content searching

```


## License

MIT

## Support

- 📚 [Railway Documentation](https://docs.railway.app/)
- 🔧 [uv Documentation](https://docs.astral.sh/uv/)
- 🤖 [python-telegram-bot Guide](https://docs.python-telegram-bot.org/)
- 🧠 [PydanticAI Documentation](https://ai.pydantic.dev/)

---

**Ready to deploy your Telegram bot?** Click the button below to deploy to Railway:

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/make-bot)