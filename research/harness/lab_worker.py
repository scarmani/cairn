"""Private owned-process protocol. Import targets come from trusted local code.

Callbacks must not detach, daemonize, or launch unrelated work. Process-group
cleanup does not claim containment of malicious code that violates this rule.
"""

from contextlib import redirect_stdout
import importlib
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "engine")]
from research.harness.lab_terminal_cert import canonical_json  # noqa: E402


def main():
    channel = sys.stdout
    request = json.loads(sys.stdin.readline())
    nonce = request["nonce"]
    finished = False

    def terminate(_signum, _frame):
        os._exit(0 if finished else 143)

    signal.signal(signal.SIGTERM, terminate)

    def emit(event, **data):
        channel.write(canonical_json({"event": event, "nonce": nonce, **data}) + "\n")
        channel.flush()

    emit("ready", pid=os.getpid(), pgid=os.getpgrp())
    go = json.loads(sys.stdin.readline())
    if go != {"go": nonce}:
        raise ValueError("invalid start authorization")

    def parent_lifetime():
        # The supervisor retains stdin until group cleanup. EOF is a fail-closed
        # parent-death signal, not a persistent PID-based ownership inference.
        sys.stdin.readline()
        os.killpg(os.getpgrp(), signal.SIGKILL)

    watcher = threading.Thread(target=parent_lifetime, daemon=True)
    watcher.start()
    before = canonical_json(request["task"])
    try:
        for source in request["sources"]:
            if hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("authoritative worker source changed before callback")
        with redirect_stdout(sys.stderr):
            module = importlib.import_module(request["module"])
            callback = getattr(module, request["function"])
            result = callback(request["task"])
        if canonical_json(request["task"]) != before:
            raise ValueError("callback mutated its task input")
        serialized = canonical_json(result)
        cpu = resource.getrusage(resource.RUSAGE_SELF)
        finished = True
        emit("result", result=json.loads(serialized), cpu_seconds=cpu.ru_utime + cpu.ru_stime)
    except BaseException as error:
        try:
            mutated = canonical_json(request["task"]) != before
        except ValueError:
            mutated = True
        kind = "integrity-failure" if mutated or isinstance(error, (ValueError, TypeError)) else "callback-error"
        finished = True
        emit("error", kind=kind, error={"type": type(error).__name__, "message": str(error)[:4096]})
    # Never exit/release the group leader before the owner cleans descendants.
    watcher.join()


if __name__ == "__main__":
    main()
