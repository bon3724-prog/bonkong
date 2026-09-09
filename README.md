# 오늘의 운세 자동 발행 봇

매일 아침 7시, 별자리 운세 12개 + 띠별 운세 12개를 카드 7장으로 만들어
쓰레드와 인스타그램에 캐러셀로 자동 발행합니다.

## 파이프라인

    generate.py  일진(日辰) 계산 → 12띠 합/충 판정 → Claude API로 문구 생성
        ↓ data/YYYY-MM-DD.json
    cards.py     카드 이미지 7장 렌더링 (1080x1350)
        ↓ docs/cards/YYYY-MM-DD/*.png  → GitHub Pages로 공개
    publish.py   쓰레드 캐러셀 + 인스타 캐러셀 발행

## 설정 순서

### 1. 저장소 준비
- 이 파일들을 새 GitHub 저장소에 올립니다.
- Settings → Pages → Source: `main` 브랜치 / `/docs` 폴더
- Settings → Variables → `PAGES_BASE` = `https://<아이디>.github.io/<저장소명>`

### 2. Meta 앱 설정
1. 인스타 계정을 프로페셔널(비즈니스/크리에이터)로 전환
2. 페이스북 페이지 생성 후 인스타 계정과 연결
3. developers.facebook.com → 앱 만들기 → Instagram, Threads 제품 추가
4. 앱 역할 → 테스터에 본인 계정 추가 (심사 없이 본인 계정 발행 가능)
5. 권한 요청: instagram_business_content_publish, threads_basic, threads_content_publish
6. 그래프 API 탐색기에서 장기 토큰(60일) 발급

인스타그램 자동 발행에는 `instagram_business_content_publish` 권한과
프로페셔널 계정의 숫자형 `IG_USER_ID`가 필요합니다. `IG_TOKEN`은 해당 계정에
대한 장기 액세스 토큰이어야 합니다. 쓰레드를 사용하지 않는 경우에는
Actions 변수 `PUBLISH_THREADS`를 `0`으로 설정하면 인스타그램만 발행합니다.

### 3. Secrets 등록
Settings → Secrets and variables → Actions

| 이름 | 설명 |
|---|---|
| ANTHROPIC_API_KEY | console.anthropic.com에서 발급 |
| IG_USER_ID | 인스타 비즈니스 계정 ID (숫자) |
| IG_TOKEN | 인스타 장기 액세스 토큰 |
| PUBLISH_THREADS | 쓰레드 발행 여부. `0`이면 인스타그램만 발행 (선택) |
| THREADS_USER_ID | 쓰레드 사용자 ID |
| THREADS_TOKEN | 쓰레드 장기 액세스 토큰 |
| TG_TOKEN, TG_CHAT | (선택) 실패 알림용 텔레그램 |

### 4. 테스트
로컬에서 발행 없이 확인:

    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...
    python generate.py
    python cards.py
    DRY_RUN=1 PAGES_BASE=https://example.com python publish.py

카드 이미지는 `docs/cards/오늘날짜/` 에 생깁니다. 눈으로 확인한 뒤
GitHub에서 Actions → "오늘의 운세 자동 발행" → Run workflow 로 실제 발행을 시험하세요.

## 주의사항

- **일진 검증**: 첫 실행 시 출력되는 일진(예: 병오년 정유월 갑진일)을
  네이버 만세력에서 같은 날짜로 조회해 일치하는지 확인하세요.
- **토큰 만료**: 장기 토큰은 60일입니다. publish.py가 매일 갱신을 호출하지만,
  30일 이상 워크플로가 멈추면 만료되어 수동 재발급이 필요합니다.
- **인스타 캐러셀 한도**: API는 10장까지입니다 (앱에서는 20장). 7장으로 맞춰뒀습니다.
- **이미지 URL**: 인스타그램 API는 공개 HTTPS 이미지 URL만 받으므로 GitHub Pages가
    활성화되어 있어야 합니다. `PAGES_BASE`는 카드 PNG가 실제로 열리는 주소여야 합니다.
- **발행 한도**: 인스타 100건/24시간, 쓰레드 250건/24시간. 하루 1건이므로 여유롭습니다.
- **실행 시각**: GitHub Actions cron은 정시를 보장하지 않습니다.
  06:40 KST에 시작해 07:00 전후로 발행되도록 잡아뒀습니다.
