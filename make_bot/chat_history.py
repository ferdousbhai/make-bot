import json
import logging
import time
from pathlib import Path
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

logger = logging.getLogger(__name__)

# Configuration
MAX_RECENT_TURNS = 15
MAX_RECENT_AGE_MINUTES = 10
CHAT_DATA_DIR = Path(__file__).parent.parent / "chat_data"
CHAT_DATA_DIR.mkdir(exist_ok=True)

# In-memory storage - everything stays as ModelMessage objects
chat_turns: dict[int, list[tuple[list[ModelMessage], float]]] = {}
chat_context: dict[int, str] = {}
_loaded_chats: set[int] = set()  # Track which chats have been loaded

def _get_chat_file_path(chat_id: int) -> Path:
    """Get file path for chat history."""
    return CHAT_DATA_DIR / f"chat_{chat_id}.jsonl"

def _get_context_file_path(chat_id: int) -> Path:
    """Get file path for chat context."""
    return CHAT_DATA_DIR / f"context_{chat_id}.txt"

def _load_chat_from_disk(chat_id: int) -> list[tuple[list[ModelMessage], float]]:
    """Load chat history from disk. Only called when needed."""
    file_path = _get_chat_file_path(chat_id)

    if not file_path.exists():
        return []

    try:
        turns = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    # Parse the JSON wrapper first
                    turn_data = json.loads(line)
                    
                    # Handle both new format and potential legacy formats
                    if isinstance(turn_data, dict) and "timestamp" in turn_data:
                        if "messages_json" in turn_data:
                            # New format: messages stored as JSON string
                            messages = ModelMessagesTypeAdapter.validate_json(turn_data["messages_json"])
                            timestamp = turn_data["timestamp"]
                        elif "messages" in turn_data:
                            # Legacy format: messages stored as objects (causes warning)
                            messages_json = json.dumps(turn_data["messages"]).encode('utf-8')
                            messages = ModelMessagesTypeAdapter.validate_json(messages_json)
                            timestamp = turn_data["timestamp"]
                    else:
                        # Legacy format: try direct deserialization
                        try:
                            messages = ModelMessagesTypeAdapter.validate_json(line)
                            timestamp = time.time()
                        except:
                            # Fallback for very old formats
                            messages = turn_data if isinstance(turn_data, list) else [turn_data]
                            timestamp = time.time()

                    turns.append((messages, timestamp))
                except Exception as e:
                    logger.warning(f"Skipping corrupted line {line_num} in chat file for {chat_id}: {e}")
                    continue

        logger.debug(f"Loaded {len(turns)} turns from disk for chat_id: {chat_id}")
        return turns
    except Exception as e:
        logger.error(f"Error loading chat history from disk for chat {chat_id}: {e}", exc_info=True)
        return []

def _ensure_chat_loaded(chat_id: int):
    """Lazy load chat from disk if not already loaded."""
    if chat_id not in _loaded_chats:
        chat_turns[chat_id] = _load_chat_from_disk(chat_id)
        _loaded_chats.add(chat_id)

def _persist_turn_to_disk(chat_id: int, messages: list[ModelMessage], timestamp: float):
    """Append a single turn to disk."""
    file_path = _get_chat_file_path(chat_id)

    try:
        # Serialize messages correctly using ModelMessagesTypeAdapter
        messages_json_str = ModelMessagesTypeAdapter.dump_json(messages).decode('utf-8')
        
        # Create turn record with timestamp and messages as JSON string
        turn_data = {
            "timestamp": timestamp,
            "messages_json": messages_json_str
        }
        
        # Use standard JSON for the wrapper structure
        serialized = json.dumps(turn_data).encode('utf-8')

        with open(file_path, 'ab') as f:
            f.write(serialized + b'\n')

        logger.debug(f"Persisted turn with {len(messages)} messages for chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"Error persisting turn to disk for chat {chat_id}: {e}", exc_info=True)

def _get_recent_turns(chat_id: int) -> list[tuple[list[ModelMessage], float]]:
    """Get recent turns based on time and count limits."""
    _ensure_chat_loaded(chat_id)

    if chat_id not in chat_turns or not chat_turns[chat_id]:
        return []

    current_time = time.time()
    max_age_seconds = MAX_RECENT_AGE_MINUTES * 60

    # Get recent by time and count, return whichever is shorter
    recent_by_time = [
        (messages, ts) for messages, ts in chat_turns[chat_id]
        if current_time - ts < max_age_seconds
    ]
    recent_by_count = chat_turns[chat_id][-MAX_RECENT_TURNS:]

    return recent_by_time if len(recent_by_time) < len(recent_by_count) else recent_by_count

# Public API - everything works with ModelMessage objects directly

def get_chat_history(chat_id: int, full_history: bool = False) -> list[ModelMessage]:
    """Get chat history as ModelMessage objects - ready for agent consumption."""
    _ensure_chat_loaded(chat_id)

    selected_turns = chat_turns[chat_id] if full_history else _get_recent_turns(chat_id)

    # Flatten turns into a single list
    messages = []
    for messages_in_turn, _ in selected_turns:
        messages.extend(messages_in_turn)
    return messages

def add_turn_to_history(chat_id: int, messages: list[ModelMessage], timestamp: float):
    """Add conversation turn - no serialization overhead in memory."""
    _ensure_chat_loaded(chat_id)

    # Store in memory as-is
    if chat_id not in chat_turns:
        chat_turns[chat_id] = []

    chat_turns[chat_id].append((messages, timestamp))

    # Persist to disk (only place we serialize)
    _persist_turn_to_disk(chat_id, messages, timestamp)

    logger.debug(f"Added {len(messages)} messages to history for chat_id: {chat_id}")

def get_chat_context(chat_id: int) -> str:
    """Get conversation context."""
    if chat_id not in chat_context:
        file_path = _get_context_file_path(chat_id)
        try:
            if file_path.exists():
                chat_context[chat_id] = file_path.read_text(encoding='utf-8').strip()
            else:
                chat_context[chat_id] = ""
        except Exception as e:
            logger.error(f"Error loading context for chat {chat_id}: {e}", exc_info=True)
            chat_context[chat_id] = ""

    return chat_context.get(chat_id, "")

def set_chat_context(chat_id: int, context: str):
    """Set conversation context."""
    logger.info(f"Setting chat context for chat_id {chat_id}: {context[:100]}{'...' if len(context) > 100 else ''}")
    chat_context[chat_id] = context

    # Persist to disk
    file_path = _get_context_file_path(chat_id)
    try:
        file_path.write_text(context, encoding='utf-8')
    except Exception as e:
        logger.error(f"Error saving context for chat {chat_id}: {e}", exc_info=True)

    # Clear history if context is empty
    if not context.strip():
        logger.info(f"Context is blank, clearing chat history for chat_id: {chat_id}")
        clear_chat_history(chat_id)

def clear_chat_history(chat_id: int):
    """Clear in-memory chat history."""
    logger.info(f"Clearing in-memory chat history for chat_id: {chat_id}")
    if chat_id in chat_turns:
        chat_turns[chat_id] = []

def clear_chat_context(chat_id: int):
    """Clear conversation context."""
    logger.info(f"Clearing chat context for chat_id: {chat_id}")
    chat_context.pop(chat_id, None)

    file_path = _get_context_file_path(chat_id)
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        logger.error(f"Error deleting context file for chat {chat_id}: {e}", exc_info=True)

# Search functions - work directly with ModelMessage objects

def _extract_searchable_content(message: ModelMessage) -> str:
    """Extract searchable text from ModelMessage."""
    try:
        return str(message)
    except Exception:
        return ""

def search_chat_history_keywords(chat_id: int, keywords: list[str], max_results: int = 10) -> list[str]:
    """Search chat history for keywords."""
    _ensure_chat_loaded(chat_id)

    if chat_id not in chat_turns or not chat_turns[chat_id]:
        return []

    keywords_lower = [kw.lower() for kw in keywords]
    matches = []

    for messages, _ in chat_turns[chat_id]:
        for message in messages:
            searchable_text = _extract_searchable_content(message)
            if any(kw in searchable_text.lower() for kw in keywords_lower) and len(matches) < max_results:
                matches.append(searchable_text)

    return matches

def get_chat_history_range(chat_id: int, start_turn: int = -30, end_turn: int = -1) -> list[ModelMessage]:
    """Get chat history within turn range."""
    _ensure_chat_loaded(chat_id)

    if chat_id not in chat_turns or not chat_turns[chat_id]:
        return []

    total_turns = len(chat_turns[chat_id])

    # Convert negative indices and ensure valid range
    start_turn = max(0, total_turns + start_turn if start_turn < 0 else start_turn)
    end_turn = min(total_turns, (total_turns + end_turn + 1) if end_turn < 0 else end_turn + 1)
    start_turn = min(start_turn, total_turns)
    end_turn = max(start_turn, end_turn)

    # Flatten messages in range
    messages = []
    for messages_in_turn, _ in chat_turns[chat_id][start_turn:end_turn]:
        messages.extend(messages_in_turn)
    return messages

def get_chat_history_by_time(chat_id: int, minutes_ago_start: int, minutes_ago_end: int = 0) -> list[ModelMessage]:
    """Get chat history from time range."""
    _ensure_chat_loaded(chat_id)

    if chat_id not in chat_turns or not chat_turns[chat_id]:
        return []

    current_time = time.time()
    start_time = current_time - (minutes_ago_start * 60)
    end_time = current_time - (minutes_ago_end * 60)

    messages = []
    for messages_in_turn, timestamp in chat_turns[chat_id]:
        if start_time <= timestamp <= end_time:
            messages.extend(messages_in_turn)
    return messages