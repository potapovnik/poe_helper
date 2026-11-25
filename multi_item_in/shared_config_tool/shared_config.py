"""Generic JSON configuration helper for independent Python applications.

This module intentionally does not integrate with any game or automation loop.
Applications may use it for ordinary shared settings storage.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping


class SharedConfig:
    def __init__(self, path: str | Path = "config.json", defaults: Mapping[str, Any] | None = None):
        self.path = Path(path).resolve()
        self.defaults = dict(defaults or {})
        self._lock = threading.RLock()
        self.data: dict[str, Any] = {}
        self.reload()

    def reload(self) -> dict[str, Any]:
        """Reload from disk, merging saved keys over defaults."""
        with self._lock:
            loaded: dict[str, Any] = {}
            if self.path.exists():
                try:
                    parsed = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(parsed, dict):
                        loaded = parsed
                except (OSError, json.JSONDecodeError):
                    loaded = {}
            self.data = {**self.defaults, **loaded}
            if not self.path.exists():
                self.save()
            return dict(self.data)

    def get(self, key: str, fallback: Any = None) -> Any:
        with self._lock:
            return self.data.get(key, fallback)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self.data[key] = value

    def update(self, values: Mapping[str, Any]) -> None:
        with self._lock:
            self.data.update(dict(values))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self.data)

    def save(self) -> None:
        """Atomically write JSON via a temporary file + replace."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.data, ensure_ascii=False, indent=2)
            fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
                    temp_file.write(payload)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                os.replace(temp_name, self.path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
