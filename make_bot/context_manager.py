import logging
import tiktoken
from typing import List, Tuple
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

def analyze_context_usage(system_prompt: str, context: str, chat_history: List, user_input: str, model_identifier: str) -> ContextInfo:
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

def _compress_by_truncation(history_items: List, target_reduction: int, min_keep: int = 2) -> List:
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

def _compress_text_smartly(text: str, max_tokens: int) -> str:
    """Compress text with smart truncation at sentence boundaries."""
    if not text or count_tokens(text) <= max_tokens:
        return text

    target_ratio = max_tokens / count_tokens(text)
    target_length = int(len(text) * target_ratio)

    # Try sentence-boundary truncation
    sentences = text.split('. ')
    if len(sentences) > 1:
        compressed = ""
        for sentence in reversed(sentences):
            test_text = sentence + ". " + compressed
            if count_tokens(test_text) <= max_tokens:
                compressed = test_text
            else:
                break
        if compressed:
            return compressed.strip()

    # Fallback to simple truncation
    compressed = text[:target_length]
    logger.warning(f"Text truncated from {len(text)} to {len(compressed)} characters")
    return compressed

def ensure_context_fits(system_prompt: str, context: str, chat_history: List, user_input: str, model_identifier: str) -> Tuple[str, List]:
    """Ensure context fits within model limits by compressing as needed."""
    info = analyze_context_usage(system_prompt, context, chat_history, user_input, model_identifier)

    if not info.needs_compression:
        logger.debug(f"Context fits for {model_identifier}: {info.total_tokens}/{info.limit} tokens")
        return context, chat_history

    logger.warning(f"Context limit exceeded for {model_identifier}: {info.total_tokens}/{info.limit} tokens, compressing...")

    tokens_to_remove = abs(info.remaining)
    compressed_context = context
    compressed_history = chat_history

    # Compress history first (less important for immediate context)
    history_tokens = count_tokens("\n".join(str(msg) for msg in chat_history))
    if history_tokens > 0 and tokens_to_remove > 0:
        history_reduction = min(tokens_to_remove, history_tokens // 2)
        compressed_history = _compress_by_truncation(chat_history, history_reduction)

        tokens_removed = history_tokens - count_tokens("\n".join(str(msg) for msg in compressed_history))
        tokens_to_remove -= tokens_removed
        logger.info(f"Compressed history for {model_identifier}: removed {tokens_removed} tokens")

    # Compress context if still needed
    if tokens_to_remove > 0 and context:
        context_tokens = count_tokens(context)
        target_tokens = max(context_tokens - tokens_to_remove, context_tokens // 4)
        compressed_context = _compress_text_smartly(context, target_tokens)

        tokens_removed = context_tokens - count_tokens(compressed_context)
        logger.info(f"Compressed context for {model_identifier}: removed {tokens_removed} tokens")

    # Verify final result
    final_info = analyze_context_usage(system_prompt, compressed_context, compressed_history, user_input, model_identifier)
    if final_info.needs_compression:
        logger.error(f"Still over limit after compression for {model_identifier}: {final_info.total_tokens}/{final_info.limit}")
    else:
        logger.info(f"Successfully compressed for {model_identifier}: {final_info.total_tokens}/{final_info.limit} tokens")

    return compressed_context, compressed_history