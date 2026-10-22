"""
deal_cards.py — '오늘 놓치면 손해 보는 정보' JSON을 카드 이미지로 렌더링

입력: data/deals/YYYY-MM-DD.json
출력: docs/cards/deals/YYYY-MM-DD/00.png ~ NN.png  (1080x1350, 4:5)
  00     커버 (날짜 + 헤드라인 + 항목 목록과 D-day)
  01~05  항목 1개당 1장 (대상·혜택·마감·신청 방법·출처)
  마지막 저장 안내 + 확인 고지

항목은 최대 5개라 최대 7장(인스타 API 캐러셀 한도 10장 이내).
이미지는 matplotlib으로 직접 그린다(제3자 이미지 사용 안 함).
"""

import json
import sys
import datetime
import pathlib
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

ROOT = pathlib.Path(__file__).parent
W, H = 1080, 1350
DPI = 100

# ── 밝은 팔레트 ─────────────────────────────────────────
BG = "#FFFFFF"
PANEL = "#F6F7F9"
TEXT = "#1F2328"
SUB = "#5B6470"
LINE = "#E3E6EA"
ACCENT = "#E5484D"  # D-day·강조
CAT_COLORS = {"지원금": "#12A150", "신청 마감": "#E5484D", "할인": "#F08C00"}
WEEK = "월화수목금토일"


def setup_font():
    """한글 폰트(보통·굵게)를 같은 글꼴 이름으로 등록해 fontweight="bold"가 굵은 파일을 쓰게 한다."""
    pairs = [
        ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"),
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
         "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    ]
    for reg, bold in pairs:
        if pathlib.Path(reg).exists() and pathlib.Path(bold).exists():
            font_manager.fontManager.addfont(reg)
            font_manager.fontManager.addfont(bold)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=reg).get_name()
            return
    raise SystemExit("한글 폰트(맑은 고딕 또는 나눔고딕)를 찾을 수 없습니다.")


def dday(post_date, deadline):
    n = (deadline - post_date).days
    return "오늘 마감" if n == 0 else f"D-{n}"


def kdate(d):
    return f"{d.month}월 {d.day}일({WEEK[d.weekday()]})"


def new_canvas():
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor(BG)
    return fig, ax


def save(fig, path):
    fig.savefig(path, facecolor=fig.get_facecolor(), dpi=DPI)
    plt.close(fig)
    print(f"  {path.name}")


def chip(ax, x, y, text, color, size=24, ha="left"):
    ax.text(x, y, f" {text} ", ha=ha, va="center", color="white", fontsize=size,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.45,rounding_size=0.8", fc=color, ec="none"))


def panel(ax, x, y, w, h, color=PANEL):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.025",
                                fc=color, ec="none", transform=ax.transAxes))


def wrap(s, width):
    return "\n".join(textwrap.wrap(s, width)) if s else ""


def draw_cover(d, post_date, out):
    fig, ax = new_canvas()
    ax.text(0.08, 0.915, kdate(post_date), color=SUB, fontsize=30)
    ax.text(0.08, 0.80, "오늘 놓치면\n손해 보는 정보", color=TEXT, fontsize=64,
            fontweight="bold", va="center", linespacing=1.25)
    ax.text(0.08, 0.685, d.get("headline", ""), color=ACCENT, fontsize=34, fontweight="bold")

    top, step = 0.60, 0.105
    for i, it in enumerate(d["items"]):
        y = top - i * step
        panel(ax, 0.06, y - 0.085, 0.88, 0.09)
        chip(ax, 0.09, y - 0.040, it["category"], CAT_COLORS[it["category"]], size=20)
        ax.text(0.28, y - 0.040, it["title"], color=TEXT, fontsize=27, fontweight="bold", va="center")
        dl = datetime.date.fromisoformat(it["deadline"])
        ax.text(0.91, y - 0.040, dday(post_date, dl), color=ACCENT, fontsize=27,
                fontweight="bold", va="center", ha="right")

    ax.text(0.5, 0.045, "넘겨서 대상·혜택·신청 방법 확인 →", ha="center", color=SUB, fontsize=24)
    save(fig, out)


def draw_item(it, idx, total, post_date, out):
    fig, ax = new_canvas()
    color = CAT_COLORS[it["category"]]
    dl = datetime.date.fromisoformat(it["deadline"])

    chip(ax, 0.08, 0.925, it["category"], color, size=24)
    ax.text(0.92, 0.925, f"{idx}/{total}", ha="right", va="center", color=SUB, fontsize=24)
    ax.text(0.08, 0.80, wrap(it["title"], 11), color=TEXT, fontsize=56, fontweight="bold",
            va="center", linespacing=1.3)

    # D-day 강조 띠
    panel(ax, 0.06, 0.62, 0.88, 0.10, color="#FDECEC")
    ax.text(0.10, 0.67, dday(post_date, dl), color=ACCENT, fontsize=44, fontweight="bold", va="center")
    note = f"{kdate(dl)}까지" + (f" · {it['deadline_note']}" if it.get("deadline_note") else "")
    lines = textwrap.wrap(note, 20)
    if len(lines) > 2:  # 상자 안에 2줄까지만 — 넘치면 말줄임
        lines = [lines[0], lines[1][:19] + "…"]
    ax.text(0.36, 0.67, "\n".join(lines), color=TEXT, fontsize=26, va="center", linespacing=1.4)

    rows = [("대상", it["who"]), ("혜택", it["benefit"]), ("신청", it["how"])]
    y = 0.54
    for label, body in rows:
        ax.text(0.08, y, label, color=color, fontsize=28, fontweight="bold", va="top")
        txt = wrap(body, 19)
        ax.text(0.25, y, txt, color=TEXT, fontsize=30, va="top", linespacing=1.45)
        lines = max(1, txt.count("\n") + 1)
        y -= 0.06 + 0.042 * lines
        ax.plot([0.08, 0.92], [y + 0.025, y + 0.025], color=LINE, lw=1.2)

    ax.text(0.08, 0.075, wrap(f"출처: {it['source_name']}", 34), color=SUB, fontsize=22, va="center")
    ax.text(0.08, 0.035, "신청 전 공식 안내에서 조건을 꼭 확인하세요", color=SUB, fontsize=20, va="center")
    save(fig, out)


def draw_end(d, out):
    fig, ax = new_canvas()
    checked = datetime.date.fromisoformat(d["created_at"][:10])
    ax.text(0.5, 0.66, "저장해 두고\n마감 전에 챙기세요", ha="center", va="center", color=TEXT,
            fontsize=56, fontweight="bold", linespacing=1.35)
    ax.text(0.5, 0.50, "매일 아침, 놓치기 쉬운 지원금·마감·할인을\n한 번에 정리해 드려요",
            ha="center", va="center", color=SUB, fontsize=28, linespacing=1.6)
    panel(ax, 0.08, 0.17, 0.84, 0.17)
    ax.text(0.5, 0.255,
            f"{checked.year}.{checked.month:02d}.{checked.day:02d} 공식 안내 기준 정보예요.\n"
            "예산 소진·일정 변경이 있을 수 있으니\n신청 전 공식 홈페이지에서 확인하세요.",
            ha="center", va="center", color=SUB, fontsize=24, linespacing=1.6)
    save(fig, out)


def main(date_str=None):
    setup_font()
    src_dir = ROOT / "data" / "deals"
    src = src_dir / f"{date_str}.json" if date_str else sorted(src_dir.glob("*.json"))[-1]
    d = json.loads(src.read_text(encoding="utf-8"))
    post_date = datetime.date.fromisoformat(d["date"])
    items = d["items"]
    if not 1 <= len(items) <= 5:
        raise SystemExit(f"항목은 1~5개여야 합니다 (현재 {len(items)}개)")

    out_dir = ROOT / "docs" / "cards" / "deals" / d["date"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):  # 다시 만들 때 남은 장수가 섞이지 않게
        old.unlink()
    print(f"카드 생성 → {out_dir}")

    draw_cover(d, post_date, out_dir / "00.png")
    for i, it in enumerate(items, 1):
        draw_item(it, i, len(items), post_date, out_dir / f"{i:02d}.png")
    draw_end(d, out_dir / f"{len(items) + 1:02d}.png")
    print(f"완료: {len(items) + 2}장")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
