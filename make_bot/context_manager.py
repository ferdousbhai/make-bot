import logging
import tiktoken
from typing import List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Model context limits (conservative estimates)
MODEL_LIMITS = {
    'groq:llama-3.1-8b-instant': 8192,
    'anthropic:claude-sonnet-4-latest': 200000,
    'openai:gpt-4o': 128000,
    'openai:gpt-4o-mini': 128000,
}

# Default limits for unknown models
DEFAULT_CONTEXT_LIMIT = 8192
SAFETY_MARGIN = 1000  # Reserve tokens for response

@dataclass
class ContextInfo:
    """Information about context usage."""
    total_tokens: int
    limit: int
    remaining: int
    needs_compression: bool

def get_model_limit(model_identifier: str) -> int:
    """Get context limit for a specific model."""
    return MODEL_LIMITS.get(model_identifier, DEFAULT_CONTEXT_LIMIT)

def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in text using tiktoken."""
    try:
        # Use gpt-4 encoding as a reasonable default for most models
        encoding = tiktoken.encoding_for_model("gpt-4")
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Error counting tokens: {e}, using character estimate")
        # Fallback: rough estimate (4 chars per token on average)
        return len(text) // 4

def analyze_context_usage(
    system_prompt: str,
    context: str,
    chat_history: List,
    user_input: str,
    model_identifier: str
) -> ContextInfo:
    """Analyze total context usage and determine if compression is needed."""
    
    # Count tokens for each component
    system_tokens = count_tokens(system_prompt)
    context_tokens = count_tokens(context) if context else 0
    user_tokens = count_tokens(user_input)
    
    # Count chat history tokens
    history_text = "\n".join(str(msg) for msg in chat_history)
    history_tokens = count_tokens(history_text)
    
    total_tokens = system_tokens + context_tokens + history_tokens + user_tokens
    limit = get_model_limit(model_identifier)
    available = limit - SAFETY_MARGIN
    remaining = available - total_tokens
    
    logger.debug(f"Context analysis - System: {system_tokens}, Context: {context_tokens}, "
                f"History: {history_tokens}, User: {user_tokens}, Total: {total_tokens}/{available}")
    
    return ContextInfo(
        total_tokens=total_tokens,
        limit=available,
        remaining=remaining,
        needs_compression=remaining < 0
    )

def compress_chat_history(chat_history: List, target_reduction: int, context: str = "") -> List:
    """Compress chat history to reduce token count while preserving important context."""
    if not chat_history:
        return chat_history
    
    # Strategy 1: Remove oldest messages first, but keep recent ones
    compressed_history = chat_history.copy()
    
    while compressed_history and target_reduction > 0:
        # Calculate current tokens
        current_text = "\n".join(str(msg) for msg in compressed_history)
        current_tokens = count_tokens(current_text)
        
        if current_tokens <= target_reduction:
            break
            
        # Remove oldest message
        if len(compressed_history) > 2:  # Always keep at least 2 recent messages
            removed_msg = compressed_history.pop(0)
            logger.debug(f"Removed message from history: {str(removed_msg)[:50]}...")
        else:
            break
    
    return compressed_history

def compress_context(context: str, max_tokens: int) -> str:
    """Compress context string to fit within token limit."""
    if not context:
        return context
    
    current_tokens = count_tokens(context)
    if current_tokens <= max_tokens:
        return context
    
    # Simple truncation strategy - keep the most recent part
    # More sophisticated strategies could use summarization
    target_length = int(len(context) * (max_tokens / current_tokens))
    
    # Try to truncate at sentence boundaries
    sentences = context.split('. ')
    if len(sentences) > 1:
        compressed = ""
        for sentence in reversed(sentences):
            test_context = sentence + ". " + compressed
            if count_tokens(test_context) <= max_tokens:
                compressed = test_context
            else:
                break
        if compressed:
            return compressed.strip()
    
    # Fallback: simple truncation
    compressed = context[:target_length]
    logger.warning(f"Context truncated from {len(context)} to {len(compressed)} characters")
    return compressed

def ensure_context_fits(
    system_prompt: str,
    context: str,
    chat_history: List,
    user_input: str,
    model_identifier: str
) -> tuple[str, List]:
    """Ensure the entire context fits within model limits by compressing as needed."""
    
    # Analyze current usage
    info = analyze_context_usage(system_prompt, context, chat_history, user_input, model_identifier)
    
    if not info.needs_compression:
        logger.debug(f"Context fits comfortably: {info.total_tokens}/{info.limit} tokens")
        return context, chat_history
    
    logger.warning(f"Context limit exceeded: {info.total_tokens}/{info.limit} tokens, compressing...")
    
    # Compression strategy: prioritize system prompt > user input > context > history
    # System prompt and user input are never compressed
    
    tokens_to_remove = abs(info.remaining)
    compressed_context = context
    compressed_history = chat_history
    
    # First, try compressing history (least important for immediate context)
    history_text = "\n".join(str(msg) for msg in chat_history)
    history_tokens = count_tokens(history_text)
    
    if history_tokens > 0 and tokens_to_remove > 0:
        # Try to remove some history
        history_reduction = min(tokens_to_remove, history_tokens // 2)
        compressed_history = compress_chat_history(chat_history, history_reduction, context)
        
        # Recalculate remaining tokens needed
        new_history_text = "\n".join(str(msg) for msg in compressed_history)
        new_history_tokens = count_tokens(new_history_text)
        tokens_removed = history_tokens - new_history_tokens
        tokens_to_remove -= tokens_removed
        
        logger.info(f"Compressed history: removed {tokens_removed} tokens")
    
    # If still over limit, compress context
    if tokens_to_remove > 0 and context:
        context_tokens = count_tokens(context)
        if context_tokens > 0:
            target_context_tokens = max(context_tokens - tokens_to_remove, context_tokens // 4)
            compressed_context = compress_context(context, target_context_tokens)
            
            tokens_removed = context_tokens - count_tokens(compressed_context)
            logger.info(f"Compressed context: removed {tokens_removed} tokens")
    
    # Final verification
    final_info = analyze_context_usage(system_prompt, compressed_context, compressed_history, user_input, model_identifier)
    if final_info.needs_compression:
        logger.error(f"Still over limit after compression: {final_info.total_tokens}/{final_info.limit}")
    else:
        logger.info(f"Successfully compressed context: {final_info.total_tokens}/{final_info.limit} tokens")
    
    return compressed_context, compressed_history