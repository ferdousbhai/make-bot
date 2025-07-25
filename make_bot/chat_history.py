import json
import logging
import time
from pathlib import Path
from pydantic_ai.messages import ModelMessage, UserPromptPart

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

def _extract_user_assistant_messages(messages: list[ModelMessage]) -> tuple[str, str]:
    """Extract user input and assistant response from ModelMessage list.

    Returns:
        Tuple of (user_message, assistant_message)
    """
    user_message = ""
    assistant_message = ""

    for message in messages:
        if hasattr(message, 'parts'):
            for part in message.parts:
                if hasattr(part, 'part_kind'):
                    if part.part_kind == 'user-prompt':
                        user_message = part.content if isinstance(part.content, str) else str(part.content)
                    elif part.part_kind == 'text':
                        assistant_message = part.content

    return user_message, assistant_message

def _save_conversation_turn(chat_id: int, messages: list[ModelMessage]) -> None:
    """Save a single conversation turn to disk in simplified format."""
    user_msg, assistant_msg = _extract_user_assistant_messages(messages)

    if user_msg or assistant_msg:  # Only save if we have actual content
        turn_data = {
            "timestamp": time.time(),
            "user": user_msg,
            "assistant": assistant_msg
        }

        file_path = _get_chat_file_path(chat_id)
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(turn_data, ensure_ascii=False) + '\n')

def _load_chat_from_disk(chat_id: int) -> list[tuple[list[ModelMessage], float]]:
    """Load chat history from disk and convert back to ModelMessage format.

    Returns:
        List of (messages, timestamp) tuples
    """
    file_path = _get_chat_file_path(chat_id)
    if not file_path.exists():
        return []

    turns = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    turn_data = json.loads(line.strip())

                    # Convert simplified format back to ModelMessage objects
                    messages = []
                    if turn_data.get("user"):
                        # Create a simple user message
                        user_part = UserPromptPart(content=turn_data["user"])
                        # Note: We can't perfectly reconstruct the original ModelRequest,
                        # but we can create a minimal representation
                        messages.append(user_part)

                    if turn_data.get("assistant"):
                        # Create a simple assistant response
                        # Note: This is a simplified reconstruction
                        messages.append(turn_data["assistant"])

                    if messages:
                        turns.append((messages, turn_data.get("timestamp", time.time())))

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error loading chat {chat_id}: {e}")
        return []

    return turns

def add_chat_turn(chat_id: int, messages: list[ModelMessage]) -> None:
    """Add a new conversation turn to both memory and disk."""
    timestamp = time.time()

    # Add to memory
    if chat_id not in chat_turns:
        chat_turns[chat_id] = []
    chat_turns[chat_id].append((messages, timestamp))

    # Save to disk
    _save_conversation_turn(chat_id, messages)

    # Trim old turns in memory
    _trim_old_turns(chat_id)

def _trim_old_turns(chat_id: int) -> None:
    """Remove old turns from memory to keep it manageable."""
    if chat_id not in chat_turns:
        return

    current_time = time.time()
    cutoff_time = current_time - (MAX_RECENT_AGE_MINUTES * 60)

    # Keep recent turns by count and age
    turns = chat_turns[chat_id]

    # First, keep the most recent N turns
    recent_turns = turns[-MAX_RECENT_TURNS:]

    # Then, filter by age
    filtered_turns = [
        (msgs, ts) for msgs, ts in recent_turns
        if ts >= cutoff_time
    ]

    # Always keep at least one turn if we have any
    if not filtered_turns and turns:
        filtered_turns = [turns[-1]]

    chat_turns[chat_id] = filtered_turns

def get_recent_messages(chat_id: int) -> list[ModelMessage]:
    """Get recent chat messages for this chat ID."""
    # Load from disk if not in memory
    if chat_id not in _loaded_chats:
        disk_turns = _load_chat_from_disk(chat_id)
        if chat_id not in chat_turns:
            chat_turns[chat_id] = []
        chat_turns[chat_id].extend(disk_turns)
        _loaded_chats.add(chat_id)
        _trim_old_turns(chat_id)

    if chat_id not in chat_turns:
        return []

    # Flatten all messages from recent turns
    all_messages = []
    for messages, _ in chat_turns[chat_id]:
        all_messages.extend(messages)

    return all_messages

def save_chat_context(chat_id: int, context: str) -> None:
    """Save chat context to disk."""
    chat_context[chat_id] = context
    context_file = _get_context_file_path(chat_id)

    try:
        with open(context_file, 'w', encoding='utf-8') as f:
            f.write(context)
    except Exception as e:
        logger.error(f"Failed to save context for chat {chat_id}: {e}")

def load_chat_context(chat_id: int) -> str:
    """Load chat context from disk."""
    if chat_id in chat_context:
        return chat_context[chat_id]

    context_file = _get_context_file_path(chat_id)
    if context_file.exists():
        try:
            with open(context_file, 'r', encoding='utf-8') as f:
                context = f.read().strip()
                chat_context[chat_id] = context
                return context
        except Exception as e:
            logger.error(f"Failed to load context for chat {chat_id}: {e}")

    return ""

def update_chat_context(chat_id: int, new_context: str) -> None:
    """Update and save chat context."""
    save_chat_context(chat_id, new_context)

def clear_chat_history(chat_id: int) -> None:
    """Clear all history for a specific chat."""
    # Clear from memory
    if chat_id in chat_turns:
        del chat_turns[chat_id]
    if chat_id in chat_context:
        del chat_context[chat_id]
    if chat_id in _loaded_chats:
        _loaded_chats.remove(chat_id)

    # Clear from disk
    chat_file = _get_chat_file_path(chat_id)
    context_file = _get_context_file_path(chat_id)

    try:
        if chat_file.exists():
            chat_file.unlink()
        if context_file.exists():
            context_file.unlink()
    except Exception as e:
        logger.error(f"Failed to clear files for chat {chat_id}: {e}")