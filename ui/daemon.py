"""aria2 daemon yöneticisi — aria2c'yi RPC modunda başlatır/durdurur."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from bridge.aria2_rpc import Aria2RPC
from bridge.paths import paket_koku


class DaemonHatasi(Exception):
    """Kullanıcıya/AI'a anlaşılır biçimde iletilir (plan Review Focus #1)."""


def binary_bul() -> str:
    """tools/aria2c.exe → PATH search order; raises DaemonHatasi if not found."""
    yerel = paket_koku() / "tools" / "aria2c.exe"
    if yerel.exists():
        return str(yerel)
    yol = shutil.which("aria2c") or shutil.which("aria2c.exe")
    if yol:
        return yol
    raise DaemonHatasi(
        "aria2c not found — place tools/aria2c.exe or add to PATH "
        "(https://github.com/aria2/aria2/releases)")


class Aria2Daemon:
    def __init__(self, port: int = 6800, rpc_port: int | None = None):
        self.port = port
        self.rpc = Aria2RPC(port=port)
        self._surec: subprocess.Popen | None = None
        self._gizli_dosya = Path(os.environ.get("TEMP", ".")) / "ai-dl-bridge-aria2.log"

    def start(self) -> None:
        exe = binary_bul()
        if self.healthy():
            return  # already running
        self._surec = subprocess.Popen(
            [exe, "--enable-rpc", "--rpc-listen-all=false",
             f"--rpc-listen-port={self.port}", "--rpc-max-request-size=4M",
             "--continue=true", "--max-connection-per-server=16",
             "--split=16", "--min-split-size=1M",
             f"--log={self._gizli_dosya}", "--log-level=warn",
             "--allow-overwrite=false", "--auto-file-renaming=true"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(50):  # ~5 sec wait
            if self.healthy():
                return
            if self._surec.poll() is not None:
                raise DaemonHatasi(
                    f"aria2c failed to start (exit code {self._surec.returncode}) — "
                    f"log: {self._gizli_dosya}")
            time.sleep(0.1)
        raise DaemonHatasi("aria2c did not respond within 5 seconds")

    def healthy(self) -> bool:
        try:
            self.rpc._call("getVersion", [])
            return True
        except Exception:
            return False

    def stop(self) -> None:
        if self.healthy():
            try:
                self.rpc.shutdown()
            except Exception:
                pass
        if self._surec and self._surec.poll() is None:
            self._surec.terminate()
            try:
                self._surec.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._surec.kill()
