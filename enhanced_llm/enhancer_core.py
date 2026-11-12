"""Pure prompt-enhancer state logic, with no ComfyUI or GPU imports."""

from __future__ import annotations

import hashlib
import json
import random
import re
from typing import Any

CYCLE_MODES = ("fixed", "increment", "decrement", "shuffle", "random")
MAX_HISTORY = 512
MAX_BATCH = 64
DEFAULT_INSTRUCTIONS = (
    "You are an expert image and video generation prompt editor. Expand the user's "
    "source prompt into a clear, detailed, production-ready prompt. Preserve all "
    "specified subjects, actions, constraints, and intent. Add useful visual, "
    "spatial, lighting, camera, and motion details only where appropriate. "
    "Return ONLY the enhanced prompt with no commentary, formatting or preface."
)


def parse_history(raw: str | list[str] | None) -> list[str]:
    if raw is None or raw == "":
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError) as exc:
        raise ValueError("Enhanced prompt history must be a JSON array of strings") from exc
    if not isinstance(data, list) or len(data) > MAX_HISTORY or any(not isinstance(x, str) for x in data):
        raise ValueError(f"Enhanced prompt history must contain at most {MAX_HISTORY} strings")
    return list(data)


def dumps_history(prompts: list[str]) -> str:
    return json.dumps(prompts, ensure_ascii=False)


def normalize_index(index: Any, length: int) -> int:
    if length <= 0:
        return 0
    try:
        return min(max(int(index), 0), length - 1)
    except (ValueError, TypeError, OverflowError):
        return 0


def _stable_rng(seed: int, epoch: int) -> random.Random:
    digest = hashlib.sha256(f"enhanced-llm-cycle:{seed}:{epoch}".encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _shuffle_deck(length: int, seed: int, epoch: int) -> list[int]:
    deck = list(range(length))
    _stable_rng(seed, epoch).shuffle(deck)
    if epoch > 0 and length > 1:
        prev = list(range(length))
        _stable_rng(seed, epoch - 1).shuffle(prev)
        if deck[0] == prev[-1]:
            i = next(i for i in range(1, length) if deck[i] != prev[-1])
            deck[0], deck[i] = deck[i], deck[0]
    return deck


def select_index(mode: str, active_index: int, length: int, counter: int = 0, seed: int = 0) -> int:
    if mode not in CYCLE_MODES:
        raise ValueError(f"Unknown prompt cycle mode: {mode}")
    if length < 1:
        return 0
    active = normalize_index(active_index, length)
    if mode == "fixed":
        return active
    if mode == "increment":
        return (active + int(counter)) % length
    if mode == "decrement":
        return (active - int(counter)) % length
    if mode == "shuffle":
        epoch, pos = divmod(int(counter), length)
        return _shuffle_deck(length, int(seed), epoch)[pos]
    return _stable_rng(int(seed), int(counter)).randrange(length)


def apply_generated(
    history: list[str], active_index: int, generated: list[str], overwrite: bool
) -> tuple[list[str], int]:
    result = list(history)
    if not generated:
        return result, normalize_index(active_index, len(result))
    if len(generated) > MAX_BATCH or any(not isinstance(x, str) or not x.strip() for x in generated):
        raise ValueError("Generated prompts must contain between 1 and 64 nonempty strings")
    if overwrite and len(generated) == 1 and result:
        target = normalize_index(active_index, len(result))
        result[target] = generated[0]
        return result, target
    result.extend(generated)
    if len(result) > MAX_HISTORY:
        result = result[-MAX_HISTORY:]
    return result, len(result) - 1


def clean_generated(text: str) -> str:
    result = (text or "").strip()
    fence = chr(96) * 3
    fenced = re.fullmatch(re.escape(fence) + r"(?:text|markdown)?\s*\n([\s\S]*?)\n?" + re.escape(fence), result, re.I)
    if fenced:
        result = fenced.group(1).strip()
    result = re.sub(r"^(?:enhanced|revised)\s+prompt\s*:\s*", "", result, flags=re.I)
    if not result:
        raise ValueError("The native LLM returned an empty enhanced prompt")
    return result


def enhancement_system_prompt(instructions: str) -> str:
    return (
        "You enhance prompts for other generative AI models. Follow these instructions. "
        "Return the requested enhanced prompt only.\n\n"
        + (instructions.strip() or DEFAULT_INSTRUCTIONS)
    )
