"""Launch the cross-platform Streamlit app using the current Python interpreter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Run the Streamlit browser app from the project root."""
    project_root = Path(__file__).resolve().parents[1]
    app_path = project_root / "streamlit_app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    completed = subprocess.run(command, cwd=project_root, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
