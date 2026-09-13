"""External LaunchAgent controls used by the native server settings panel."""

import json
import fcntl
from contextlib import contextmanager
import os
import plistlib
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

LABEL = "com.ap.cx.glyphs-mcp-sidecar"


class ServerControl:
    def __init__(self, home=None):
        self.home = Path(home or Path.home())
        self.agent = self.home / "Library/LaunchAgents" / (LABEL + ".plist")
        self.domain = "gui/" + str(os.getuid())
        self.support = self.home / "Library/Application Support/Glyphs MCP"

    @contextmanager
    def exclusive(self):
        self.support.mkdir(parents=True, exist_ok=True)
        with (self.support / ".control.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("Another service control or installation is already running.") from error
            yield

    def _management(self, port, action, **values):
        configured = self._plist().get("EnvironmentVariables", {}).get("GLYPHS_MCP_BRIDGE_TOKEN_FILE")
        token_path = Path(configured).expanduser() if configured else self.support / "bridge-token"
        token = token_path.read_text(encoding="ascii").strip()
        request = Request("http://127.0.0.1:{}/internal/control".format(port),
            data=json.dumps({"action": action, **values}).encode(),
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=5) as response:
                result = json.load(response)
        except HTTPError as error:
            if error.code == 404:
                raise RuntimeError("Update the installed components to enable safe desktop controls.") from error
            result = json.loads(error.read())
        if not result.get("ok"):
            raise RuntimeError((result.get("error") or {}).get("message", "Service control was refused."))
        return result["data"]

    @contextmanager
    def idle(self, state):
        lease = self._management(state["port"], "reserve") if state["processRunning"] else None
        try:
            if lease and lease.get("processId") != state["processId"]:
                raise RuntimeError("The listener does not belong to the managed sidecar process. No process was stopped.")
            yield
        finally:
            if lease:
                try:
                    self._management(state["port"], "release", reservationId=lease["reservationId"])
                except Exception:
                    # A stopped process cannot reply. A surviving process expires
                    # abandoned leases after 30 seconds, without replaying work.
                    pass

    def _launchctl(self, *args):
        return subprocess.run(["/bin/launchctl", *args], capture_output=True, text=True, timeout=10)

    def _plist(self):
        if not self.agent.is_file():
            raise RuntimeError("The MCP sidecar is not installed. Run the Glyphs MCP installer first.")
        return plistlib.loads(self.agent.read_bytes())

    def _write(self, settings):
        temporary = self.agent.with_suffix(".plist.tmp")
        temporary.write_bytes(plistlib.dumps(settings, sort_keys=True))
        temporary.replace(self.agent)

    def set_port(self, value):
        if not isinstance(value, str) or not value.isascii() or not value.isdigit() or not 1024 <= int(value) <= 65535:
            raise ValueError("Enter a port number from 1024 to 65535.")
        port = int(value)
        settings = self._plist()
        args = list(settings.get("ProgramArguments", []))
        bridge = args[args.index("--bridge") + 1] if "--bridge" in args else "http://127.0.0.1:9681"
        if port == urlparse(bridge).port:
            raise ValueError("That port is reserved for the Glyphs connection. Choose another port.")
        state = self.status()
        if port == state["port"]:
            return state
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                # Match the HTTP listener: closed connections in TIME_WAIT do
                # not occupy a port, while a live listener still blocks bind.
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(("127.0.0.1", port))
        except OSError as error:
            raise ValueError("Port {} is already in use. Choose another port.".format(port)) from error
        if "--port" in args:
            args[args.index("--port") + 1] = str(port)
        else:
            args.extend(["--port", str(port)])
        if state["loaded"]:
            self._run("stop")
        try:
            self._write({**settings, "ProgramArguments": args})
            return self._run("start") if state["running"] else self.status()
        except Exception:
            # Restore the previous configuration if a restart cannot bind.
            self._run("stop")
            self._write(settings)
            if state["running"]:
                self._run("start")
            raise

    def status(self):
        settings = self._plist()
        args = settings.get("ProgramArguments", [])
        port = int(args[args.index("--port") + 1]) if "--port" in args else 9680
        process = self._launchctl("print", self.domain + "/" + LABEL)
        loaded = process.returncode == 0
        match = re.search(r"(?m)^\s*pid = (\d+)", process.stdout) if loaded else None
        process_id = int(match[1]) if match else None
        running = process_id is not None
        listening = False
        if running:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    listening = True
            except OSError:
                pass
        return {"running": bool(running and listening), "processRunning": bool(running), "processId": process_id, "loaded": loaded, "port": port,
                "autoStart": bool(settings.get("RunAtLoad", False)),
                "url": "http://127.0.0.1:{}/mcp/".format(port)}

    def run(self, action, value=None):
        if action == "status":
            return self.status()
        with self.exclusive():
            return self._run(action, value)

    def _run(self, action, value=None):
        if action == "port":
            return self.set_port(value)
        if action in ("auto-on", "auto-off"):
            settings = self._plist()
            settings["RunAtLoad"] = settings["KeepAlive"] = action == "auto-on"
            self._write(settings)
            return self.status()
        state = self.status()
        if action == "start":
            if state["running"]:
                return state
            if state["loaded"]:
                result = self._launchctl("kickstart", self.domain + "/" + LABEL)
            else:
                result = self._launchctl("bootstrap", self.domain, str(self.agent))
                if result.returncode == 0 and not state["autoStart"]:
                    result = self._launchctl("kickstart", self.domain + "/" + LABEL)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "The MCP server could not start")
        elif action == "stop":
            if state["loaded"]:
                with self.idle(state):
                    result = self._launchctl("bootout", self.domain + "/" + LABEL)
                    if result.returncode:
                        raise RuntimeError(result.stderr.strip() or "The MCP server could not stop")
        else:
            raise ValueError("Unknown server control action")
        for _ in range(50):
            state = self.status()
            if (state["running"] if action == "start" else not state["loaded"]):
                return state
            time.sleep(.1)
        raise RuntimeError("The server did not {}. Check the server logs.".format(action))


def main():
    try:
        result = {"ok": True, "data": ServerControl().run(sys.argv[1] if len(sys.argv) > 1 else "status", sys.argv[2] if len(sys.argv) > 2 else None)}
    except Exception as error:
        result = {"ok": False, "error": str(error) or type(error).__name__}
    print(json.dumps(result))
    return 0 if result["ok"] else 1
