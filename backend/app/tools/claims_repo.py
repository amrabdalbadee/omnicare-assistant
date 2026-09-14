"""Persistence layer for the JSON claims store.

The assessment uses a JSON file as the system of record, which has two sharp
edges worth handling explicitly rather than pretending they do not exist:

1. Concurrent writers can interleave a read-modify-write and lose a claim.
   Every mutation therefore takes an exclusive advisory lock on a sidecar
   lock file for the whole read-modify-write cycle.
2. A crash mid-write can truncate the file. Writes go to a temporary file in
   the same directory and are moved into place with ``os.replace``, which is
   atomic on POSIX, so the file is never observed half-written.
"""

from __future__ import annotations

import fcntl
import json
import os
import random
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.models.claim import Claim


class ClaimsRepositoryError(RuntimeError):
    """Raised when the claims store cannot be read or written."""


class ClaimsRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    # --- locking ----------------------------------------------------------

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    # --- reads ------------------------------------------------------------

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        except json.JSONDecodeError as exc:
            raise ClaimsRepositoryError(
                f"Claims store at {self.path} is not valid JSON: {exc}"
            ) from exc
        if not isinstance(raw, list):
            raise ClaimsRepositoryError(
                f"Claims store at {self.path} must contain a JSON array."
            )
        return raw

    def get(self, claim_id: str) -> dict[str, Any] | None:
        target = claim_id.strip().upper()
        for record in self.load():
            if str(record.get("claim_id", "")).upper() == target:
                return record
        return None

    # --- writes -----------------------------------------------------------

    def _atomic_write(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".claims-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(records, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def _allocate_claim_id(self, existing: list[dict[str, Any]]) -> str:
        taken = {str(record.get("claim_id", "")).upper() for record in existing}
        for _ in range(100):
            candidate = f"CLM-{random.randint(1000, 9999)}"
            if candidate not in taken:
                return candidate
        raise ClaimsRepositoryError("Could not allocate a unique claim id.")

    def append(self, claim: Claim, *, claim_id: str | None = None) -> Claim:
        """Append a claim, assigning an id if one was not supplied.

        The entire read-modify-write runs under the lock so two concurrent
        submissions cannot be handed the same id or clobber each other.
        """
        with self._exclusive_lock():
            records = self.load()
            record = claim.model_dump(exclude_none=True)
            record["claim_id"] = claim_id or self._allocate_claim_id(records)
            records.append(record)
            self._atomic_write(records)
        return Claim(**record)
