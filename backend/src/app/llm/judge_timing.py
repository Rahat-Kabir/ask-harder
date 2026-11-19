import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from uuid import UUID

# Uvicorn's configured handler emits INFO records to the dyno log stream.
logger = logging.getLogger("uvicorn.error.askharder.judging")
_interview_id: ContextVar[UUID | None] = ContextVar(
    "judging_interview_id", default=None
)


@contextmanager
def time_judging_stage(stage: str, **fields: str | int) -> Iterator[None]:
    metadata = " ".join(f"{key}={value}" for key, value in fields.items())
    label = (
        f"judging stage={stage} interview_id={_interview_id.get()} {metadata}".rstrip()
    )
    started = perf_counter()
    logger.info("%s event=start", label)
    outcome = "interrupted"
    try:
        yield
        outcome = "ok"
    finally:
        logger.info(
            "%s event=end outcome=%s elapsed_ms=%.1f",
            label,
            outcome,
            (perf_counter() - started) * 1000,
        )


@contextmanager
def time_judging_run(interview_id: UUID) -> Iterator[None]:
    token = _interview_id.set(interview_id)
    try:
        with time_judging_stage("run"):
            yield
    finally:
        _interview_id.reset(token)
