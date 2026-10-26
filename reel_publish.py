"""'놓치면 손해' 릴스 영상 발행 (사용자가 직접 요청할 때만 수동 실행).

영상: docs/reels/<기준일>.mp4 (GitHub Pages로 공개 호스팅, deals_video.py로 만든 것)
캡션: 초안 JSON(data/deals/<초안일>.json)으로 deals_publish.build_caption과 같은 형식, 날짜·D-day는 기준일로

사용법 (GitHub Actions 'reel.yml' 수동 실행이 기본):
  python reel_publish.py 2026-10-27 2026-10-26     # 초안일, 기준일
환경변수: PAGES_BASE, IG_USER_ID, IG_TOKEN, (선택) TG_TOKEN, TG_CHAT, DRY_RUN=1
"""
import copy
import datetime
import json
import os
import sys
from pathlib import Path

from deals_publish import build_caption, notify
from publish import page_base_url, publish_reel

BASE = Path(__file__).parent


def main():
    src, asof = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else sys.argv[1]
    d = json.loads((BASE / "data" / "deals" / f"{src}.json").read_text(encoding="utf-8"))
    d = copy.deepcopy(d)
    d["date"] = asof
    d["items"] = [it for it in d["items"]
                  if datetime.date.fromisoformat(it["deadline"]) >= datetime.date.fromisoformat(asof)]
    video = BASE / "docs" / "reels" / f"{asof}.mp4"
    if not video.exists():
        sys.exit(f"영상 없음: {video}")
    url = f"{page_base_url()}/reels/{asof}.mp4"
    caption = build_caption(d)
    if os.environ.get("DRY_RUN") == "1":
        print("=== DRY RUN ===\n" + url + "\n\n--- 캡션 ---\n" + caption)
        return
    mid = publish_reel(url, caption)
    try:
        notify(f"🎬 놓치면 손해 릴스 발행 완료 ({asof}) id={mid}")
    except Exception as e:  # 알림 실패는 발행 결과에 영향 없음
        print(f"알림 실패: {e}")


if __name__ == "__main__":
    main()
