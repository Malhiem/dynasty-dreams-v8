"""Persist a chat intent once, including concurrent response-loss retries."""
from hashlib import sha256
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError


async def persist_message(db, message, client_id=None):
    if client_id is not None:
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 128:
            raise HTTPException(400, "Invalid client message ID")
        identity = f"chat:{message['channel_id']}:{message['user_id']}:{client_id}"
        message["_id"] = ObjectId(sha256(identity.encode()).hexdigest()[:24])
    try:
        result = await db.chat_messages.insert_one(message)
        message["_id"] = result.inserted_id
        return message, True
    except DuplicateKeyError:
        existing = await db.chat_messages.find_one({"_id": message["_id"]})
        if existing is None or existing.get("content") != message["content"]:
            raise HTTPException(409, "This message ID was already used for different content")
        return existing, False
