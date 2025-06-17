"""
Centralized configuration loading for the make-bot application.

This module consolidates all configuration loading from environment variables
and configuration files to eliminate duplication and improve maintainability.
"""

import json
import logging
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables once at module level
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Configuration for the Telegram bot."""
    bot_token: str
    allowed_chat_ids: set[int]


@dataclass
class ModelConfig:
    """Configuration for AI models."""
    orchestrator_model_identifier: str
    expert_model_identifier: str
    orchestrator_context_limit: int
    expert_context_limit: int
    default_context_limit: int


@dataclass
class AppConfig:
    """Main application configuration."""
    bot: BotConfig
    models: ModelConfig
    mcp_servers: dict[str, any]


def _load_telegram_bot_config() -> BotConfig:
    """Load Telegram bot configuration from environment variables."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set.")

    # Parse allowed chat IDs
    allowed_ids_str = os.getenv('ALLOWED_CHAT_IDS', '')
    allowed_chat_ids = set()

    if allowed_ids_str:
        try:
            allowed_chat_ids = set(int(chat_id.strip()) for chat_id in allowed_ids_str.split(','))
            if allowed_chat_ids:
                logger.info(f"Loaded {len(allowed_chat_ids)} allowed chat IDs")
            else:
                logger.warning("ALLOWED_CHAT_IDS is set but empty. No users will be allowed.")
        except ValueError as e:
            logger.error("Invalid format for ALLOWED_CHAT_IDS. Please provide comma-separated integers.")
            raise ValueError(f"Invalid ALLOWED_CHAT_IDS format: {e}")
    else:
        logger.warning("ALLOWED_CHAT_IDS not set. No users will be allowed.")

    return BotConfig(
        bot_token=bot_token,
        allowed_chat_ids=allowed_chat_ids
    )


def _parse_int_env_var(var_name: str, default_value: int) -> int:
    """Parse integer environment variable with default fallback."""
    value_str = os.getenv(var_name)
    if not value_str:
        return default_value

    try:
        return int(value_str)
    except ValueError as e:
        logger.warning(f"Invalid integer value for {var_name}: '{value_str}', using default: {default_value}")
        return default_value


def _load_model_config() -> ModelConfig:
    """Load AI model configuration from environment variables."""
    orchestrator_model = os.getenv('ORCHESTRATOR_MODEL_IDENTIFIER')
    expert_model = os.getenv('EXPERT_MODEL_IDENTIFIER')

    if not orchestrator_model or not expert_model:
        raise ValueError(
            "Model identifiers must be set in environment variables: "
            "ORCHESTRATOR_MODEL_IDENTIFIER and EXPERT_MODEL_IDENTIFIER"
        )

    # Load context limits with sensible defaults
    orchestrator_context_limit = _parse_int_env_var('ORCHESTRATOR_CONTEXT_LIMIT', 128000)
    expert_context_limit = _parse_int_env_var('EXPERT_CONTEXT_LIMIT', 200000)
    default_context_limit = _parse_int_env_var('DEFAULT_CONTEXT_LIMIT', 8192)

    logger.info(f"Loaded model config: orchestrator={orchestrator_model} (limit: {orchestrator_context_limit}), "
                f"expert={expert_model} (limit: {expert_context_limit})")

    return ModelConfig(
        orchestrator_model_identifier=orchestrator_model,
        expert_model_identifier=expert_model,
        orchestrator_context_limit=orchestrator_context_limit,
        expert_context_limit=expert_context_limit,
        default_context_limit=default_context_limit
    )


def _load_mcp_servers_config() -> dict[str, any]:
    """Load MCP server configurations from JSON file."""
    config_file = Path('mcp_servers_config.json')

    try:
        if not config_file.exists():
            logger.warning("mcp_servers_config.json not found. No MCP servers will be available.")
            return {}

        with open(config_file, 'r') as f:
            config_data = json.load(f)

        mcp_servers = config_data.get('mcpServers', {})
        logger.info(f"Loaded {len(mcp_servers)} MCP server configurations")

        return mcp_servers

    except json.JSONDecodeError as e:
        logger.error(f"Error decoding mcp_servers_config.json: {e}")
        raise ValueError(f"Invalid JSON in mcp_servers_config.json: {e}")
    except Exception as e:
        logger.error(f"Error loading MCP server config: {e}")
        raise


def load_application_config() -> AppConfig:
    """Load all application configuration.

    Returns:
        AppConfig instance with all loaded configuration

    Raises:
        ValueError: If required configuration is missing or invalid
    """
    try:
        bot_config = _load_telegram_bot_config()
        model_config = _load_model_config()
        mcp_servers_config = _load_mcp_servers_config()

        logger.info("Application configuration loaded successfully")

        return AppConfig(
            bot=bot_config,
            models=model_config,
            mcp_servers=mcp_servers_config
        )

    except Exception as e:
        logger.error(f"Failed to load application configuration: {e}")
        raise


# Global configuration instance - loaded once at module import
try:
    CONFIG = load_application_config()
except Exception as e:
    logger.error(f"Failed to initialize application configuration: {e}")
    raise