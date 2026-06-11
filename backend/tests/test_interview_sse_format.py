from app.interviews.events import StreamEventName, StreamMessage
from app.interviews.sse import format_keepalive, format_sse


def test_format_sse_serializes_event_and_data():
    message = StreamMessage(
        event=StreamEventName.token,
        data={"text": "Hello"},
    )
    assert format_sse(message) == (
        'event: token\n'
        'data: {"text": "Hello"}\n\n'
    )


def test_format_keepalive_is_sse_comment():
    assert format_keepalive() == ": keepalive\n\n"
