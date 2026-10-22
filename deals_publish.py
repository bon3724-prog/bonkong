"""
deals_publish.py — 승인된 '오늘 놓치면 손해 보는 정보' 카드를 인스타그램에 발행 (GitHub Actions)

흐름: PC(deals_draft.py)가 전날 밤 data/deals/<날짜>.json + 카드 이미지를 만들어 푸시하고
      텔레그램으로 미리보기를 보낸다 → 사용자가 '승인 MMDD'(또는 미리보기에 답장 '승인')
      → 이 스크립트가 아침에 승인 여부를 확인해 발행한다.

승인 방법(둘 중 하나):
  1) 텔레그램: '승인 1023' 이라고 보내거나, 미리보기 메시지에 '승인'이라고 답장
  2) GitHub: data/deals/<날짜>.json 의 "status" 를 "approved" 로 수정
취소: 텔레그램 '취소 1023' (또는 미리보기에 답장 '취소')

상태(status): draft → approved → posted   /  cancelled, skipped(마지막 실행까지 미승인)
인스타 토큰 갱신은 승인 여부와 관계없이 매 실행마다 한다(60일 만료 방지).

환경변수: PAGES_BASE, IG_USER_ID, IG_TOKEN, TG_TOKEN, TG_CHAT, DRY_RUN=1(발행 없이 확인)
         LAST_RUN=1 이면 이번 실행이 그날 마지막 시도(미승인이면 skipped 처리하고 알림)
"""

import os
import sys
import json
import time
import pathlib
import datetime

import requests

from publish import (KST, DRY, page_base_url, require_env, configured, clean_secret,
                     publish_instagram, refresh_tokens)

ROOT = pathlib.Path(__file__).parent
WEEK = "월화수목금토일"


# ── 텔레그램 ────────────────────────────────────────────
def tg_ok():
    return configured("TG_TOKEN", "TG_CHAT")


def tg(method, **params):
    token = clean_secret(os.environ["TG_TOKEN"])
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", data=params, timeout=30)
    r.raise_for_status()
    return r.json()


def notify(text):
    if not tg_ok():
        print(f"[알림 생략 — 텔레그램 미설정] {text}")
        return
    try:
        tg("sendMessage", chat_id=clean_secret(os.environ["TG_CHAT"]), text=text[:4000])
    except Exception as e:
        print(f"::warning::텔레그램 알림 실패: {e}")


def tg_decision(d):
    """텔레그램에서 이 날짜에 대한 마지막 결정('승인'/'취소')을 찾는다. 없으면 None."""
    if not tg_ok():
        return None
    chat = clean_secret(os.environ["TG_CHAT"])
    mmdd = d["date"][5:7] + d["date"][8:10]
    preview_id = d.get("tg_message_ids") or []
    sent_at = d.get("tg_sent_at", 0)
    try:
        updates = tg("getUpdates", limit=100).get("result", [])
    except Exception as e:
        print(f"::warning::텔레그램 확인 실패: {e}")
        return None
    decision = None
    for u in updates:  # 오래된 것부터 → 마지막 결정이 남는다
        m = u.get("message") or {}
        if str((m.get("chat") or {}).get("id")) != chat or m.get("date", 0) < sent_at:
            continue
        t = (m.get("text") or "").replace(" ", "")
        reply_to = (m.get("reply_to_message") or {}).get("message_id")
        for word in ("승인", "취소"):
            if t == f"{word}{mmdd}" or (t == word and reply_to in preview_id):
                decision = word
    return decision


# ── 캡션 ────────────────────────────────────────────────
def kdate(s):
    d = datetime.date.fromisoformat(s)
    return f"{d.month}/{d.day}({WEEK[d.weekday()]})"


def dday(post, dl):
    n = (datetime.date.fromisoformat(dl) - datetime.date.fromisoformat(post)).days
    return "오늘 마감" if n == 0 else f"D-{n}"


def build_caption(d):
    date = datetime.date.fromisoformat(d["date"])
    checked = d["created_at"][:10].replace("-", ".")
    head = f"📌 {date.month}월 {date.day}일 오늘 놓치면 손해 보는 정보\n{d.get('headline', '')}\n\n"
    tail = (f"※ {checked} 공식 안내 기준이에요. 예산 소진·일정 변경이 있을 수 있으니 "
            "신청 전 공식 홈페이지에서 꼭 확인하세요.\n"
            "저장해 두고 마감 전에 챙기세요 🔖\n\n"
            "#놓치면손해 #지원금 #신청마감 #할인정보 #정부지원금 #생활정보 #생활꿀팁 #오늘의정보")
    def block(i, it, short):
        note = f" · {it['deadline_note']}" if it.get("deadline_note") else ""
        lines = [f"{i}. [{it['category']}] {it['title']}"]
        if not short:
            lines.append(f"· 대상: {it['who']}")
        lines.append(f"· 혜택: {it['benefit']}")
        lines.append(f"· 마감: {kdate(it['deadline'])} {dday(d['date'], it['deadline'])}{note}")
        if not short:
            lines.append(f"· 신청: {it['how']}")
        lines.append(f"· 출처: {it['source_name']}")
        return "\n".join(lines) + "\n"

    for short in (False, True):  # 인스타 캡션 한도 2,200자 — 넘으면 대상·신청 줄을 뺀다
        body = "\n".join(block(i, it, short) for i, it in enumerate(d["items"], 1))
        caption = head + body + "\n" + tail
        if len(caption) <= 2200:
            return caption
    return caption[:2200]


# ── 상태 저장 ───────────────────────────────────────────
def save(path, d):
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    now = datetime.datetime.now(KST)
    today = now.date().isoformat()
    # 오전에 여러 번 돈다. 낮 12시 이후 실행(=마지막 시도)이면 미승인 시 건너뛰고 알린다
    last = os.environ.get("LAST_RUN") == "1" or now.hour >= 12

    if not DRY and configured("IG_TOKEN"):
        refresh_tokens()  # 발행 여부와 무관하게 매일 갱신

    path = ROOT / "data" / "deals" / f"{today}.json"
    if not path.exists():
        print(f"{today} 초안이 없습니다 (PC 초안 작업이 안 돌았거나 올릴 정보가 없음).")
        if last and not DRY:
            notify(f"⚠️ {today} 인스타 '놓치면 손해' 초안이 없어 오늘은 게시하지 않았어요.")
        return

    d = json.loads(path.read_text(encoding="utf-8"))
    status = d.get("status", "draft")
    if status in ("posted", "cancelled", "skipped"):
        print(f"{today} 상태가 {status} — 할 일 없음")
        return

    decision = "승인" if status == "approved" else tg_decision(d)
    if decision == "취소":
        d["status"] = "cancelled"
        save(path, d)
        notify(f"🗑 {today} 인스타 게시를 취소했어요.")
        print("취소됨")
        return
    if decision != "승인":
        print(f"{today} 아직 승인 전")
        if last and not DRY:
            d["status"] = "skipped"
            save(path, d)
            notify(f"⏭ {today} 인스타 카드가 승인되지 않아 오늘은 게시하지 않았어요.")
        return

    require_env("PAGES_BASE")
    base = page_base_url()
    files = sorted((ROOT / "docs" / "cards" / "deals" / today).glob("*.png"))
    if not 3 <= len(files) <= 10:
        raise SystemExit(f"카드 장수가 이상합니다 ({len(files)}장)")
    ver = int(time.time())
    urls = [f"{base}/cards/deals/{today}/{f.name}?v={ver}" for f in files]
    caption = build_caption(d)

    if DRY:
        print("=== DRY RUN ===\n" + "\n".join(urls) + "\n\n--- 캡션 ---\n" + caption)
        return

    require_env("IG_USER_ID", "IG_TOKEN")
    for u in urls:  # Pages 배포 지연 방어
        r = requests.head(u, timeout=30, allow_redirects=True)
        if not r.ok:
            raise RuntimeError(f"이미지에 접근할 수 없습니다: {u} ({r.status_code})")

    try:
        publish_instagram(urls, caption)
    except Exception as e:
        notify(f"❌ {today} 인스타 게시 실패: {str(e)[:300]}")
        raise
    d["status"] = "posted"
    d["posted_at"] = datetime.datetime.now(KST).strftime("%Y-%m-%dT%H:%M+09:00")
    save(path, d)
    notify(f"✅ {today} 인스타에 '놓치면 손해' 카드 {len(files)}장을 올렸어요.")


if __name__ == "__main__":
    main()
