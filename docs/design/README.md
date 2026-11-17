# Sori Studio 화면 설계 - 무엇이 어디 있나

기능 설계 [`../sori-studio-features.md`](../sori-studio-features.md)(v0.3, 정본)의 MVP(P0·P1)를 화면으로 옮긴 자료예요. 코드는 아직 없어요.

| 파일 | 내용 | 언제 봐요 |
|---|---|---|
| [`design.md`](design.md) | 화면 설계서: 디자인 원칙, 브랜드(로고·색·글꼴·아이콘, 라이트/다크 토큰 표, 접근성), 내비게이션, 창 크기·serve 모드, 화면 목록(목적·구성·상태·단축키), 핵심 흐름 8개, 마이크로카피·오류 문구, 기능 대응표, **기능 설계에 돌려줄 것** | 화면을 만들기 전에 전체를 한 번 |
| [`components.md`](components.md) | 구현용 부품 목록과 상태별 규칙(단추·배지·엔진 카드·엔진 줄·설치 패널·대본 줄·테이크·파형·진행·알림·마법사·앱 틀) | 부품을 만들 때 옆에 두고 |
| [`mockups/`](mockups/) | 예상 화면 그림 8장(`<번호>-<화면>.png` 원본 1536×1024, `.webp` 가벼운 판)과 프롬프트 [`prompts.json`](mockups/prompts.json) | 분위기·짜임을 눈으로 볼 때 |
| [`../../etc/mockups.py`](../../etc/mockups.py) | 그림을 만드는 스크립트(Azure OpenAI gpt-image-2.5) | 그림을 다시 만들 때 |

## 읽는 순서
1. `design.md` 0~3절(틀과 색) → 5절에서 만들 화면 → 6절에서 그 화면이 든 흐름.
2. `components.md` 에서 그 화면에 쓰는 부품.
3. `mockups/` 의 그림은 참고만 해요.

## 정본 순서
기능은 **기능 설계**가, 화면·토큰·문구는 **design.md 와 components.md** 가 정본이에요. **목업 그림은 예상 모습**이라 문서와 다르면 문서가 맞아요(다른 곳은 `design.md` 11절 표에 적어 뒀어요). 그림 속 용량·시간·포트·판 번호는 예시 숫자예요.

## 그림 목록
| 그림 | 화면 |
|---|---|
| `01-wizard` | 첫 실행 마법사 3단계(쓰임새 → 추천 엔진) |
| `02-catalog` | 모델 카탈로그 |
| `03-model-install` | 모델 상세 + 설치(계획·라이선스 동의·진행) |
| `04-studio` | 대본 에디터(캐릭터·대본 줄·테이크·일괄 생성) |
| `05-compare` | 엔진 비교(이름 가리기) |
| `06-engine-status` | 설치됨 - 엔진 죽음과 복구 |
| `07-export` | 내보내기 창 |
| `08-settings-api-dark` | 설정 > 로컬 API(다크 모드) |

## 그림 다시 만들기
```
python etc/mockups.py gen                      # 전부, 화면당 후보 둘 → tmp/mockups/<화면>.<a|b>.png
python etc/mockups.py gen studio --tag r2      # 한 화면만 다시 → tmp/mockups/studio.<a|b>.r2.png
python etc/mockups.py pick studio=b.r2         # 고른 후보 → docs/design/mockups/04-studio.png + .webp
```
- 프롬프트는 `mockups/prompts.json` 을 고쳐요(공통 화풍 `style`, 공통 틀 `chrome`, 화면별 `prompt`).
- 목업 그림은 사내 이미지 생성 도구로 만들었어요(`etc/mockups.py` 는 공개판에 없어요). 그림은 예상 모습일 뿐이고, 정본은 이 폴더의 설계서예요.
- 화면별 후보 둘을 만들어 고르는 방식이었어요.
- 후보는 꼭 눈으로 열어 봐요: 화면 짜임이 설계서와 맞는지, 한글 오타가 없는지, 남의 로고가 없는지. 버린 후보는 `tmp/` 에 둬요(git 제외).
