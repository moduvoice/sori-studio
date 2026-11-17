"""레시피용 가중치 목록 만들기 - HF 저장소의 판(커밋)을 고정하고 파일마다 크기·sha256 을 적어요.

  python etc/hf_weights.py Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice [--rev main] [--dir customvoice] [--skip '*.md,*.png']
LFS 파일은 HF 가 주는 sha256 을, 작은 일반 파일은 받아서 직접 계산해요. 결과는 recipe.yaml 의 weights 항목(YAML)으로 찍어요.
"""
import argparse
import fnmatch
import hashlib
import json
import urllib.request

UA = {"User-Agent": "sori-studio-recipe-tool"}
SKIP = ["*.md", ".gitattributes", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.mp4", "*.wav", "*.mp3", "*.pdf", "LICENSE*", "*.ipynb"]


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--rev", default="main")
    ap.add_argument("--dir", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--only", default="", help="이 꼴만(쉼표로)")
    a = ap.parse_args()
    d = json.loads(get(f"https://huggingface.co/api/models/{a.repo}/revision/{a.rev}?blobs=true"))
    sha = d["sha"]
    skip = SKIP + [x for x in a.skip.split(",") if x]
    only = [x for x in a.only.split(",") if x]
    files = []
    for s in d["siblings"]:
        p = s["rfilename"]
        if only and not any(fnmatch.fnmatch(p, o) for o in only):
            continue
        if not only and any(fnmatch.fnmatch(p.split("/")[-1], k) or fnmatch.fnmatch(p, k) for k in skip):
            continue
        lfs = s.get("lfs") or {}
        if lfs.get("sha256"):
            h, size = lfs["sha256"], s["size"]
        else:
            b = get(f"https://huggingface.co/{a.repo}/resolve/{sha}/{p}")
            h, size = hashlib.sha256(b).hexdigest(), len(b)
        files.append((p, size, h))
    lic = (d.get("cardData") or {}).get("license")
    print(f"# {a.repo} @ {sha[:7]} · 파일 {len(files)}개 · {sum(f[1] for f in files) / 1e9:.2f} GB · 카드 라이선스 {lic}")
    print(f"  - dir: {a.dir or a.repo.split('/')[-1].lower()}")
    print(f"    sources: [{{repo: {a.repo}, revision: {sha}}}]")
    print("    files:")
    for p, size, h in files:
        print(f"      - {{path: {p}, size: {size}, sha256: {h}}}")


if __name__ == "__main__":
    main()
