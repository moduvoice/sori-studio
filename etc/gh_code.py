"""레시피용 소스 코드 항목 만들기 - GitHub 저장소의 커밋을 고정하고 묶음(zip)의 크기·sha256 을 적어요.

  python etc/gh_code.py netease-youdao/Confucius4-TTS [--ref main] [--dir confucius4] [--save tmp/src]
"""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

UA = {"User-Agent": "sori-studio-recipe-tool", "Accept": "application/vnd.github+json"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--dir")
    ap.add_argument("--save", help="풀어서 볼 폴더(requirements 읽기용)")
    a = ap.parse_args()
    c = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"https://api.github.com/repos/{a.repo}/commits/{a.ref}", headers=UA), timeout=60).read())
    sha = c["sha"]
    url = f"https://codeload.github.com/{a.repo}/zip/{sha}"
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()
    h = hashlib.sha256(data).hexdigest()
    d = a.dir or a.repo.split("/")[1].lower()
    print(f"# {a.repo} @ {sha[:7]} ({c['commit']['committer']['date'][:10]}) · {len(data) / 1e6:.1f} MB")
    print(f"  - {{url: \"{url}\", sha256: {h}, size: {len(data)}, dir: {d}}}")
    if a.save:
        import io
        import zipfile

        z = zipfile.ZipFile(io.BytesIO(data))
        out = Path(a.save) / d
        z.extractall(out)


if __name__ == "__main__":
    main()
