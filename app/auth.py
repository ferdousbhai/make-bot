import functools
import logging
import os
from telegram import Update
from telegram.ext import ContextTypes

chat_ids_str = os.getenv('ALLOWED_CHAT_IDS', '')
ALLOWED_CHAT_IDS = set(int(x.strip()) for x in chat_ids_str.strip('[]').replace(' ','').split(',') if x.strip()) if chat_ids_str else set()

logger = logging.getLogger(__name__)

def is_user_authorized(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.message.chat_id
        if ALLOWED_CHAT_IDS and chat_id not in ALLOWED_CHAT_IDS:
            logger.warning(f"Unauthorized access from chat_id: {chat_id} for {func.__name__}")
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper