"""SGLang-Omni 서버형 엔진 레시피 만들기(Fish Drama-3 int4 · ZONOS3-Mini · CosyVoice3). 한 번 돌려 engines/<id>/ 에 써요.
가중치 목록은 etc/hf_weights.py 결과(tmp/w-<dir>.yaml). 측정·사람 평가는 oh-my-tts 벤치(2026-11-16).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = '  - {url: "https://codeload.github.com/sgl-project/sglang-omni/zip/eeaf0390f5bcd4cd335217622db253df03c7fc7a", sha256: 6b56a9193c77619b84cde0a27bdc83c79d7e62b03dfe23ea091a053ede3c29f2, size: 40651276, dir: sglang-omni}'

COMMON = """python: "3.12"
runtime: {{win-x64: wsl}}           # 리눅스 전용(SGLang) - Windows 에서는 WSL2 안에서
packages: {{linux-x64: ../_runtimes/sglang-omni/requirements-linux-x64.txt}}
packages_nodeps: {{linux-x64: ../_runtimes/sglang-omni/requirements-nodeps-linux-x64.txt}}
code:
{code}
local_packages: [code/sglang-omni]
env_bytes: {{cuda: 12600000000}}    # 리눅스 스팟 실측(torch cu13 + sglang + flashinfer)
requires: {{nvidia_driver: 580}}
system_deps: {{linux-x64: [cuda-toolkit-13-0]}}   # SGLang 커널 즉석 컴파일용 정식 CUDA 툴킷(WSL2 는 허브가 NVIDIA 공식 저장소에서 깔아요)
"""

ENGINES = {
    "zonos3-mini": dict(
        name="ZONOS3-Mini", wdir="zonos3", maker="Zyphra",
        summary="아주 빠른 엔진. 애니메이션·뉴스 성우 톤에 강해요. 공용 목소리 12명으로 말해요.",
        homepage="https://huggingface.co/Zyphra/ZONOS3-Mini",
        measured='  syll_rate: 7.5\n  cer_ko: 0.0393\n  hallu: "14/435"\n  gpu_mem_gb: 16  # 추정\n  gpu_tested_gb: 32\n  load_s: 300\n  rtf_gpu: 0.3\n  sample_rate: 44100\n  at: "2026-11-16"\n  evidence: verified',
        human='  line: 애니메이션과 뉴스 성우 톤에 강해요. 일상 한국어는 부자연스러운 편이에요.\n  short: 애니·뉴스 성우 톤\n  by: 사람 평가 1명(2026-11-16)',
        good_for="[애니메이션·뉴스 톤, 빠른 생성]",
        lic=dict(id="apache-2.0", name="Apache-2.0", commercial="yes", url="https://huggingface.co/Zyphra/ZONOS3-Mini",
                 summary=["개인·회사 모두 상업적으로 쓸 수 있어요.", "복제는 본인 목소리나 허락받은 목소리만 써요.",
                          "요약은 참고용이고 원문이 우선해요."]),
        voices="voices_from: shared\ndefault_voice: eunyoung",
        adapter_body='''    model_dir = "zonos3"

    def body(self, text, voice=None, seed=0, ref=None, ref_text=None):
        # 이 SGLang-Omni 판의 ZONOS3 는 voice 칸을 쓰지 않고 참조 클립만 받아요(서연·민준이 같은 소리였음 - 리뷰 2026-11-17).
        # 복제는 전사 없이 참조만(bench 와 같음).
        b = {"input": text, "response_format": "wav", "seed": int(seed or 0)}
        if ref:
            b["references"] = [{"audio_path": ref}]
        return b''',
    ),
    "cosyvoice3": dict(
        name="CosyVoice3 0.5B", wdir="cosyvoice3", maker="Alibaba FunAudioLLM",
        summary="작은데 자연스러운 범용 엔진. 작은 GPU 에 맞아요. 공용 목소리 12명으로 말해요.",
        homepage="https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
        measured='  syll_rate: 7.9\n  cer_ko: 0.0738\n  hallu: "54/515"\n  gpu_mem_gb: 6  # 추정\n  gpu_tested_gb: 32\n  load_s: 300\n  rtf_gpu: 1.3\n  sample_rate: 24000\n  at: "2026-11-16"\n  evidence: verified',
        human='  line: 작은데도 자연스러워요. 음질은 VoxCPM2 보다 조금 아래예요.\n  short: 작고 자연스러움\n  by: 사람 평가 1명(2026-11-16)',
        good_for="[범용 나레이션, 작은 GPU]",
        lic=dict(id="apache-2.0", name="Apache-2.0", commercial="yes", url="https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
                 summary=["개인·회사 모두 상업적으로 쓸 수 있어요.", "복제는 본인 목소리나 허락받은 목소리만 써요.",
                          "요약은 참고용이고 원문이 우선해요."]),
        voices="voices_from: shared\ndefault_voice: sujin",
        extra_code=['  - {url: "https://codeload.github.com/FunAudioLLM/CosyVoice/zip/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc", sha256: 4e7b1ce909f97abcc8afa0a890f92ccf2839ff435c698d4f04a1ba7aa71a022f, size: 1633232, dir: cosyvoice}',
                    '  - {url: "https://codeload.github.com/shivammehta25/Matcha-TTS/zip/dd9105b34bf2be2230f4aa1e4769fb586a3c824e", sha256: 75701744385a813822b2561b02562e4efe5e241d0142c21969642fcb15f61c15, size: 525858, dir: matcha}'],
        adapter_body='''    model_dir = "cosyvoice3"

    def python_paths(self):
        # SGLang 의 CosyVoice3 는 공식 CosyVoice 소스(cosyvoice 패키지)와 그 서브모듈 Matcha-TTS 가 경로에 있어야 해요
        code = Path(self.weights_dir).parent / "code"
        return [code / "cosyvoice", code / "matcha"]

    def body(self, text, voice=None, seed=0, ref=None, ref_text=None):
        # CosyVoice3 는 전사를 빼고 복제해야 정확해요(bench: 빼면 오류율 1.2~1.3%)
        b = {"input": text, "response_format": "wav", "seed": int(seed or 0)}
        if ref:
            b["references"] = [{"audio_path": ref}]
        return b''',
    ),
    "dots-tts": dict(
        name="dots.tts (MeanFlow)", wdir="dots-tts", maker="dots-studio",
        summary="2026 새 모델. 48kHz 고음질이에요. 한국어는 공식 언어 목록에 없고 벤치 점수만 있어요. 공용 목소리 12명으로 말해요.",
        homepage="https://huggingface.co/dots-studio/dots.tts-mf",
        measured='  evidence: unverified   # 우리 벤치 전 - 스팟 설치 확인만(2026-11-17)\n  gpu_mem_gb: 10  # 추정\n  gpu_tested_gb: 32\n  load_s: 300\n  sample_rate: 48000',
        human=None,
        good_for="[고음질]",
        lic=dict(id="apache-2.0", name="Apache-2.0", commercial="yes", url="https://huggingface.co/dots-studio/dots.tts-mf",
                 summary=["개인·회사 모두 상업적으로 쓸 수 있어요.", "복제는 본인 목소리나 허락받은 목소리만 써요.",
                          "요약은 참고용이고 원문이 우선해요."]),
        voices="voices_from: shared\ndefault_voice: dajung",
        adapter_body='''    model_dir = "dots-tts"''',
    ),
}


def main():
    for eid, e in ENGINES.items():
        d = ROOT / "engines" / eid
        d.mkdir(parents=True, exist_ok=True)
        w = (ROOT / "tmp" / f"w-{e['wdir']}.yaml").read_text(encoding="utf-8").splitlines()
        weights = "\n".join(w[1:])
        lic = e["lic"]
        summ = "\n".join(f"    - {s}" for s in lic["summary"])
        y = f"""# {e['name']} 레시피(판 1, 2026-11-17) - SGLang-Omni 서버형, 리눅스 전용(Windows 는 WSL2). 만든 곳: etc/make_sglomni_recipes.py
id: {eid}
name: {e['name']}
recipe_version: 1
role: tts
summary: {e['summary']}
maker: {e['maker']}
homepage: {e['homepage']}

devices: {{cpu: "no", nvidia: ok, mac: "no"}}
measured:
{e['measured']}
{('human_eval:' + chr(10) + e['human']) if e.get('human') else ''}
good_for: {e['good_for']}

license:
  id: {lic['id']}
  name: {lic['name']}
  url: {lic['url']}
  commercial: "{lic['commercial']}"
  text_file: LICENSE-weights.txt
  summary:
{summ}
maintenance: {{status: active}}

{COMMON.format(code=CODE + "".join(chr(10) + x for x in e.get("extra_code", [])))}
weights:
{weights}

adapter: adapter.py
max_chars: 200
{e['voices']}

selftest:
  - 안녕하세요, 소리 스튜디오 자가 시험이에요.
  - 오늘은 십일월 십칠일이고, 기온은 영상 오도예요.
  - 이 문장이 또렷하게 들리면 설치가 끝난 거예요.
"""
        (d / "recipe.yaml").write_text(y, encoding="utf-8", newline="\n")
        a = f'''"""{e['name']} 어댑터 - SGLang-Omni 서버(engines/_shared/sglomni.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from sglomni import SglOmniAdapter  # noqa: E402


class Adapter(SglOmniAdapter):
{e['adapter_body']}
'''
        (d / "adapter.py").write_text(a, encoding="utf-8", newline="\n")
        print("wrote", eid)


if __name__ == "__main__":
    main()
