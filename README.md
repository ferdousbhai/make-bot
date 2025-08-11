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

### 3. Configure Environment Variables

Add the following environment variables in Railway dashboard:

**Required:**
- `TELEGRAM_BOT_TOKEN` - Your bot token from BotFather
- `MODEL_IDENTIFIER` - AI model (e.g., `anthropic:claude-sonnet-4-20250514`)
- `ALLOWED_CHAT_IDS` - Comma-separated chat IDs (e.g., `123456789,987654321`)

**AI Model API Keys** (choose based on your model):
- `ANTHROPIC_API_KEY` - Your Anthropic API key (if using Claude)
- `GOOGLE_GENERATIVE_AI_API_KEY` - Your Google AI API key (if using Gemini)

**Optional:**
- `LOGFIRE_WRITE_TOKEN` - For monitoring and logging

**Note:** Railway automatically provides `DATABASE_URL` when you add the PostgreSQL service.


### 4. Deploy

Railway automatically deploys when you push to your connected branch.

## Core Features

### Chat History Management

The bot provides sophisticated context management through a single `get_chat_history` tool:

```python
# Get recent messages
await get_chat_history(limit=20)

# Search by keyword
await get_chat_history(query="python", limit=10)

# Time-based filtering
await get_chat_history(after_time="2024-01-01T00:00:00Z")

# Turn-based ranges (negative indexing supported)
await get_chat_history(start_turn=-10, end_turn=-1)

# Role filtering
await get_chat_history(role_filter="user", limit=5)

# Combined filtering
await get_chat_history(query="API", start_turn=-20, limit=5)
```

## Project Structure

```
make-bot/
├── app/
│   ├── __init__.py
│   ├── agent.py            # AI agent service and tools
│   ├── data_client.py      # PostgreSQL data client
├── run.py                  # Main bot runner
├── Dockerfile              # Container configuration
├── railway.json            # Railway deployment config
├── pyproject.toml          # Dependencies and project config
├── README.md               # This file
└── .gitignore
```

### Database Schema

The PostgreSQL client automatically creates these tables:

```sql
-- Chat messages with full-text search
CREATE TABLE chat_history (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for better query performance
CREATE INDEX idx_chat_history_chat_id ON chat_history(chat_id);
CREATE INDEX idx_chat_history_timestamp ON chat_history(timestamp);
CREATE INDEX idx_chat_history_content_search ON chat_history USING gin(to_tsvector('english', content));
```

## Development

### Adding New Tools

1. Add async function with `@agent.tool` decorator in `app/agent.py`
2. The tool will automatically be available to the agent
3. Test locally before deployment

### Extending Data Client

The PostgreSQL client in `app/data_client.py` uses:
- SQLAlchemy with async engine (asyncpg driver)
- SQLModel for type-safe database models
- Persistent chat history storage (all messages retained)
- Full-text search with PostgreSQL GIN indexes


### Logs and Monitoring

```bash
# Railway logs
railway logs

```


## License

MIT License - see LICENSE file for details.

## Support

- 📚 [Railway Documentation](https://docs.railway.app/)
- 🔧 [uv Documentation](https://docs.astral.sh/uv/)
- 🤖 [python-telegram-bot Guide](https://docs.python-telegram-bot.org/)
- 🧠 [PydanticAI Documentation](https://ai.pydantic.dev/)

---

**Ready to deploy your Telegram bot?** Click the button below to deploy to Railway:

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/make-bot)