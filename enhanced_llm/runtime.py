"""Request serialization and cooperative native-model reference caching.

The cache retains Python CLIP references only. ComfyUI's ModelPatcher remains
the sole owner of GPU residency/offloading decisions. Dropping an entry is not
an assertion that all of its GPU allocations have been freed.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable

from .native import load_native_clip


@dataclass(frozen=True)
class ModelRef:
    path: str | None = None
    clip_type: str = "auto"
    borrowed_clip: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if (self.path is None) == (self.borrowed_clip is None):
            raise ValueError("Exactly one of path or borrowed_clip is required")


@dataclass
class CacheEntry:
    clip: Any
    filename: str
    clip_type: str
    signature: tuple[Any, ...]
    loaded_at: float
    last_used_at: float
    hits: int = 0


class NativeLLMRuntime:
    """Serialize native generation; share model wrappers across workflow nodes."""

    def __init__(self, loader: Callable[[str, str], Any] | None = None, max_cached_models: int = 2):
        self._loader = loader or load_native_clip
        self._lock = threading.RLock()
        self._entries: OrderedDict[tuple[Any, ...], CacheEntry] = OrderedDict()
        self._max_cached_models = max(0, int(max_cached_models))
        self._active = False
        self._request_count = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._last_result: dict[str, Any] | None = None

    @staticmethod
    def _key(ref: ModelRef) -> tuple[Any, ...]:
        if ref.path is None:
            raise ValueError("Borrowed CLIP objects are not stored in the path cache")
        path = str(Path(ref.path).resolve(strict=True))
        info = os.stat(path)
        return (path, ref.clip_type, info.st_size, info.st_mtime_ns)

    def configure(self, max_cached_models: int) -> None:
        with self._lock:
            self._max_cached_models = max(0, min(int(max_cached_models), 16))
            self._trim()

    def _trim(self) -> None:
        while len(self._entries) > self._max_cached_models:
            self._entries.popitem(last=False)

    def _obtain(self, ref: ModelRef) -> tuple[Any, bool]:
        if ref.borrowed_clip is not None:
            return ref.borrowed_clip, True
        key = self._key(ref)

        # Drop stale checkpoint revisions of the same model.
        for existing in tuple(self._entries):
            if existing[:2] == key[:2] and existing != key:
                del self._entries[existing]

        if key in self._entries:
            entry = self._entries.pop(key)
            entry.hits += 1
            entry.last_used_at = time.time()
            self._entries[key] = entry
            self._cache_hits += 1
            return entry.clip, True

        self._cache_misses += 1
        clip = self._loader(key[0], ref.clip_type)
        now = time.time()
        self._entries[key] = CacheEntry(
            clip=clip,
            filename=Path(key[0]).name,
            clip_type=ref.clip_type,
            signature=key,
            loaded_at=now,
            last_used_at=now,
        )
        self._trim()
        return clip, False

    def run(self, ref: ModelRef, operation: Callable[[Any], Any]) -> tuple[Any, bool]:
        """The lock is held through the complete native GPU request."""
        with self._lock:
            self._active = True
            try:
                clip, reused = self._obtain(ref)
                result = operation(clip)
                self._request_count += 1
                return result, reused
            finally:
                self._active = False

    def remember(self, result: dict[str, Any]) -> None:
        with self._lock:
            self._last_result = dict(result)

    def release(self, ref: ModelRef | None = None) -> int:
        """Release owned Python cache references, never invalidate borrowed CLIP."""
        with self._lock:
            if ref is None:
                count = len(self._entries)
                self._entries.clear()
                return count
            if ref.path is None:
                return 0
            resolved = str(Path(ref.path).resolve(strict=False))
            keys = [k for k in self._entries if k[0] == resolved and k[1] == ref.clip_type]
            for key in keys:
                del self._entries[key]
            return len(keys)

    def status(self) -> dict[str, Any]:
        """No device-memory queries here: can deadlock dynamic VRAM paging."""
        with self._lock:
            return {
                "engine": "comfy_native",
                "active_request": self._active,
                "completed_requests": self._request_count,
                "cached_model_count": len(self._entries),
                "cache_capacity": self._max_cached_models,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "models": [
                    {
                        "filename": e.filename,
                        "clip_type": e.clip_type,
                        "reference_hits": e.hits,
                        "loaded_at": e.loaded_at,
                        "last_used_at": e.last_used_at,
                    }
                    for e in self._entries.values()
                ],
                "last_generation": self._last_result,
                "gpu_memory_owner": "ComfyUI ModelPatcher",
                "persistent_kv_cache": "not_implemented",
            }


RUNTIME = NativeLLMRuntime()
