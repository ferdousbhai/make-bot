import logging
import time
import json
from pathlib import Path
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

# Configuration for chat history limits (for recent context only)
MAX_RECENT_MESSAGES = 15
MAX_RECENT_AGE_MINUTES = 10

# Configuration for persistence
CHAT_DATA_DIR = Path(__file__).parent.parent / "chat_data"
CHAT_DATA_DIR.mkdir(exist_ok=True)

# chat_map now stores tuples of (messages, timestamp)
chat_map: Dict[int, List[Tuple[List, float]]] = {}

# Store conversation context for each chat
chat_context: Dict[int, str] = {}

def _get_file_path(chat_id: int, file_type: str) -> Path:
    """Get the file path for a specific chat file type."""
    if file_type == "chat":
        return CHAT_DATA_DIR / f"chat_{chat_id}.jsonl"
    elif file_type == "context":
        return CHAT_DATA_DIR / f"context_{chat_id}.txt"
    else:
        raise ValueError(f"Unknown file type: {file_type}")

def _save_to_file(chat_id: int, file_type: str):
    """Save chat data to file."""
    file_path = _get_file_path(chat_id, file_type)
    
    try:
        if file_type == "chat":
            if chat_id not in chat_map:
                return
            with open(file_path, 'w') as f:
                for messages, timestamp in chat_map[chat_id]:
                    line = {
                        'timestamp': timestamp,
                        'messages': messages
                    }
                    f.write(json.dumps(line) + '\n')
        elif file_type == "context":
            if chat_id not in chat_context:
                return
            with open(file_path, 'w') as f:
                f.write(chat_context[chat_id])
        
        logger.debug(f"Saved {file_type} for {chat_id} to {file_path}")
    except Exception as e:
        logger.error(f"Error saving {file_type} for {chat_id}: {e}", exc_info=True)

def _load_from_file(chat_id: int, file_type: str):
    """Load chat data from file."""
    file_path = _get_file_path(chat_id, file_type)
    if not file_path.exists():
        return [] if file_type == "chat" else ""
    
    try:
        if file_type == "chat":
            messages = []
            with open(file_path, 'r') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        messages.append((data['messages'], data['timestamp']))
            logger.debug(f"Loaded {len(messages)} message groups for chat {chat_id}")
            return messages
        elif file_type == "context":
            with open(file_path, 'r') as f:
                context = f.read().strip()
            logger.debug(f"Loaded context for chat {chat_id}")
            return context
    except Exception as e:
        logger.error(f"Error loading {file_type} for {chat_id}: {e}", exc_info=True)
        return [] if file_type == "chat" else ""

def _ensure_chat_loaded(chat_id: int):
    """Ensure chat history is loaded for the given chat_id."""
    if chat_id not in chat_map:
        chat_map[chat_id] = _load_from_file(chat_id, "chat")
        if not chat_map[chat_id]:
            chat_map[chat_id] = []

def _get_recent_messages(chat_id: int) -> List[Tuple[List, float]]:
    """Get recent messages based on time and count limits."""
    if chat_id not in chat_map:
        return []
    
    current_time = time.time()
    max_age_seconds = MAX_RECENT_AGE_MINUTES * 60
    
    # Filter by time - get messages newer than MAX_RECENT_AGE_MINUTES
    recent_by_time = [
        (messages, timestamp) for messages, timestamp in chat_map[chat_id] 
        if current_time - timestamp < max_age_seconds
    ]
    
    # Filter by count - get only the most recent MAX_RECENT_MESSAGES message groups
    recent_by_count = chat_map[chat_id][-MAX_RECENT_MESSAGES:]
    
    # Return whichever is shorter
    if len(recent_by_time) < len(recent_by_count):
        return recent_by_time
    else:
        return recent_by_count

def get_chat_history(chat_id: int, full_history: bool = False) -> List:
    """Get chat history for the given chat_id.
    
    Args:
        chat_id: The chat ID
        full_history: If True, return complete history; if False, return recent only
    """
    _ensure_chat_loaded(chat_id)
    
    # Choose which messages to return
    if full_history:
        selected_messages = chat_map[chat_id]
    else:
        selected_messages = _get_recent_messages(chat_id)
    
    # Flatten message tuples back to a simple list
    messages = []
    for message_list, timestamp in selected_messages:
        messages.extend(message_list)
    
    return messages

def clear_chat(chat_id: int):
    """Clear the in-memory chat history for fresh conversation start (keeps persistent history intact)."""
    logger.info(f"Clearing in-memory chat history for chat_id: {chat_id} (persistent history preserved)")
    chat_map[chat_id] = []
    # Note: We deliberately do NOT clear the persistent .jsonl file to preserve full history

def add_messages_to_history(chat_id: int, messages: List, timestamp: float):
    """Add messages to the chat history for the given chat_id with timestamp.
    
    Args:
        chat_id: The chat ID
        messages: List of messages to add
        timestamp: Unix timestamp for the messages
    """
    _ensure_chat_loaded(chat_id)
    
    # Add messages with timestamp as tuple
    chat_map[chat_id].append((messages, timestamp))
    
    # Auto-save to file
    _save_to_file(chat_id, "chat")
    
    logger.debug(f"Added {len(messages)} messages to history for chat_id: {chat_id}")

def get_chat_context(chat_id: int) -> str:
    """Get the current conversation context for the given chat_id."""
    if chat_id not in chat_context:
        chat_context[chat_id] = _load_from_file(chat_id, "context")
    return chat_context.get(chat_id, "")

def set_chat_context(chat_id: int, context: str):
    """Set the conversation context for the given chat_id."""
    logger.info(f"Setting chat context for chat_id {chat_id}: {context[:100]}{'...' if len(context) > 100 else ''}")
    chat_context[chat_id] = context
    
    # Auto-save context to file
    _save_to_file(chat_id, "context")
    
    # If context is empty/blank, also clear the chat history to start fresh
    if not context.strip():
        logger.info(f"Context is blank, clearing chat history for chat_id: {chat_id}")
        clear_chat(chat_id)

def clear_chat_context(chat_id: int):
    """Clear the conversation context for the given chat_id."""
    logger.info(f"Clearing chat context for chat_id: {chat_id}")
    if chat_id in chat_context:
        del chat_context[chat_id]
    
    # Also clear the context file
    context_file = _get_file_path(chat_id, "context")
    if context_file.exists():
        try:
            context_file.unlink()
            logger.debug(f"Deleted context file for chat {chat_id}")
        except Exception as e:
            logger.error(f"Error deleting context file for {chat_id}: {e}", exc_info=True)

def search_chat_history_keywords(chat_id: int, keywords: List[str], max_results: int = 10) -> List[str]:
    """Search chat history for messages containing any of the specified keywords.
    
    Args:
        chat_id: The chat ID to search
        keywords: List of keywords to search for (case-insensitive, OR search)
        max_results: Maximum number of matching messages to return
        
    Returns:
        List of messages containing any of the keywords
    """
    _ensure_chat_loaded(chat_id)
    if not chat_map[chat_id]:
        return []
    
    keywords_lower = [keyword.lower() for keyword in keywords]
    matches = []
    
    for messages, timestamp in chat_map[chat_id]:
        for message in messages:
            # Convert message to string for searching (handles different message types)
            message_str = str(message).lower()
            
            # Check if any keyword matches
            if any(keyword in message_str for keyword in keywords_lower):
                matches.append(str(message))  # Keep original case for display
                if len(matches) >= max_results:
                    return matches
    
    return matches

def get_chat_history_range(chat_id: int, start_turn: int = -30, end_turn: int = -1) -> List:
    """Get chat history within a specific turn range.
    
    Args:
        chat_id: The chat ID
        start_turn: Starting turn (negative numbers count from end, e.g., -30 = 30 turns ago)
        end_turn: Ending turn (negative numbers count from end, e.g., -1 = most recent)
        
    Returns:
        List of messages in the specified range
    """
    _ensure_chat_loaded(chat_id)
    if not chat_map[chat_id]:
        return []
    
    total_turns = len(chat_map[chat_id])
    
    # Convert negative indices to positive
    if start_turn < 0:
        start_turn = max(0, total_turns + start_turn)
    if end_turn < 0:
        end_turn = total_turns + end_turn + 1
    else:
        end_turn = min(end_turn + 1, total_turns)
    
    # Ensure valid range
    start_turn = max(0, min(start_turn, total_turns))
    end_turn = max(start_turn, min(end_turn, total_turns))
    
    # Get messages in range
    messages = []
    for message_list, timestamp in chat_map[chat_id][start_turn:end_turn]:
        messages.extend(message_list)
    
    return messages

def get_chat_history_by_time(chat_id: int, minutes_ago_start: int, minutes_ago_end: int = 0) -> List:
    """Get chat history from a specific time range.
    
    Args:
        chat_id: The chat ID
        minutes_ago_start: How many minutes back to start looking (older boundary)
        minutes_ago_end: How many minutes back to stop looking (newer boundary, default: 0 = now)
        
    Returns:
        List of messages from the specified time range
        
    Examples:
        get_chat_history_by_time(123, 30, 0)    # Last 30 minutes
        get_chat_history_by_time(123, 60, 30)   # Between 60-30 minutes ago
        get_chat_history_by_time(123, 120, 90)  # Between 2-1.5 hours ago
    """
    _ensure_chat_loaded(chat_id)
    if not chat_map[chat_id]:
        return []
    
    current_time = time.time()
    start_time = current_time - (minutes_ago_start * 60)  # Older boundary
    end_time = current_time - (minutes_ago_end * 60)      # Newer boundary
    
    messages = []
    for message_list, timestamp in chat_map[chat_id]:
        # Message is in range if timestamp is between start_time and end_time
        if start_time <= timestamp <= end_time:
            messages.extend(message_list)
    
    return messages 