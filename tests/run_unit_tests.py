"""Run unit tests without importing the plugin entrypoint or installing ComfyUI."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(prefix="enhanced-llm-tests-") as tmp:
    dest = Path(tmp)
    (dest / "tests").mkdir()
    for filename in ("nodes.py", "queue_service.py"):
        shutil.copy2(ROOT / filename, dest / filename)
    for source in (ROOT / "tests").glob("test_*.py"):
        shutil.copy2(source, dest / "tests" / source.name)
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=dest))
