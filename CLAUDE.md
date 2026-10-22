# insta_auto — 인스타 자동 발행 봇

> **2026-10-22부터 주제 변경: "오늘 놓치면 손해 보는 정보 (지원금·신청 마감·할인)"**
> 운세 자동 발행은 중단했다(아래 운세 설명과 generate.py·cards.py는 기록용으로 남김. `publish.py`의 인스타 발행·토큰 갱신 함수는 새 흐름에서도 그대로 쓴다).
>
> **새 흐름 — 확인 후 게시**
> 1. 밤 22:30 PC 작업 스케줄러 `InstaDealsDraft` → `deals_draft.py`
>    - 최근 뉴스 묶음(`blog/news-report/data/*_digest.md`, 6시간 넘게 오래되면 `collect.py`로 새로 수집)을 근거로
>      Claude(`claude -p`, 지시문 `prompts/deals.md`)가 3~5개를 골라 **공식 페이지로 확인**해 `data/deals/<게시일>.json` 저장
>    - 검사(빈 칸·분류·마감 지난 항목 제거) → `deal_cards.py`로 카드(밝은 배경, 표지+항목별+마무리, 최대 7장) → 커밋·푸시(GitHub Pages)
>    - 텔레그램(news-alert 봇)으로 카드 미리보기 + "승인 MMDD / 취소 MMDD" 안내
> 2. 아침 GitHub Actions `daily.yml`(06:40·08:40·10:40·12:40 KST 시도) → `deals_publish.py`
>    - 텔레그램 '승인 MMDD'(또는 미리보기 답장 '승인') 또는 JSON `status: approved`면 인스타 캐러셀 발행 → `posted`
>    - 낮 12시 이후 마지막 시도까지 미승인이면 `skipped` + 알림. 인스타 토큰 갱신은 매 실행마다(승인 여부 무관)
> - **사람 승인 없이 게시하지 않는다.** 이 원칙을 바꾸지 말 것(마감·금액 오류는 독자 실제 손해).
> - 저장소가 공개라 Claude 원문 출력·로그(`data/deals/*_claude.txt`, `draft.log`)는 .gitignore. 토큰은 GitHub Secrets(IG_TOKEN, IG_USER_ID, TG_TOKEN, TG_CHAT)에만.
> - PC가 밤에 꺼져 있으면 초안이 안 생기고, 그날은 게시하지 않는다(알림만).

작업 환경: Windows / 바탕화면 `insta_auto` 폴더

---

## (이전) 오늘의 운세 — 2026-10-22까지 운영

## 파이프라인

```
    generate.py   일진(日辰) 계산 → 12띠 합/충 판정 → 무료 템플릿으로 운세 문구 생성
    ↓ data/YYYY-MM-DD.json
cards.py      카드 이미지 7장 렌더링 (1080x1350, 4:5)
    ↓ docs/cards/YYYY-MM-DD/00~06.png  → GitHub Pages로 공개 호스팅
publish.py    쓰레드 캐러셀 + 인스타 캐러셀 발행 + 토큰 갱신
    ↑
.github/workflows/daily.yml   매일 21:40 UTC(06:40 KST) 실행
```

### 카드 구성 (7장인 이유)
인스타 Content Publishing API는 캐러셀 **10장**이 한계 (앱에서는 20장이지만 API는 10장).
별자리는 빼고(사용자 요청, 2026-10-20) 띠만 다룬다. 휴대폰 가독성을 위해 한 장에 띠 2개씩, 본문 40px 안팎.

- `00.png` 커버 — 날짜, 일진, 헤드라인, 오늘 운 좋은 띠 TOP3, 행운의 색/숫자/아이템
- `01~06.png` 띠 2개씩 — 띠 이름, 출생연도(예: 58·70·82·94·06년생), 합/충 태그, 총운, 애정운·금전운·사업운 별점+한 줄
- 별점은 합/충 판정 범위 안에서만 움직인다 (합 3~5, 충 1~3) — 판정과 어긋나지 않게

---

## 핵심 설계 의도 — 함부로 바꾸지 말 것

**일진 기반 관계 계산이 이 프로젝트의 핵심이다.**

LLM에게 "오늘 운세 써줘"만 시키면 매일 비슷한 글이 나오고, 그건 양산형 콘텐츠로 취급된다.
그래서 `generate.py`에서 먼저 그날의 일지(日支)와 12띠 지지의 관계를 명리 규칙으로 계산한다:

- 삼합: 신자진 / 해묘미 / 인오술 / 사유축
- 육합: 자축 / 인해 / 묘술 / 진유 / 사신 / 오미
- 충: 자오 / 축미 / 인신 / 묘유 / 진술 / 사해

이 판정 결과를 프롬프트에 근거로 넣고, "충이면 조심, 합이면 순조롭게" 어긋나지 않게 강제한다.
→ 날마다 결과가 논리적으로 달라진다.

**리팩터링할 때 이 부분을 단순화하거나 프롬프트만 남기지 말 것.**

---

## 현재 상태

- [x] 코드 4개 파일 작성 완료 (문법 검증만 됨)
- [ ] **로컬 실행 미검증** — 아직 한 번도 실제로 돌려본 적 없음
- [ ] Meta 앱 / 토큰 발급 안 됨
- [ ] GitHub 저장소 생성 안 됨

즉, 지금은 "코드만 있는" 상태다. 다음 순서로 진행한다.

---

## 다음 작업 순서

### 1단계: 로컬에서 카드 이미지부터 뽑아보기 (지금 여기부터)

```powershell
cd $env:USERPROFILE\Desktop\insta_auto
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python generate.py
python cards.py
```

`docs\cards\<오늘날짜>\` 에 PNG 7장이 생긴다. 눈으로 확인.

발행 없이 캡션과 URL만 확인:
```powershell
$env:PAGES_BASE = "https://example.com"
$env:DRY_RUN = "1"
python publish.py
```

**Windows 한글 폰트**: `cards.py`의 `setup_font()`가 맑은 고딕(`C:/Windows/Fonts/malgunbd.ttf`)을
자동으로 찾는다. 못 찾으면 에러 메시지가 뜬다.

### 2단계: 일진 검증 (반드시)

`generate.py` 실행 시 출력되는 일진(예: `병오년 정유월 갑진일`)을
네이버 만세력에서 같은 날짜로 조회해 **일치하는지 대조한다.**
`korean_lunar_calendar` 라이브러리가 절기 경계에서 어긋날 수 있다.
여기가 틀리면 콘텐츠 전체의 근거가 무너지므로 넘어가지 말 것.

### 3단계: 카드 디자인 다듬기
색상 팔레트는 `cards.py` 상단 상수(`BG`, `ACCENT`, `TEXT`, `SUB`)에 모여 있다.
레이아웃은 `draw_cover()` / `draw_items()`.

### 4단계: Meta 앱 설정 + 토큰 발급
1. 인스타 계정 → 프로페셔널(비즈니스/크리에이터) 전환
2. 페이스북 페이지 생성 후 인스타 계정 연결
3. developers.facebook.com → 앱 만들기 → Instagram, Threads 제품 추가
4. **앱 역할 → 테스터에 본인 계정 추가** ← 이걸 하면 앱 심사(2~4주) 없이 본인 계정 발행 가능
5. 권한: `instagram_business_content_publish`, `threads_basic`, `threads_content_publish`
6. 그래프 API 탐색기에서 장기 토큰(60일) 발급

### 5단계: GitHub 저장소 + Pages
- 저장소 생성 후 push
- Settings → Pages → Source: `main` 브랜치 / `/docs` 폴더
- Settings → Variables → `PAGES_BASE` = `https://<아이디>.github.io/<저장소명>`
- Settings → Secrets: `IG_USER_ID`, `IG_TOKEN`,
  `THREADS_USER_ID`, `THREADS_TOKEN`, (선택) `TG_TOKEN`, `TG_CHAT`

### 6단계: Actions에서 수동 실행으로 첫 발행 테스트
Actions → "오늘의 운세 자동 발행" → Run workflow

---

## 알려진 제약 / 주의사항

| 항목 | 내용 |
|---|---|
| 인스타 캐러셀 | API는 10장 한계 (앱은 20장). 7장으로 맞춤 |
| 쓰레드 텍스트 | 500자 제한, 해시태그 1개만 인식 |
| 이미지 호스팅 | 두 API 모두 **공개 URL 필수**. 바이트 업로드 불가 |
| 예약 발행 | 두 API 모두 지원 안 함. cron 직접 돌려야 함 |
| 토큰 만료 | 장기 토큰 60일. `publish.py`가 매일 갱신 호출하지만 30일 이상 멈추면 수동 재발급 |
| cron 정확도 | GitHub Actions는 정시 보장 안 됨. 06:40 시작해서 07:00 전후 발행 |
| 발행 한도 | 인스타 100건/24h, 쓰레드 250건/24h (하루 1건이라 여유) |
| 텍스트 전용 | 인스타는 이미지 없이 발행 불가 |

---

## 튜닝 여지 (나중에)

**관계 판정이 "평"으로 많이 빠지는 문제**
현재 12띠 중 4~5개만 합/충이 걸리고 나머지는 "평(무난)"이라 문구가 밋밋해진다.
개선안: 일간(日干)의 오행과 띠 지지의 상생상극을 한 겹 더 얹으면 12개 전부 뚜렷하게 갈린다.
며칠 돌려보고 결과가 밋밋하면 그때 추가.

**추가 아이디어**
- 주말/월초 등 특별한 날 카드 템플릿 변형
- 인스타 릴스로 확장 (카드 슬라이드 애니메이션)
- 발행 후 인사이트 수집해서 어떤 요일/문구가 반응 좋은지 분석

---

## 콘텐츠 원칙

- 카드와 캡션에 **"재미로 보는 운세입니다"** 고지를 반드시 유지한다
- 겁주는 표현 금지 — 금전 손실, 사고, 질병 등 불안 유발 문구는 프롬프트에서 차단 중
- 이미지는 전부 matplotlib으로 직접 생성 (저작권 안전, 제3자 이미지 사용 안 함)
- 상투어("좋은 하루 되세요" 등) 금지도 프롬프트에 포함되어 있음
