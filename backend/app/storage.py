"""Filesystem storage for uploads and derived files.

Files live under ``settings.data_dir`` which is never mounted as a static
directory. Every path handed out by this module is resolved and checked to be
inside the storage root, so a crafted id cannot escape it.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import BinaryIO

_SAFE_ID = re.compile(r"^[a-z]+_[0-9a-f]{20}$")


class StorageError(Exception):
    pass


class UploadTooLarge(StorageError):
    pass


class Storage:
    def __init__(self, uploads_dir: Path, derived_dir: Path):
        self.uploads_dir = Path(uploads_dir).resolve()
        self.derived_dir = Path(derived_dir).resolve()
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.derived_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _check_id(item_id: str) -> str:
        if not _SAFE_ID.match(item_id):
            raise StorageError("invalid id")
        return item_id

    @staticmethod
    def _inside(root: Path, path: Path) -> Path:
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            raise StorageError("path escapes storage root")
        return resolved

    def upload_path(self, item_id: str, suffix: str) -> Path:
        self._check_id(item_id)
        suffix = suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,5}", suffix):
            raise StorageError("invalid suffix")
        return self._inside(self.uploads_dir, self.uploads_dir / f"{item_id}{suffix}")

    def derived(self, item_id: str, *parts: str) -> Path:
        self._check_id(item_id)
        for part in parts:
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", part) or part in (".", ".."):
                raise StorageError("invalid path part")
        path = self._inside(self.derived_dir, self.derived_dir.joinpath(item_id, *parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def derived_root(self, item_id: str) -> Path:
        self._check_id(item_id)
        return self._inside(self.derived_dir, self.derived_dir / item_id)

    def save_stream(self, src: BinaryIO, dest: Path, max_bytes: int) -> tuple[int, str]:
        """Copy a stream to ``dest`` enforcing ``max_bytes``. Returns (size, sha256)."""
        h = hashlib.sha256()
        size = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with open(tmp, "wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLarge(f"file exceeds {max_bytes // (1024 * 1024)} MB")
                    h.update(chunk)
                    out.write(chunk)
            tmp.replace(dest)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return size, h.hexdigest()

    def delete_item(self, item_id: str) -> None:
        self._check_id(item_id)
        for p in self.uploads_dir.glob(f"{item_id}.*"):
            self._inside(self.uploads_dir, p).unlink(missing_ok=True)
        root = self.derived_root(item_id)
        if root.exists():
            shutil.rmtree(root)

    def find_upload(self, item_id: str) -> Path | None:
        self._check_id(item_id)
        for p in self.uploads_dir.glob(f"{item_id}.*"):
            if not p.name.endswith(".part"):
                return self._inside(self.uploads_dir, p)
        return None
