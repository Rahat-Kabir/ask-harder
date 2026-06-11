import json

import pytest

import app.methodology as methodology

pytestmark = pytest.mark.anyio

SAMPLE_RESULTS = {
    "judge_backend": "anthropic",
    "judge_model": "claude-sonnet-4-6",
    "generated_at": "2026-06-12T00:00:00+00:00",
    "evaluations": 30,
    "grounding": {"quotes_total": 100, "quotes_grounded": 95, "rate": 0.95},
    "key_adherence": {"points_total": 20, "points_matched": 17, "rate": 0.85},
    "fixtures": {"q01_project_walkthrough": {"ordering_ok": True}},
}


async def test_methodology_is_public_and_serves_artifacts(
    client, tmp_path, monkeypatch
):
    artifact_dir = tmp_path / "results"
    artifact_dir.mkdir()
    (artifact_dir / "anthropic.json").write_text(
        json.dumps(SAMPLE_RESULTS), encoding="utf-8"
    )
    mock_results = {
        **SAMPLE_RESULTS,
        "judge_backend": "mock",
        "judge_model": "mock",
    }
    (artifact_dir / "mock.json").write_text(json.dumps(mock_results), encoding="utf-8")
    monkeypatch.setattr(methodology, "RESULTS_DIR", artifact_dir)

    # no login/cookie — the page must be public
    response = await client.get("/api/methodology")
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    # real judges sort before the mock self-test
    assert [entry["judge_backend"] for entry in results] == ["anthropic", "mock"]
    assert results[0]["grounding"]["rate"] == 0.95
    assert results[0]["fixtures"]["q01_project_walkthrough"]["ordering_ok"] is True


async def test_methodology_with_no_artifacts(client, tmp_path, monkeypatch):
    monkeypatch.setattr(methodology, "RESULTS_DIR", tmp_path / "missing")
    response = await client.get("/api/methodology")
    assert response.status_code == 200
    assert response.json() == {"results": []}


async def test_methodology_serves_committed_artifacts(client):
    # the real results dir must parse against the schema (drift guard)
    response = await client.get("/api/methodology")
    assert response.status_code == 200
    for entry in response.json()["results"]:
        assert entry["judge_backend"]
        assert entry["evaluations"] > 0
