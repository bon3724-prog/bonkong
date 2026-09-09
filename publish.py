"""
publish.py — 카드 7장을 쓰레드 + 인스타에 캐러셀로 발행

두 API 모두 '컨테이너 생성 → 발행' 2단계 구조다.
이미지는 반드시 공개 URL이어야 한다 (GitHub Pages 사용).

환경변수:
  PAGES_BASE        예) https://myid.github.io/fortune-bot
  THREADS_USER_ID / THREADS_TOKEN
  IG_USER_ID / IG_TOKEN
  DRY_RUN=1         발행 없이 캡션/URL만 출력 (첫 테스트용)
"""

import os
import sys
import json
import time
import pathlib
import datetime
import zoneinfo
import requests

ROOT = pathlib.Path(__file__).parent
KST = zoneinfo.ZoneInfo("Asia/Seoul")
THREADS_API = "https://graph.threads.net/v1.0"
IG_API = f"https://graph.facebook.com/{os.environ.get('IG_API_VERSION', 'v24.0')}"
DRY = os.environ.get("DRY_RUN") == "1"


def post(url, params):
    r = requests.post(url, data=params, timeout=60)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text[:500]}")
    return r.json()


def get(url, params):
    r = requests.get(url, params=params, timeout=60)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text[:500]}")
    return r.json()


def require_env(*names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError("필수 환경변수가 없습니다: " + ", ".join(missing))


def configured(*names):
    return all(os.environ.get(name) for name in names)


# ── 캡션 ────────────────────────────────────────────────
def build_captions(d):
    date_k = datetime.date.fromisoformat(d["date"]).strftime("%m월 %d일")

    # 쓰레드는 500자 제한 — 짧게
    threads_text = (
        f"{date_k} 오늘의 운세\n"
        f"{d['gapja']}\n\n"
        f"{d['headline']}\n\n"
        f"행운의 색 {d['lucky_color']} · 숫자 {d['lucky_number']} · "
        f"아이템 {d['lucky_item']}\n\n"
        f"별자리와 띠별 운세는 카드에서 확인하세요 →\n"
        f"#오늘의운세"  # 쓰레드는 해시태그 1개만 인식됨
    )
    if len(threads_text) > 500:
        threads_text = threads_text[:497] + "..."

    ig_caption = (
        f"{date_k} 오늘의 운세 🔮\n"
        f"{d['gapja']}\n\n"
        f"{d['headline']}\n\n"
        f"✨ 행운의 색 {d['lucky_color']}\n"
        f"✨ 행운의 숫자 {d['lucky_number']}\n"
        f"✨ 행운의 아이템 {d['lucky_item']}\n\n"
        f"오늘 나의 별자리·띠 운세는 넘겨서 확인 👉\n"
        f"매일 아침 7시 업데이트됩니다.\n"
        f"※ 재미로 보는 운세입니다\n\n"
        f"#오늘의운세 #별자리운세 #띠별운세 #오늘의띠별운세 #운세 "
        f"#데일리운세 #{d['date'].replace('-', '')}운세"
    )
    return threads_text, ig_caption


# ── 쓰레드 ──────────────────────────────────────────────
def publish_threads(urls, text):
    uid, token = os.environ["THREADS_USER_ID"], os.environ["THREADS_TOKEN"]

    children = []
    for u in urls:
        res = post(f"{THREADS_API}/{uid}/threads", {
            "media_type": "IMAGE",
            "image_url": u,
            "is_carousel_item": "true",
            "access_token": token,
        })
        children.append(res["id"])
        time.sleep(1)  # 스파이크 방지

    parent = post(f"{THREADS_API}/{uid}/threads", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "text": text,
        "access_token": token,
    })

    # Meta 권장: 발행 전 평균 30초 대기
    time.sleep(30)
    res = post(f"{THREADS_API}/{uid}/threads_publish", {
        "creation_id": parent["id"],
        "access_token": token,
    })
    print(f"[쓰레드] 발행 완료 id={res['id']}")


# ── 인스타그램 ──────────────────────────────────────────
def wait_ready(container_id, token, timeout=300):
    """컨테이너가 FINISHED 될 때까지 폴링. 이거 없이 발행하면 자주 실패한다."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = get(f"{IG_API}/{container_id}",
                  {"fields": "status_code,status", "access_token": token})
        code = res.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError(f"컨테이너 처리 실패: {res}")
        time.sleep(10)
    raise TimeoutError(f"컨테이너 {container_id} 처리 시간 초과")


def publish_instagram(urls, caption):
    uid, token = os.environ["IG_USER_ID"], os.environ["IG_TOKEN"]

    if len(urls) > 10:
        raise ValueError(f"인스타 캐러셀은 API로 10장까지입니다 (현재 {len(urls)}장)")

    children = []
    for u in urls:
        res = post(f"{IG_API}/{uid}/media", {
            "image_url": u,
            "is_carousel_item": "true",
            "access_token": token,
        })
        children.append(res["id"])
        time.sleep(1)

    for cid in children:
        wait_ready(cid, token)

    parent = post(f"{IG_API}/{uid}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
        "access_token": token,
    })
    wait_ready(parent["id"], token)

    res = post(f"{IG_API}/{uid}/media_publish", {
        "creation_id": parent["id"],
        "access_token": token,
    })
    print(f"[인스타] 발행 완료 id={res['id']}")


# ── 토큰 갱신 ───────────────────────────────────────────
def refresh_tokens():
    """장기 토큰은 60일이면 만료된다. 매일 갱신 호출을 걸어두면 만료되지 않는다.
    갱신된 값은 로그로 찍히지 않으니, 실패하면 알림만 받고 수동 재발급할 것."""
    if not configured("THREADS_TOKEN"):
        return
    try:
        r = get("https://graph.threads.net/refresh_access_token", {
            "grant_type": "th_refresh_token",
            "access_token": os.environ["THREADS_TOKEN"],
        })
        print(f"[토큰] 쓰레드 갱신 OK, 만료까지 {r.get('expires_in', 0)//86400}일")
    except Exception as e:
        print(f"[토큰] 쓰레드 갱신 실패: {e}", file=sys.stderr)


def main():
    require_env("PAGES_BASE")
    base = os.environ["PAGES_BASE"].rstrip("/")
    today = datetime.datetime.now(KST).date().isoformat()

    d = json.loads((ROOT / "data" / f"{today}.json").read_text(encoding="utf-8"))
    card_dir = ROOT / "docs" / "cards" / today
    files = sorted(card_dir.glob("*.png"))
    if len(files) != 7:
        raise RuntimeError(f"카드가 7장이 아닙니다 ({len(files)}장)")

    urls = [f"{base}/cards/{today}/{f.name}" for f in files]
    threads_text, ig_caption = build_captions(d)

    if DRY:
        print("=== DRY RUN ===")
        print("\n".join(urls))
        print("\n--- 쓰레드 ---\n" + threads_text)
        print("\n--- 인스타 ---\n" + ig_caption)
        return

    require_env("IG_USER_ID", "IG_TOKEN")

    # 이미지 URL이 실제로 열리는지 먼저 확인 (Pages 배포 지연 방어)
    for u in urls:
        r = requests.head(u, timeout=30, allow_redirects=True)
        if not r.ok:
            raise RuntimeError(f"이미지에 접근할 수 없습니다: {u} ({r.status_code})")

    errors = []
    publishers = [("인스타", lambda: publish_instagram(urls, ig_caption))]
    if os.environ.get("PUBLISH_THREADS", "1") != "0":
        if configured("THREADS_USER_ID", "THREADS_TOKEN"):
            publishers.insert(0, ("쓰레드", lambda: publish_threads(urls, threads_text)))
        elif any(os.environ.get(name) for name in ("THREADS_USER_ID", "THREADS_TOKEN")):
            errors.append("쓰레드: THREADS_USER_ID와 THREADS_TOKEN을 함께 설정해야 합니다")
        else:
            print("[쓰레드] 자격 증명이 없어 건너뜁니다")

    for name, fn in publishers:
        try:
            fn()
        except Exception as e:  # 한쪽 실패가 다른 쪽을 막지 않게
            print(f"[{name}] 실패: {e}", file=sys.stderr)
            errors.append(f"{name}: {e}")

    refresh_tokens()

    if errors:
        raise SystemExit("발행 실패:\n" + "\n".join(errors))


if __name__ == "__main__":
    main()
