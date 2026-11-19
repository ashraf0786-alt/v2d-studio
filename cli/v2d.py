#!/usr/bin/env python3
"""Command-line client for Video to 3D Studio.

Usage:
  v2d login --email you@example.com --password ...
  v2d convert video.mp4 --mode parallax --out ./results
  v2d demo --mode scene
  v2d jobs
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("Install the CLI dependency: pip install httpx")

CONFIG_DIR = Path.home() / ".v2d"
TOKEN_FILE = CONFIG_DIR / "token"
API = os.getenv("V2D_API", "http://localhost:8000")


def token() -> str:
    return TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""


def headers() -> dict:
    t = token()
    if not t:
        sys.exit("Not logged in. Run: v2d login --email ... --password ...")
    return {"Authorization": f"Bearer {t}"}


def login(args):
    with httpx.Client(base_url=API, timeout=30) as c:
        r = c.post("/api/auth/login", json={"email": args.email, "password": args.password})
    if r.status_code != 200:
        sys.exit(f"Login failed: {r.text}")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(r.json()["access_token"])
    TOKEN_FILE.chmod(0o600)
    print("Logged in.")


def watch(c, job_id: str, quiet: bool = False):
    last = -1
    while True:
        r = c.get(f"/api/jobs/{job_id}", headers=headers())
        r.raise_for_status()
        job = r.json()
        if job["progress"] != last and not quiet:
            print(f"  [{job['progress']:3d}%] {job['message']}")
            last = job["progress"]
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(1)


def download(c, job: dict, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    result = job.get("result") or {}
    urls = []
    if result.get("videos"):
        urls += list(result["videos"].values())
    if result.get("formats"):
        urls += list(result["formats"].values())
    for key in ("video", "glb", "bvh", "pose", "point_cloud", "keyframe", "depth"):
        if result.get(key):
            urls.append(result[key])
    for url in dict.fromkeys(urls):
        r = c.get(url)
        if r.status_code != 200:
            print(f"  ! failed to download {url}", file=sys.stderr)
            continue
        name = url.split("/")[-1].split("?")[0]
        (out / name).write_bytes(r.content)
        print(f"  saved {out / name}")


def convert(args):
    with httpx.Client(base_url=API, timeout=120) as c:
        if args.file:
            with open(args.file, "rb") as f:
                r = c.post("/api/jobs/upload", headers=headers(),
                           data={"mode": args.mode, "max_width": str(args.width)},
                           files={"file": (Path(args.file).name, f)})
        else:
            r = c.post("/api/jobs/demo", headers=headers(),
                       data={"mode": args.mode, "seconds": str(args.seconds)})
        if r.status_code != 200:
            sys.exit(f"Submission failed ({r.status_code}): {r.text}")
        job_id = r.json()["id"]
        print(f"Job {job_id} submitted.")
        job = watch(c, job_id, args.quiet)
        if job["status"] == "failed":
            sys.exit(f"Conversion failed: {job['error']}")
        print("Done. Downloading artifacts…")
        download(c, job, Path(args.out))


def jobs(_args):
    with httpx.Client(base_url=API, timeout=30) as c:
        r = c.get("/api/jobs", headers=headers())
        r.raise_for_status()
        for j in r.json():
            print(f"{j['id'][:12]}  {j['status']:10s} {j['progress']:3d}%  "
                  f"{j['mode']:9s}  {j['input_filename']}")


def main():
    global API
    p = argparse.ArgumentParser(prog="v2d", description="Video to 3D Studio CLI")
    p.add_argument("--api", default=API, help="API base URL")
    sub = p.add_subparsers(dest="command", required=True)

    lp = sub.add_parser("login")
    lp.add_argument("--email", required=True)
    lp.add_argument("--password", required=True)
    lp.set_defaults(func=login)

    cp = sub.add_parser("convert")
    cp.add_argument("file", nargs="?", help="video file (omit for demo)")
    cp.add_argument("--mode", default="parallax", choices=["parallax", "mocap", "scene"])
    cp.add_argument("--width", type=int, default=720)
    cp.add_argument("--seconds", type=int, default=8)
    cp.add_argument("--out", default="./results")
    cp.add_argument("--quiet", action="store_true")
    cp.set_defaults(func=convert)

    dp = sub.add_parser("demo")
    dp.add_argument("--mode", default="parallax", choices=["parallax", "mocap", "scene"])
    dp.add_argument("--seconds", type=int, default=8)
    dp.add_argument("--out", default="./results")
    dp.add_argument("--quiet", action="store_true")
    dp.set_defaults(func=lambda a: convert(argparse.Namespace(
        file=None, mode=a.mode, width=720, seconds=a.seconds, out=a.out, quiet=a.quiet)))

    jp = sub.add_parser("jobs")
    jp.set_defaults(func=jobs)

    args = p.parse_args()
    API = args.api.rstrip("/")
    args.func(args)


if __name__ == "__main__":
    main()
