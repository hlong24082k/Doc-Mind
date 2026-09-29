# src/app/models/message.py

from enum import Enum as PyEnum


class MessageSenderType(str, PyEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
