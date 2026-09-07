"""Short synthetic supervised callbacks. Never import a game or proof runner."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def synthetic_callback(task):
    payload = task["payload"]
    mode = payload.get("mode", "value")
    if "pid_file" in payload:
        Path(payload["pid_file"]).write_text(str(os.getpid()))
    if mode == "error":
        raise RuntimeError("synthetic callback negative evidence")
    if mode == "mutate":
        payload["mutated"] = True
    if mode == "nan":
        return float("nan")
    if mode == "exit":
        os._exit(7)
    if mode == "source":
        Path(payload["source_file"]).write_text("changed during callback")
    if mode == "descendant":
        child = subprocess.Popen([sys.executable, "-c",
            "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);\nwhile True: time.sleep(.01)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Path(payload["child_file"]).write_text(str(child.pid))
    if mode in ("hang", "descendant"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            time.sleep(.01)
    time.sleep(payload.get("delay", 0))
    return {"id": task["id"], "value": payload.get("value", 0)}
