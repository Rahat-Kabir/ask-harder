import json

from app.interviews.events import StreamMessage


def format_sse(message: StreamMessage) -> str:
    return f"event: {message.event.value}\ndata: {json.dumps(message.data)}\n\n"


def format_keepalive() -> str:
    return ": keepalive\n\n"
