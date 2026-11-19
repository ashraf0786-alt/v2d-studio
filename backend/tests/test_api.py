"""API-level tests for auth, entitlements, jobs and billing gates."""
from __future__ import annotations

import time

import pytest


def _wait(client, headers, job_id, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.25)
    raise AssertionError("job did not finish in time")


def test_health_and_auth(client, owner_headers):
    assert client.get("/api/health").json()["status"] == "ok"
    me = client.get("/api/auth/me", headers=owner_headers).json()
    assert me["is_owner"] is True
    assert me["plan"] == "owner"


def test_free_plan_and_owner_bypass(client, free_headers, owner_headers):
    free_plan = client.get("/api/billing/plans", headers=free_headers).json()["current"]
    assert free_plan["max_duration_seconds"] == 10
    assert free_plan["plan"] == "free"
    owner_plan = client.get("/api/billing/plans", headers=owner_headers).json()["current"]
    assert owner_plan["plan"] == "owner"
    assert client.get("/api/billing/api-keys", headers=free_headers).status_code == 403
    assert client.get("/api/billing/api-keys", headers=owner_headers).status_code == 200


def test_verify_and_reset_flows(client, free_headers):
    sent = client.post("/api/auth/verify/send", headers=free_headers).json()
    assert sent["sent"] is True
    token = sent["dev_token"]
    assert client.post("/api/auth/verify/confirm", json={"token": token}).json()["verified"] is True
    assert client.post("/api/auth/verify/confirm", json={"token": token}).status_code == 400

    email = client.get("/api/auth/me", headers=free_headers).json()["email"]
    reset = client.post("/api/auth/reset/request", json={"email": email}).json()
    assert client.post("/api/auth/reset/confirm", json={
        "token": reset["dev_token"], "new_password": "newpassword123"}).json()["reset"] is True
    assert client.post("/api/auth/login", json={
        "email": email, "password": "newpassword123"}).status_code == 200


@pytest.mark.parametrize("mode", ["parallax", "mocap", "scene"])
def test_all_modes_complete(client, owner_headers, mode):
    r = client.post("/api/jobs/demo", headers=owner_headers,
                    data={"mode": mode, "seconds": 5})
    assert r.status_code == 200, r.text
    job = _wait(client, owner_headers, r.json()["id"])
    assert job["status"] == "completed", job["error"]
    assert job["result"]
    assert job["result"]["shots"] >= 1


def test_parallax_exports_are_real_files(client, owner_headers):
    jid = client.post("/api/jobs/demo", headers=owner_headers,
                      data={"mode": "parallax", "seconds": 5}).json()["id"]
    job = _wait(client, owner_headers, jid)
    result = job["result"]
    for key in ("video", "videos", "glb", "keyframe", "depth"):
        assert key in result, result
    url = result["glb"]
    data = client.get(url).content
    assert data[:4] == b"glTF"
    for url in result["videos"].values():
        assert client.get(url).status_code == 200


def test_api_key_and_public_api(client, owner_headers):
    key = client.post("/api/billing/api-keys", headers=owner_headers,
                      json={"name": "test"}).json()["key"]
    headers = {"X-API-Key": key}
    assert client.get("/api/v1/jobs", headers=headers).status_code == 200
    assert client.get("/api/v1/jobs", headers={"X-API-Key": "bad"}).status_code == 401
    import hashlib
    assert client.get("/api/billing/api-keys", headers=owner_headers).json()[0]["prefix"] == \
        hashlib.sha256(key.encode()).hexdigest()[:8]


def test_length_limit_enforced(client, free_headers):
    from pathlib import Path
    video = Path("/tmp/opencode/v2d-tests/long.mp4")
    if not video.exists():
        import subprocess
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
            "-i", "color=c=blue:s=160x90:d=12:r=12", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", str(video),
        ], check=True)
    with open(video, "rb") as f:
        r = client.post("/api/jobs/upload", headers=free_headers,
                        data={"mode": "parallax"},
                        files={"file": ("long.mp4", f, "video/mp4")})
    assert r.status_code == 402
