"""aria2 JSON-RPC istemcisi (saf stdlib — bağımlılıksız, testi kolay)."""
from __future__ import annotations

import json
import urllib.request


class Aria2Error(Exception):
    pass


class Aria2RPC:
    def __init__(self, port: int = 6800, token: str | None = None):
        self.url = f"http://127.0.0.1:{port}/jsonrpc"
        self._id = 0
        self._token = token

    def _call(self, method: str, params: list) -> dict:
        self._id += 1
        if self._token:
            params = [f"token:{self._token}"] + params
        payload = json.dumps({
            "jsonrpc": "2.0", "id": self._id, "method": f"aria2.{method}", "params": params,
        }).encode()
        req = urllib.request.Request(self.url, data=payload,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read())
        except Exception as e:
            raise Aria2Error(f"aria2'ye ulaşılamadı: {e}") from e
        if "error" in resp:
            raise Aria2Error(f"aria2 hatası {resp['error'].get('code')}: "
                             f"{resp['error'].get('message')}")
        return resp["result"]

    def add_uri(self, link: str, out_dir: str, out_name: str | None = None,
                paused: bool = False, secenekler: dict | None = None) -> str:
        opts = {"dir": out_dir}
        if out_name:
            opts["out"] = out_name
        if paused:
            opts["pause"] = "true"
        if secenekler:
            opts.update(secenekler)
        return self._call("addUri", [[link], opts])

    def tell_status(self, gid: str) -> dict:
        return self._call("tellStatus", [gid,
                        ["gid", "status", "totalLength", "completedLength",
                         "downloadSpeed", "bittorrent", "files"]])

    def tell_active(self) -> list:
        return self._call("tellActive", [["gid", "status", "totalLength",
                         "completedLength", "downloadSpeed", "files"]])

    def tell_waiting(self, offset: int = 0, num: int = 100) -> list:
        return self._call("tellWaiting", [offset, num,
                         ["gid", "status", "totalLength", "completedLength",
                          "downloadSpeed", "files"]])

    def tell_stopped(self, offset: int = 0, num: int = 100) -> list:
        """Kuyruktan düşmüş (tamamlanan/hata/iptal) sonuçları döner."""
        return self._call("tellStopped", [offset, num,
                         ["gid", "status", "totalLength", "completedLength",
                          "downloadSpeed", "files"]])

    def pause(self, gid: str) -> str:
        return self._call("pause", [gid])

    def unpause(self, gid: str) -> str:
        return self._call("unpause", [gid])

    def remove(self, gid: str) -> str:
        return self._call("remove", [gid])

    def remove_download_result(self, gid: str) -> str:
        """Biten/hata ile biten görevi kuyruk sonuçlarından da kaldırır."""
        return self._call("removeDownloadResult", [gid])

    def set_speed_limit(self, bytes_per_sec: int) -> str:
        # 0 = sınırsız
        return self._call("changeGlobalOption", [{"max-overall-download-limit":
                                                  str(bytes_per_sec)}])

    def shutdown(self) -> str:
        return self._call("shutdown", [])
