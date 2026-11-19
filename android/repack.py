"""Repackage: add extra files to a base APK using the standard zip library."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


def repack(base_apk: Path, out_apk: Path, extra: dict[str, Path], align: int = 4) -> None:
    """Copy base APK and add extra files. zipfile produces a standard ZIP."""
    shutil.copyfile(base_apk, out_apk)
    with zipfile.ZipFile(out_apk, "a", zipfile.ZIP_DEFLATED) as z:
        for name, path in extra.items():
            z.write(path, name)
