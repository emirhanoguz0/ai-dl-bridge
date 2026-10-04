"""Backward-compatibility stub forwarding to grab_history.py."""
import runpy
from pathlib import Path

target = Path(__file__).parent / "grab_history.py"
runpy.run_path(str(target), run_name="__main__")
