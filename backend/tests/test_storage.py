"""S3 storage helper tests using moto (skipped if moto is not installed)."""
from __future__ import annotations

import pytest

moto = pytest.importorskip("moto")
boto3 = pytest.importorskip("boto3")

from app import storage  # noqa: E402
from app.config import settings  # noqa: E402


def test_s3_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(settings, "S3_BUCKET", "v2d-test")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "test")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "test")
    monkeypatch.setattr(settings, "STORAGE_DIR", tmp_path / "local")
    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="v2d-test")
        path = storage.save_upload(7, "job1", "hello.txt", b"hello world")
        assert storage.sync_to_s3(7, "job1") == 1
        path.unlink()
        fetched = storage.get_local_path(7, "job1", "input_hello.txt")
        assert fetched.read_bytes() == b"hello world"
        storage.remove_job(7, "job1")
        assert storage.list_objects(7, "job1") == []
