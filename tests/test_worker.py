import os
import subprocess
import sys
import time
from pathlib import Path

from tests.conftest import settings_values

ROOT = Path(__file__).resolve().parents[1]


def worker_env() -> dict[str, str]:
    env = dict(os.environ)
    env |= {name.upper(): value for name, value in settings_values().items()}
    return env


def start_worker() -> subprocess.Popen:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    return subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        env=worker_env(),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=flags,
    )


def stop_worker(process: subprocess.Popen) -> None:
    if sys.platform == "win32":
        import signal

        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.terminate()


def test_worker_stays_up_and_stops_cleanly():
    process = start_worker()
    try:
        time.sleep(3)
        assert process.poll() is None, process.stdout.read()
        stop_worker(process)
        output, _ = process.communicate(timeout=15)
    finally:
        if process.poll() is None:
            process.kill()

    assert process.returncode == 0
    assert "worker started" in output
    assert "worker stopped" in output
