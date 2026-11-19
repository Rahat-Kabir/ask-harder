"""Benchmark warm, signed-in report reads against a disposable local API worker."""

import argparse
import hashlib
import json
import math
import multiprocessing
import os
import platform
import secrets
import socket
import statistics
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path

import httpx
import uvicorn
from sqlalchemy.engine import make_url

from app.config import settings
from app.interviews.schemas import ReportOut

ROOT = Path(__file__).resolve().parents[2]
CLIENT_COUNTS = (1, 12)
BATCHES = 3
READS_PER_CLIENT = 30
ANSWER = (
    "I checked the query plan on representative data, measured the slow path, "
    "and compared the latency before and after adding an index."
)


def serve(listener):
    # Skip startup recovery of unrelated interviews in the dev database.
    config = uvicorn.Config(
        "app.main:app", lifespan="off", access_log=False, log_level="warning"
    )
    uvicorn.Server(config).run(sockets=[listener])


@contextmanager
def local_api():
    database = make_url(settings.database_url)
    if database.host not in {"127.0.0.1", "localhost", "::1"} or database.query:
        raise ValueError(
            "A loopback DATABASE_URL without routing overrides is required"
        )
    os.environ.update(LLM_BACKEND="mock", APP_ENV="dev")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        worker = multiprocessing.get_context("spawn").Process(
            target=serve, args=(listener,)
        )
        worker.start()
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", trust_env=False
            ) as client:
                deadline = time.monotonic() + 120
                while worker.is_alive() and time.monotonic() < deadline:
                    try:
                        client.get("/health").raise_for_status()
                        break
                    except httpx.ConnectError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Benchmark worker failed to start")
                yield client, port
        finally:
            worker.terminate()
            worker.join()


@contextmanager
def completed_report(client):
    credentials = {
        "email": f"benchmark-{uuid.uuid4().hex}@example.com",
        "password": secrets.token_urlsafe(32),
    }
    account = (
        client.post("/api/auth/register", json=credentials).raise_for_status().json()
    )
    try:
        created = (
            client.post(
                "/api/interviews",
                json={
                    "session_type": "full_loop",
                    "jd_text": "Senior Python backend engineer using Postgres.",
                },
            )
            .raise_for_status()
            .json()
        )
        interview_id = created["id"]
        base = f"/api/interviews/{interview_id}"
        client.post(base + "/start").raise_for_status()
        for position in range(7):
            if position < 4:
                for _ in range(2):
                    client.post(
                        base + "/answer", json={"text": ANSWER}
                    ).raise_for_status()
            else:
                client.post(base + "/skip").raise_for_status()
        client.post(base + "/finish").raise_for_status()
        path = base + "/report"
        response = client.get(path).raise_for_status()
        report = ReportOut.model_validate_json(response.content)
        turn_counts = [len(question.turns) for question in report.questions]
        if (
            str(report.id) != interview_id
            or report.status != "complete"
            or [question.position for question in report.questions] != list(range(7))
            or turn_counts != [4, 4, 4, 4, 2, 2, 2]
        ):
            raise ValueError(
                "Report identity, completion state, or fixture shape is incorrect"
            )
        cookie = client.build_request("GET", path).headers["cookie"]
        yield path, cookie, response.content
    finally:
        if client.get("/api/me").raise_for_status().json()["id"] != account["id"]:
            raise RuntimeError("Fixture owner changed during benchmark")
        client.delete("/api/me").raise_for_status()


def measure_batch(port, path, cookie, expected_body, clients):
    ready = threading.Barrier(clients, timeout=30)

    def read_reports():
        connection = HTTPConnection("127.0.0.1", port, timeout=15)
        durations = []
        try:
            for index in range(READS_PER_CLIENT + 1):
                started = time.perf_counter()
                connection.request("GET", path, headers={"Cookie": cookie})
                response = connection.getresponse()
                body = response.read()
                elapsed = (time.perf_counter() - started) * 1000
                if response.status != 200 or body != expected_body:
                    raise ValueError(
                        f"Unexpected report response (HTTP {response.status})"
                    )
                if connection.sock is None:
                    raise RuntimeError("Server closed the keep-alive connection")
                if index == 0:
                    ready.wait()
                else:
                    durations.append(elapsed)
        finally:
            connection.close()
        return durations

    with ThreadPoolExecutor(clients) as workers:
        futures = [workers.submit(read_reports) for _ in range(clients)]
        timings = sorted(value for future in futures for value in future.result())
    return {
        "median": statistics.median(timings),
        "p95": timings[math.ceil(0.95 * len(timings)) - 1],
    }


def compare(before, after):
    if before["environment"] != after["environment"]:
        return (
            3,
            "Inconclusive: environment or workload differs. Capture a fresh baseline.",
        )
    flags = []
    spikes = []
    for clients in CLIENT_COUNTS:
        before_batches = before["batches"][str(clients)]
        after_batches = after["batches"][str(clients)]
        if len(before_batches) != BATCHES or len(after_batches) != BATCHES:
            raise ValueError("Incomplete benchmark batches")
        for metric in ("median", "p95"):
            hits = sum(
                new[metric] - old[metric] >= 20 and new[metric] >= 1.25 * old[metric]
                for old, new in zip(before_batches, after_batches, strict=True)
            )
            if hits:
                (flags if hits >= 2 else spikes).append(
                    f"{clients} client(s) {metric}: {hits}/3"
                )
    if flags:
        return 2, "Slowdown: " + ", ".join(flags)
    if spikes:
        return 3, "Inconclusive: isolated spike; repeat. " + ", ".join(spikes)
    return 0, "Pass: no repeated slowdown or isolated threshold crossing."


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, help="Write this run to a new JSON file")
    parser.add_argument("--before", type=Path, help="Compare against a saved run")
    args = parser.parse_args()
    before = (
        json.loads(args.before.read_text(encoding="utf-8")) if args.before else None
    )
    if args.save and args.save.exists():
        parser.error("--save requires a new path")
    database = make_url(settings.database_url)
    result = {
        "utc": datetime.now(UTC).isoformat(),
        "revision": git("rev-parse", "--short", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "environment": {
            "machine": platform.node(),
            "os": platform.platform(),
            "python": platform.python_version(),
            "database": [database.host, database.port or 5432, database.database],
            "workload": "mock-report-v1",
            "reads_per_client": READS_PER_CLIENT,
        },
        "batches": {str(clients): [] for clients in CLIENT_COUNTS},
    }
    with (
        local_api() as (client, port),
        completed_report(client) as (path, cookie, body),
    ):
        result["payload_bytes"] = len(body)
        # Fresh fixtures have different turn IDs and timestamps.
        report = json.loads(body)
        questions = report["questions"]
        for question in questions:
            for turn in question["turns"]:
                del turn["id"], turn["created_at"]
        stable_payload = json.dumps(questions, sort_keys=True).encode()
        result["environment"]["fixture_sha256"] = hashlib.sha256(
            stable_payload
        ).hexdigest()
        for batch in range(1, BATCHES + 1):
            for clients in CLIENT_COUNTS:
                metrics = measure_batch(port, path, cookie, body, clients)
                result["batches"][str(clients)].append(metrics)
                print(
                    f"Batch {batch}, clients {clients}: "
                    f"median {metrics['median']:.2f} ms, "
                    f"p95 {metrics['p95']:.2f} ms",
                    flush=True,
                )
    if args.save:
        with args.save.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
    if before is not None:
        code, message = compare(before, result)
        print(message)
        return code
    print(f"Baseline {result['revision']}, dirty={result['dirty']}, {len(body)} bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
