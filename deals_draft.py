"""
deals_draft.py — '오늘 놓치면 손해 보는 정보' 초안 만들기 (PC, 작업 스케줄러가 매일 밤 실행)

1. 최근 뉴스 묶음(blog/news-report/data/*_digest.md)을 찾는다. 6시간보다 오래됐으면 collect.py로 새로 모은다
2. Claude(claude -p)가 prompts/deals.md 기준으로 정보를 고르고 공식 페이지로 확인해 data/deals/<게시일>.json 저장
3. 형식·날짜를 검사해 잘못된 항목은 뺀다
4. deal_cards.py로 카드 이미지 생성
5. git 커밋·푸시 (GitHub Pages가 이미지를 공개해야 인스타가 가져갈 수 있다)
6. 텔레그램으로 카드 미리보기 + 승인 방법 전송 → 사용자가 '승인 MMDD' 답장하면 아침에 GitHub이 게시

게시일: 정오 이후 실행이면 내일, 그 전이면 오늘.
사용:  python deals_draft.py            (기본)
       python deals_draft.py 2026-10-23 (게시일 지정)
       python deals_draft.py --no-push   (커밋·푸시·텔레그램 없이 카드까지만)
"""

import os
import re
import sys
import json
import time
import uuid
import pathlib
import datetime
import subprocess
import urllib.parse
import urllib.request
import zoneinfo

ROOT = pathlib.Path(__file__).parent
KST = zoneinfo.ZoneInfo("Asia/Seoul")
NEWS = pathlib.Path.home() / "Desktop" / "blog" / "news-report"
TG_CONFIG = pathlib.Path.home() / "Desktop" / "blog" / "news-alert" / "config.env"
CLAUDE = str(pathlib.Path.home() / ".local" / "bin" / "claude.exe")
TOOLS = ["Read", "Write", "Glob", "Grep", "WebSearch", "WebFetch"]
LOG = ROOT / "data" / "deals" / "draft.log"
CATS = {"지원금", "신청 마감", "할인"}
FIELDS = ["category", "title", "who", "benefit", "deadline", "how", "source_name", "source_url"]
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.datetime.now(KST):%Y-%m-%d %H:%M}] {msg}"
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd, cwd, timeout=600, **kw):
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=NOWIN, **kw)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ── 텔레그램 ────────────────────────────────────────────
def tg_keys():
    keys = {}
    if TG_CONFIG.exists():
        for line in TG_CONFIG.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            keys[k.strip()] = v.strip().strip("\"'")
    return keys.get("TELEGRAM_BOT_TOKEN", ""), keys.get("TELEGRAM_CHAT_ID", "")


def tg_call(token, method, fields, files=()):
    b = uuid.uuid4().hex
    body = b"".join(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
                    for k, v in fields.items())
    for name, path in files:
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{path.name}\"\r\n"
                 "Content-Type: image/png\r\n\r\n").encode() + path.read_bytes() + b"\r\n"
    body += f"--{b}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def send_preview(d, cards):
    """카드 미리보기(앨범) + 승인 안내. 보낸 메시지 id 목록을 돌려준다."""
    token, chat = tg_keys()
    if not token or not chat:
        log("텔레그램 키가 없어 미리보기를 못 보냈어요 (news-alert/config.env 확인)")
        return [], 0
    mmdd = d["date"][5:7] + d["date"][8:10]
    media = [{"type": "photo", "media": f"attach://c{i}"} for i in range(len(cards))]
    res = tg_call(token, "sendMediaGroup", {"chat_id": chat, "media": json.dumps(media)},
                  [(f"c{i}", p) for i, p in enumerate(cards)])
    ids = [m["message_id"] for m in res.get("result", [])]
    lines = [f"📸 {d['date']} 인스타 '놓치면 손해' 초안 ({len(d['items'])}개)"]
    for i, it in enumerate(d["items"], 1):
        lines.append(f"{i}. [{it['category']}] {it['title']} — 마감 {it['deadline']}\n   {it['source_url']}")
    lines.append(f"\n올려도 되면 '승인 {mmdd}' 라고 보내 주세요 (이 메시지에 '승인' 답장도 됨).\n"
                 f"올리지 않으려면 '취소 {mmdd}'.\n승인하면 아침에 GitHub이 인스타에 올려요(낮 12시 반쯤까지 승인 가능).")
    res = tg_call(token, "sendMessage", {"chat_id": chat, "text": "\n".join(lines)[:4000],
                                         "disable_web_page_preview": "true"})
    ids.append(res["result"]["message_id"])
    return ids, int(time.time())


def send_text(text):
    token, chat = tg_keys()
    if token and chat:
        try:
            tg_call(token, "sendMessage", {"chat_id": chat, "text": text[:4000]})
        except Exception as e:
            log(f"텔레그램 전송 실패: {e}")


# ── 뉴스 묶음 ───────────────────────────────────────────
def fresh_digests():
    data = NEWS / "data"
    digests = sorted(data.glob("*_digest.md"), key=lambda p: p.stat().st_mtime)
    if not digests or time.time() - digests[-1].stat().st_mtime > 6 * 3600:
        since = (datetime.datetime.now(KST) - datetime.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
        log(f"뉴스 묶음이 오래돼서 새로 모읍니다 (--since {since})")
        code, out = run([sys.executable, "collect.py", "--since", since], NEWS, timeout=900)
        if code:
            log(f"collect.py 실패: {out[-300:]}")
        digests = sorted(data.glob("*_digest.md"), key=lambda p: p.stat().st_mtime)
    cutoff = time.time() - 30 * 3600
    return [p for p in digests if p.stat().st_mtime >= cutoff][-3:]


def recent_posts(target):
    out = []
    for p in sorted((ROOT / "data" / "deals").glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("date", "") >= (target - datetime.timedelta(days=7)).isoformat() and d.get("date") != target.isoformat():
            out += [f"{d['date']} | {it['title']} | 마감 {it['deadline']}" for it in d.get("items", [])]
    return out or ["(없음)"]


# ── 검사 ────────────────────────────────────────────────
def validate(d, target):
    keep, dropped = [], []
    for it in d.get("items", []):
        why = None
        if any(not str(it.get(k, "")).strip() for k in FIELDS):
            why = "빈 칸 있음"
        elif it["category"] not in CATS:
            why = f"분류 오류({it['category']})"
        elif not re.match(r"^https?://", it["source_url"]):
            why = "출처 주소 없음"
        else:
            try:
                if datetime.date.fromisoformat(it["deadline"]) < target:
                    why = "이미 마감"
            except ValueError:
                why = f"마감일 형식 오류({it['deadline']})"
        (dropped.append(f"{it.get('title', '?')}: {why}") if why else keep.append(it))
    d["items"] = keep[:5]
    d["date"] = target.isoformat()
    d["status"] = "draft"
    d.setdefault("created_at", datetime.datetime.now(KST).strftime("%Y-%m-%dT%H:%M+09:00"))
    return dropped


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    push = "--no-push" not in sys.argv
    now = datetime.datetime.now(KST)
    target = datetime.date.fromisoformat(args[0]) if args else (
        now.date() + datetime.timedelta(days=1) if now.hour >= 12 else now.date())
    out_path = ROOT / "data" / "deals" / f"{target.isoformat()}.json"
    log(f"초안 시작: 게시일 {target}")

    if push:
        code, out = run(["git", "pull", "--rebase", "--autostash", "origin", "main"], ROOT)
        if code:
            log(f"git pull 실패 — 중단: {out[-300:]}")
            send_text(f"⚠️ {target} 인스타 초안: GitHub 동기화 실패로 중단했어요.")
            return

    digests = fresh_digests()
    if not digests:
        log("읽을 뉴스 묶음이 없음 — WebSearch만으로 진행")
    prompt = (ROOT / "prompts" / "deals.md").read_text(encoding="utf-8")
    prompt = (prompt.replace("{DATE}", target.isoformat())
              .replace("{TODAY}", now.date().isoformat())
              .replace("{OUT_PATH}", str(out_path)))
    prompt = (f"오늘은 {now:%Y-%m-%d %H:%M} KST, 게시일은 {target.isoformat()}이야.\n\n"
              "[읽을 파일]\n" + ("\n".join(str(p) for p in digests) or "(없음)") +
              "\n\n[최근 게시 목록]\n" + "\n".join(recent_posts(target)) + "\n\n" + prompt)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    r = subprocess.run([CLAUDE, "-p", "--output-format", "text", "--allowedTools", *TOOLS],
                       input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=2400, cwd=str(ROOT), creationflags=NOWIN)
    (ROOT / "data" / "deals" / f"{target.isoformat()}_claude.txt").write_text(
        (r.stdout or "") + "\n--- stderr ---\n" + (r.stderr or ""), encoding="utf-8")
    if not out_path.exists():
        log(f"Claude가 JSON을 만들지 못함 (종료 코드 {r.returncode})")
        send_text(f"⚠️ {target} 인스타 초안을 만들지 못했어요. data/deals/{target}_claude.txt 확인")
        return

    d = json.loads(out_path.read_text(encoding="utf-8"))
    dropped = validate(d, target)
    for x in dropped:
        log(f"뺀 항목 — {x}")
    if not d["items"]:
        out_path.unlink()
        log("확인된 항목이 없어 초안을 만들지 않음")
        send_text(f"ℹ️ {target}: 확인된 '놓치면 손해' 정보가 없어 내일 인스타는 쉬어요.")
        return
    out_path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    code, out = run([sys.executable, "deal_cards.py", target.isoformat()], ROOT)
    if code:
        log(f"카드 생성 실패: {out[-300:]}")
        send_text(f"⚠️ {target} 인스타 카드 생성 실패")
        return
    cards = sorted((ROOT / "docs" / "cards" / "deals" / target.isoformat()).glob("*.png"))
    log(f"카드 {len(cards)}장 생성")
    if not push:
        return

    ids, sent_at = send_preview(d, cards)
    d["tg_message_ids"], d["tg_sent_at"] = ids, sent_at
    out_path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run(["git", "add", "data/deals", f"docs/cards/deals/{target.isoformat()}"], ROOT)
    code, out = run(["git", "commit", "-m", f"놓치면 손해 초안 {target}"], ROOT)
    for _ in range(3):
        code, out = run(["git", "pull", "--rebase", "--autostash", "origin", "main"], ROOT)
        if not code:
            code, out = run(["git", "push", "origin", "HEAD:main"], ROOT)
        if not code:
            break
        time.sleep(10)
    if code:
        log(f"git push 실패: {out[-300:]}")
        send_text(f"⚠️ {target} 인스타 초안을 GitHub에 올리지 못했어요. 승인해도 게시되지 않으니 PC를 확인해 주세요.")
        return
    log("초안 푸시·미리보기 전송 완료")


if __name__ == "__main__":
    main()
