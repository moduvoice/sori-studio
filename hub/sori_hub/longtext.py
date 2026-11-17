"""긴 글은 문장 경계에서 엔진 한도(max_chars) 안으로 나눠 만든 뒤 이어 붙여요(기능 설계 5.3, 리뷰 2026-11-17).

wav 는 일꾼이 주는 16비트 모노 그대로 이어 붙이고, 조각 사이에 쉼(기본 0.25초)을 넣어요.
"""
import io
import re
import wave



def split(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    parts = [p.strip() for p in re.split(r"(?<=[.!?…。！？])\s+|\n+", text) if p.strip()]
    out: list[str] = []
    cur = ""
    for p in parts:
        while len(p) > max_chars:  # 한 문장이 한도보다 길면 쉼표·띄어쓰기에서 자름
            cut = max(p.rfind(",", 0, max_chars), p.rfind(" ", 0, max_chars))
            cut = cut if cut > max_chars // 3 else max_chars - 1
            head, p = p[: cut + 1].strip(), p[cut + 1 :].strip()
            if cur:
                out.append(cur)
                cur = ""
            out.append(head)
        if cur and len(cur) + 1 + len(p) > max_chars:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    return out


def join_wavs(wavs: list[bytes], gap_s: float = 0.25) -> bytes:
    frames, params = [], None
    for b in wavs:
        with wave.open(io.BytesIO(b)) as w:
            if params is None:
                params = w.getparams()
            frames.append(w.readframes(w.getnframes()))
    if params is None:
        return b""
    silence = b"\x00" * int(params.framerate * gap_s) * params.sampwidth * params.nchannels
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(silence.join(frames))
    return buf.getvalue()
