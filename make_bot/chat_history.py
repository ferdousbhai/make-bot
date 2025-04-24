import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# chat_map should ideally be persisted, but using in-memory for now.
chat_map: Dict[int, List] = {}

def get_chat_history(chat_id: int) -> List:
    """Get the chat history for the given chat_id, initializing it if necessary."""
    if chat_id not in chat_map:
        logger.info(f"Initializing chat history for chat_id: {chat_id}")
        chat_map[chat_id] = []
    return chat_map[chat_id]

def clear_chat(chat_id: int):
    """Clear the chat history for the given chat_id."""
    logger.info(f"Clearing chat history for chat_id: {chat_id}")
    chat_map[chat_id] = []

def add_messages_to_history(chat_id: int, messages: List):
    """Add messages to the chat history for the given chat_id."""
    if chat_id not in chat_map:
        # This case should ideally not happen if get_chat_history is called first
        logger.warning(f"Chat history for {chat_id} not found, initializing before adding messages.")
        chat_map[chat_id] = []
    # TODO: Ensure messages are in the correct format if needed (e.g., BaseMessage instances)
    chat_map[chat_id].extend(messages)
    logger.debug(f"Added {len(messages)} messages to history for chat_id: {chat_id}") 