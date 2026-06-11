"""In-process SSE fan-out for a single-server deployment.

POST /answer and POST /finish still mutate state via InterviewService; this bus
delivers the interviewer-side events to any open stream for that interview.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID


class StreamEventName(str, Enum):
    question = "question"
    token = "token"
    interviewer_done = "interviewer_done"
    interview_complete = "interview_complete"


@dataclass(frozen=True)
class StreamMessage:
    event: StreamEventName
    data: dict[str, Any]


class InterviewEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[UUID, list[asyncio.Queue[StreamMessage | None]]] = (
            defaultdict(list)
        )

    def subscribe(self, interview_id: UUID) -> asyncio.Queue[StreamMessage | None]:
        queue: asyncio.Queue[StreamMessage | None] = asyncio.Queue()
        self._subscribers[interview_id].append(queue)
        return queue

    def unsubscribe(
        self, interview_id: UUID, queue: asyncio.Queue[StreamMessage | None]
    ) -> None:
        subscribers = self._subscribers.get(interview_id, [])
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            self._subscribers.pop(interview_id, None)

    def publish(
        self,
        interview_id: UUID,
        event: StreamEventName,
        data: dict[str, Any],
    ) -> None:
        message = StreamMessage(event=event, data=data)
        for queue in list(self._subscribers.get(interview_id, [])):
            queue.put_nowait(message)

    def close(self, interview_id: UUID) -> None:
        for queue in list(self._subscribers.get(interview_id, [])):
            queue.put_nowait(None)
        self._subscribers.pop(interview_id, None)

    def clear(self) -> None:
        for interview_id in list(self._subscribers):
            self.close(interview_id)


interview_events = InterviewEventBus()
