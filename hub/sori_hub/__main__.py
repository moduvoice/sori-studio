"""명령줄: python -m sori_hub serve [--port 5150] / doctor

- 한 컴퓨터에 허브는 하나(4.8): 홈의 hub.json 에 pid·포트를 적고, 이미 켜진 허브가 답하면 그쪽을 알려 주고 끝나요.
- 포트가 다른 프로그램에 쓰이고 있으면 다음 빈 포트를 써요(v0.4, 기본 5150).
"""
import argparse
import json
import os
import socket
import sys
import urllib.request

from . import catalog, hardware, paths


def _hub_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/hub/health",
                                                           headers={"Host": f"127.0.0.1:{port}"}), timeout=2) as r:
            return json.loads(r.read()).get("app") == "sori-studio-hub"
    except Exception:
        return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name != "nt":
            # 방금 끈 허브의 연결이 TIME_WAIT 로 남아도 다시 쓸 수 있게(uvicorn 도 같은 설정). Windows 는 뜻이 달라 쓰지 않아요.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def serve(port: int) -> int:
    import uvicorn

    from .server import create_app

    lock = paths.home() / "hub.json"
    if lock.exists():
        try:
            old = json.loads(lock.read_text(encoding="utf-8"))
            if _hub_alive(int(old["port"])):
                print(f"SORI_ALREADY_RUNNING 이미 허브가 켜져 있어요: http://127.0.0.1:{old['port']} (pid {old.get('pid')})")
                return 0
        except (ValueError, KeyError):
            pass
    p = port
    while not _port_free(p):
        p += 1
        if p > port + 50:
            print("SORI_NO_PORT 빈 포트를 찾지 못했어요", file=sys.stderr)
            return 2
    paths.write_json(lock, {"pid": os.getpid(), "port": p})
    print(f"Sori Studio 허브: http://127.0.0.1:{p}  (토큰 파일 {paths.home() / 'hub-token'})", flush=True)
    try:
        uvicorn.run(create_app(p), host="127.0.0.1", port=p, log_level="warning")
    finally:
        try:
            if json.loads(lock.read_text(encoding="utf-8")).get("pid") == os.getpid():
                lock.unlink()
        except Exception:
            pass
    return 0


def doctor() -> int:
    hw = hardware.detect()
    print(json.dumps(hw, ensure_ascii=False, indent=2))
    for eid, r in catalog.load_all().items():
        print(f"{eid}: {hardware.verdict(r, hw)}")
    return 0


def main() -> int:
    # 영어판 Windows 콘솔(cp1252)에서도 한국어 출력이 죽지 않게(스팟 시험 2026-11-17)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="sori_hub")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=5150)
    sub.add_parser("doctor")
    a = ap.parse_args()
    return serve(a.port) if a.cmd == "serve" else doctor()


if __name__ == "__main__":
    sys.exit(main())
