"""Outbound notifications.

Self-hosted builds log messages to a local outbox file. Plug an SMTP/email
provider into `send_email` for a hosted deployment.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config import settings

log = logging.getLogger("v2d.email")


def send_email(to: str, subject: str, body: str) -> None:
    outbox = settings.data_dir / "outbox.log"
    with open(outbox, "a") as f:
        f.write(f"---\nto: {to}\nsubject: {subject}\n\n{body}\n")
    log.info("email_queued", extra={"to": to, "subject": subject})
