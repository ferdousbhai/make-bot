import logging
import tiktoken
from dataclasses import dataclass

from .config import CONFIG

logger = logging.getLogger(__name__)

@dataclass
class ContextInfo:
    """Information about context usage."""
    total_tokens: int
    limit: int
    remaining: int
    needs_compression: bool

def get_model_context_limit(model_identifier: str) -> int:
    """Get the context limit for a specific model identifier.

    Args:
        model_identifier: The model identifier string

    Returns:
        Context limit for the model
    """
    if model_identifier == CONFIG.models.orchestrator_model_identifier:
        return CONFIG.models.orchestrator_context_limit
    elif model_identifier == CONFIG.models.expert_model_identifier:
        return CONFIG.models.expert_context_limit
    else:
        logger.warning(f"Unknown model identifier '{model_identifier}', using default context limit")
        return CONFIG.models.default_context_limit

def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken with fallback."""
    try:
        encoding = tiktoken.encoding_for_model("gpt-4")
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Error counting tokens: {e}, using character estimate")
        return len(text) // 4  # Rough estimate

def analyze_context_usage(system_prompt: str, context: str, chat_history: list, user_input: str, model_identifier: str) -> ContextInfo:
    """Analyze context usage and determine if compression is needed."""
    components = {
        'system': system_prompt,
        'context': context or "",
        'user': user_input,
        'history': "\n".join(str(msg) for msg in chat_history)
    }

    # Calculate tokens for all components
    token_counts = {name: count_tokens(text) for name, text in components.items()}
    total_tokens = sum(token_counts.values())

    limit = get_model_context_limit(model_identifier)
    remaining = limit - total_tokens

    logger.debug(f"Context analysis for {model_identifier} - {', '.join(f'{k}: {v}' for k, v in token_counts.items())}, Total: {total_tokens}/{limit}")

    return ContextInfo(
        total_tokens=total_tokens,
        limit=limit,
        remaining=remaining,
        needs_compression=remaining < 0
    )

def _compress_by_truncation(history_items: list, target_reduction: int, min_keep: int = 2) -> list:
    """Generic compression by removing oldest items."""
    if not history_items or len(history_items) <= min_keep:
        return history_items

    compressed = history_items.copy()

    while compressed and len(compressed) > min_keep:
        current_tokens = count_tokens("\n".join(str(item) for item in compressed))
        if current_tokens <= target_reduction:
            break

        removed = compressed.pop(0)
        logger.debug(f"Removed item: {str(removed)[:50]}...")

    return compressed

def create_context_compression_processor(model_identifier: str, system_prompt: str = "", context: str = "", user_input: str = ""):
    """Create a history processor that automatically compresses context when needed.

    This is designed to be used with pydantic-ai's built-in history_processors feature.

    Args:
        model_identifier: The model identifier to get context limits for
        system_prompt: System prompt to account for in token counting
        context: Additional context to account for in token counting
        user_input: User input to account for in token counting

    Returns:
        A history processor function that compresses messages when context limit is exceeded
    """
    async def compress_history_for_context(messages: list) -> list:
        """Compress message history to fit within context limits."""
        # Quick check - if no messages, return as-is
        if not messages:
            return messages

        # Analyze if compression is needed
        info = analyze_context_usage(system_prompt, context, messages, user_input, model_identifier)

        if not info.needs_compression:
            logger.debug(f"Context fits for {model_identifier}: {info.total_tokens}/{info.limit} tokens")
            return messages

        logger.warning(f"Context limit exceeded for {model_identifier}: {info.total_tokens}/{info.limit} tokens, compressing...")

        # Calculate how many tokens we need to remove
        tokens_to_remove = abs(info.remaining)

        # Use existing compression logic
        compressed_messages = _compress_by_truncation(messages, tokens_to_remove)

        # Log the compression
        tokens_removed = count_tokens("\n".join(str(msg) for msg in messages)) - count_tokens("\n".join(str(msg) for msg in compressed_messages))
        logger.info(f"Compressed history for {model_identifier}: removed {tokens_removed} tokens, {len(messages)} -> {len(compressed_messages)} messages")

        return compressed_messages

    return compress_history_for_context