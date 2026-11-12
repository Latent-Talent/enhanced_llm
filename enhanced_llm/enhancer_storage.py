"""Saved enhancer templates and prompt sets, separate from workflow-embedded state."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .enhancer_core import DEFAULT_INSTRUCTIONS, dumps_history, normalize_index, parse_history

PACKAGE_TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "default"
NAME_RE = re.compile(r"^[\w .()\-]{1,80}$", re.UNICODE)
MAX_TEXT_SIZE = 64_000


def user_root() -> Path:
    import folder_paths
    return Path(folder_paths.get_user_directory()) / "enhanced_llm" / "prompt_enhancer"


def validate_name(name: Any) -> str:
    clean = str(name or "").strip()
    if clean in (".", "..") or not NAME_RE.fullmatch(clean):
        raise ValueError("Name must be 1–80 characters (letters, numbers, spaces, . _ - ()).")
    return clean


def templates() -> list[dict[str, Any]]:
    records = [{"label": "Custom", "name": "Custom", "protected": True, "text": DEFAULT_INSTRUCTIONS}]
    for path in sorted(PACKAGE_TEMPLATES.glob("*.txt"), key=lambda p: p.name.casefold()):
        records.append({"label": f"Default / {path.stem}", "name": path.stem,
                        "protected": True, "text": path.read_text(encoding="utf-8")})
    dest = user_root() / "templates"
    if dest.is_dir():
        for path in sorted(dest.glob("*.txt"), key=lambda p: p.name.casefold()):
            records.append({"label": f"User / {path.stem}", "name": path.stem,
                            "protected": False, "text": path.read_text(encoding="utf-8")})
    return records


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".enhanced-llm-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_template(name: str, instructions: str) -> dict[str, Any]:
    name = validate_name(name)
    text = str(instructions or "").strip()
    if not text or len(text) > MAX_TEXT_SIZE:
        raise ValueError("Template must contain 1–64000 characters.")
    path = user_root() / "templates" / f"{name}.txt"
    _atomic_write(path, text)
    return {"label": f"User / {name}", "name": name, "protected": False, "text": text}


def remove_template(label: str) -> None:
    if not str(label).startswith("User / "):
        raise ValueError("Only user templates may be deleted.")
    name = validate_name(label[len("User / "):])
    (user_root() / "templates" / f"{name}.txt").unlink()


def prompt_sets() -> list[str]:
    dest = user_root() / "prompt_sets"
    if not dest.is_dir():
        return []
    return [p.stem for p in sorted(dest.glob("*.json"), key=lambda p: p.name.casefold())]


def save_prompt_set(name: str, prompts: list[str], active_index: int) -> dict[str, Any]:
    name = validate_name(name)
    parsed = parse_history(prompts)
    payload = {"version": 1, "prompts": parsed, "active_index": normalize_index(active_index, len(parsed))}
    _atomic_write(user_root() / "prompt_sets" / f"{name}.json",
                  json.dumps(payload, ensure_ascii=False, indent=2))
    return {"name": name, **payload}


def load_prompt_set(name: str) -> dict[str, Any]:
    name = validate_name(name)
    path = user_root() / "prompt_sets" / f"{name}.json"
    if path.stat().st_size > 2_000_000:
        raise ValueError("Prompt Set exceeds maximum supported size")
    record = json.loads(path.read_text(encoding="utf-8"))
    prompts = parse_history(record.get("prompts"))
    index = normalize_index(record.get("active_index", 0), len(prompts))
    return {"name": name, "prompts": prompts, "active_index": index,
            "history_json": dumps_history(prompts)}


def remove_prompt_set(name: str) -> None:
    name = validate_name(name)
    (user_root() / "prompt_sets" / f"{name}.json").unlink()
