"""멈출 수 있는 하위 프로세스 실행 - 설치 중 [멈춤]이 패키지 단계(수 GB 받기)에서도 듣게(리뷰 2026-11-17).

지금 스레드의 멈춤 신호(set_cancel)를 0.5초마다 보고, 멈추면 프로세스 묶음째 끝내요
(Windows = taskkill /T, 그 밖 = 프로세스 그룹).
"""
import os
import signal
import subprocess
import threading
import time

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ctx = threading.local()


class Cancelled(Exception):
    pass


def set_cancel(ev: threading.Event | None) -> None:
    _ctx.cancel = ev


def _cancel_event() -> threading.Event | None:
    return getattr(_ctx, "cancel", None)


def _kill_tree(p: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=NO_WINDOW)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        p.wait(10)
    except Exception:
        pass


def run(cmd: list[str], env: dict | None = None, timeout: float | None = None, input_bytes: bytes | None = None) -> tuple[int, bytes]:
    """(종료 코드, stdout+stderr 바이트). 멈춤 신호가 오면 Cancelled, 시간 초과면 코드 124."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE if input_bytes else subprocess.DEVNULL,
                         env=env, creationflags=NO_WINDOW, start_new_session=(os.name != "nt"))
    chunks: list[bytes] = []
    reader = threading.Thread(target=lambda: chunks.append(p.stdout.read()), daemon=True)
    reader.start()
    if input_bytes:
        try:
            p.stdin.write(input_bytes)
            p.stdin.close()
        except OSError:
            pass
    t0 = time.time()
    ev = _cancel_event()
    while p.poll() is None:
        if ev is not None and ev.is_set():
            _kill_tree(p)
            raise Cancelled()
        if timeout and time.time() - t0 > timeout:
            _kill_tree(p)
            reader.join(5)
            return 124, b"".join(chunks) + "시간 초과".encode()
        time.sleep(0.5)
    reader.join(10)
    return p.returncode, b"".join(chunks)
