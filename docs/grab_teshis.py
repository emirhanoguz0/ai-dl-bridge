"""Backward-compatibility stub forwarding to grab_diagnostics.py."""
import runpy
from pathlib import Path

target = Path(__file__).parent / "grab_diagnostics.py"
runpy.run_path(str(target), run_name="__main__")
