import logging
import time
import json
from pathlib import Path
from typing import List, Dict, Tuple, Union

logger = logging.getLogger(__name__)

# Configuration
MAX_RECENT_TURNS = 15
MAX_RECENT_AGE_MINUTES = 10
CHAT_DATA_DIR = Path(__file__).parent.parent / "chat_data"
CHAT_DATA_DIR.mkdir(exist_ok=True)

# Storage
chat_turns: Dict[int, List[Tuple[List, float]]] = {}
chat_context: Dict[int, str] = {}

def _get_chat_data_file_path(chat_id: int, file_type: str) -> Path:
    """Get file path for chat data files."""
    return CHAT_DATA_DIR / f"{file_type}_{chat_id}.{'jsonl' if file_type == 'chat' else 'txt'}"

def _perform_chat_data_file_operation(chat_id: int, file_type: str, operation: str, data: Union[str, List] = None):
    """Unified file I/O handler for chat data operations."""
    file_path = _get_chat_data_file_path(chat_id, file_type)

    try:
        if operation == "save":
            if file_type == "chat" and chat_id in chat_turns:
                with open(file_path, 'w') as f:
                    for messages, timestamp in chat_turns[chat_id]:
                        f.write(json.dumps({'timestamp': timestamp, 'messages': messages}) + '\n')
            elif file_type == "context" and chat_id in chat_context:
                file_path.write_text(chat_context[chat_id])
            logger.debug(f"Saved {file_type} for {chat_id}")

        elif operation == "load":
            if not file_path.exists():
                return [] if file_type == "chat" else ""

            if file_type == "chat":
                data = []
                for line in file_path.read_text().strip().split('\n'):
                    if line:
                        item = json.loads(line)
                        data.append((item['messages'], item['timestamp']))
                logger.debug(f"Loaded {len(data)} message groups for chat {chat_id}")
                return data
            else:
                data = file_path.read_text().strip()
                logger.debug(f"Loaded {file_type} for chat {chat_id}")
                return data

        elif operation == "delete" and file_path.exists():
            file_path.unlink()
            logger.debug(f"Deleted {file_type} file for chat {chat_id}")

    except Exception as e:
        logger.error(f"Error {operation}ing {file_type} for {chat_id}: {e}", exc_info=True)
        return [] if file_type == "chat" and operation == "load" else ""

def _ensure_chat_history_loaded(chat_id: int):
    """Ensure chat history is loaded from disk into memory."""
    if chat_id not in chat_turns:
        chat_turns[chat_id] = _perform_chat_data_file_operation(chat_id, "chat", "load") or []

def _get_recent_turns(chat_id: int) -> List[Tuple[List, float]]:
    """Get recent turns based on time and count limits."""
    if chat_id not in chat_turns:
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

def get_chat_history(chat_id: int, full_history: bool = False) -> List:
    """Get chat history for the given chat_id."""
    _ensure_chat_history_loaded(chat_id)

    selected_turns = chat_turns[chat_id] if full_history else _get_recent_turns(chat_id)

    # Flatten message tuples
    messages = []
    for messages_in_turn, _ in selected_turns:
        messages.extend(messages_in_turn)
    return messages

def add_turn_to_history(chat_id: int, messages: List, timestamp: float):
    """Add a conversation turn (list of messages) to chat history with timestamp."""
    _ensure_chat_history_loaded(chat_id)
    chat_turns[chat_id].append((messages, timestamp))
    _perform_chat_data_file_operation(chat_id, "chat", "save")
    logger.debug(f"Added {len(messages)} messages to history for chat_id: {chat_id}")

def get_chat_context(chat_id: int) -> str:
    """Get conversation context for chat."""
    if chat_id not in chat_context:
        chat_context[chat_id] = _perform_chat_data_file_operation(chat_id, "context", "load")
    return chat_context.get(chat_id, "")

def set_chat_context(chat_id: int, context: str):
    """Set conversation context for chat."""
    logger.info(f"Setting chat context for chat_id {chat_id}: {context[:100]}{'...' if len(context) > 100 else ''}")
    chat_context[chat_id] = context
    _perform_chat_data_file_operation(chat_id, "context", "save")

    # Clear history if context is empty
    if not context.strip():
        logger.info(f"Context is blank, clearing chat history for chat_id: {chat_id}")
        clear_chat_history(chat_id)

def clear_chat_history(chat_id: int):
    """Clear in-memory chat history (preserves persistent history)."""
    logger.info(f"Clearing in-memory chat history for chat_id: {chat_id}")
    if chat_id in chat_turns:
        chat_turns[chat_id] = []

def clear_chat_context(chat_id: int):
    """Clear conversation context."""
    logger.info(f"Clearing chat context for chat_id: {chat_id}")
    chat_context.pop(chat_id, None)
    _perform_chat_data_file_operation(chat_id, "context", "delete")

def _search_messages_with_filter(chat_id: int, filter_func, max_results: int = 10) -> List[str]:
    """Generic message search with custom filter function."""
    _ensure_chat_history_loaded(chat_id)
    if not chat_turns[chat_id]:
        return []

    matches = []
    for messages, _ in chat_turns[chat_id]:
        for message in messages:
            if filter_func(str(message)) and len(matches) < max_results:
                matches.append(str(message))
    return matches

def search_chat_history_keywords(chat_id: int, keywords: List[str], max_results: int = 10) -> List[str]:
    """Search chat history for messages containing keywords."""
    keywords_lower = [kw.lower() for kw in keywords]
    return _search_messages_with_filter(
        chat_id,
        lambda msg: any(kw in msg.lower() for kw in keywords_lower),
        max_results
    )

def get_chat_history_range(chat_id: int, start_turn: int = -30, end_turn: int = -1) -> List:
    """Get chat history within turn range."""
    _ensure_chat_history_loaded(chat_id)
    if not chat_turns[chat_id]:
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

def get_chat_history_by_time(chat_id: int, minutes_ago_start: int, minutes_ago_end: int = 0) -> List:
    """Get chat history from time range."""
    _ensure_chat_history_loaded(chat_id)
    if not chat_turns[chat_id]:
        return []

    current_time = time.time()
    start_time = current_time - (minutes_ago_start * 60)
    end_time = current_time - (minutes_ago_end * 60)

    messages = []
    for messages_in_turn, timestamp in chat_turns[chat_id]:
        if start_time <= timestamp <= end_time:
            messages.extend(messages_in_turn)
    return messages