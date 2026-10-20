"""
cards.py — 띠별 운세 JSON을 카드 이미지 7장으로 렌더링

출력: docs/cards/YYYY-MM-DD/00.png ~ 06.png  (1080x1350, 4:5)
  00 커버 (날짜 + 일진 + 헤드라인 + 오늘 운 좋은 띠 + 행운 아이템)
  01~06 띠 2개씩 (출생연도 + 총운 + 애정운·금전운·사업운 별점)

인스타 캐러셀 API 한도가 10장이라 7장으로 맞췄다.
4:5(1080x1350)가 피드에서 가장 넓은 면적을 차지한다.
휴대폰에서 읽히도록 본문 글씨는 40px 이상, 밝은 배경에 진한 글씨로 그린다.
"""

import json
import sys
import pathlib
import datetime
import textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

ROOT = pathlib.Path(__file__).parent
W, H = 1080, 1350
DPI = 100

# ── 색상 팔레트 (밝은 한지 톤) ─────────────────────────────
BG = "#FBF6EC"
CARD = "#FFFFFF"
TEXT = "#1F1B2E"
SUB = "#6B6478"
ACCENT = "#C8402F"   # 주홍
GOLD = "#E0A526"     # 별
LINE = "#E6DDCB"

CATEGORIES = ["애정운", "금전운", "사업운"]
CAT_COLORS = {"애정운": "#D9476B", "금전운": "#C98A0B", "사업운": "#2F6FB2"}

FONT_REG = None
FONT_BOLD = None


def setup_font():
    """한글 폰트 등록. GitHub Actions에서는 fonts-nanum 설치 필요."""
    global FONT_REG, FONT_BOLD
    pairs = [
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
         "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf"),
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
         "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"),
    ]
    for reg, bold in pairs:
        if pathlib.Path(reg).exists() and pathlib.Path(bold).exists():
            FONT_REG = font_manager.FontProperties(fname=reg)
            FONT_BOLD = font_manager.FontProperties(fname=bold)
            return
    raise SystemExit(
        "한글 폰트를 찾을 수 없습니다.\n"
        "  Ubuntu: sudo apt-get install -y fonts-nanum\n"
        "  Windows: 맑은 고딕이 기본 설치되어 있어야 합니다."
    )


def px(size):
    """픽셀 크기 → matplotlib 포인트."""
    return size * 72 / DPI


def text(ax, x, y, s, size, color=TEXT, bold=False, **kw):
    kw.setdefault("va", "top")
    return ax.text(x, y, s, fontsize=px(size), color=color,
                   fontproperties=FONT_BOLD if bold else FONT_REG, **kw)


def new_canvas():
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)  # 위에서 아래로 픽셀 좌표
    ax.axis("off")
    fig.patch.set_facecolor(BG)
    return fig, ax


def box(ax, x, y, w, h, color=CARD, r=28, edge=LINE):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                facecolor=color, edgecolor=edge, lw=2))


def save(fig, path):
    fig.savefig(path, facecolor=fig.get_facecolor(), dpi=DPI)
    plt.close(fig)
    print(f"  {path.name}")


def date_label(d):
    day = datetime.date.fromisoformat(d["date"])
    week = "월화수목금토일"[day.weekday()]
    return f"{day.month}월 {day.day}일 ({week})"


def years_label(years):
    return " · ".join(f"{y % 100:02d}" for y in years) + "년생"


def stars(n):
    return "★" * n + "☆" * (5 - n)


def draw_cover(d, out):
    fig, ax = new_canvas()
    text(ax, W / 2, 120, "오늘의 띠별 운세", 84, ACCENT, bold=True, ha="center")
    text(ax, W / 2, 245, date_label(d), 50, TEXT, bold=True, ha="center")
    text(ax, W / 2, 320, d["gapja"], 40, SUB, ha="center")

    box(ax, 80, 420, W - 160, 200)
    head = "\n".join(textwrap.wrap(d["headline"], 14))
    text(ax, W / 2, 520, head, 58, TEXT, bold=True, ha="center", va="center",
         linespacing=1.3)

    text(ax, W / 2, 680, "오늘 운 좋은 띠", 44, SUB, bold=True, ha="center")
    best = "  ·  ".join(f"{a}띠" for a in d["best"])
    text(ax, W / 2, 750, best, 66, ACCENT, bold=True, ha="center")

    box(ax, 80, 900, W - 160, 250)
    rows = [("행운의 색", d["lucky_color"]), ("행운의 숫자", d["lucky_number"]),
            ("행운의 아이템", d["lucky_item"])]
    for k, (label, val) in enumerate(rows):
        y = 935 + k * 72
        text(ax, 140, y, label, 44, SUB, bold=True)
        text(ax, W - 140, y, val, 44, TEXT, bold=True, ha="right")

    text(ax, W / 2, 1210, "넘겨서 내 띠 확인하기  →", 44, TEXT, bold=True, ha="center")
    text(ax, W / 2, 1285, "재미로 보는 운세 · 설 이전 1~2월생은 앞 띠예요", 30, SUB,
         ha="center")
    save(fig, out)


def draw_animal(ax, name, a, top):
    """띠 하나를 카드 한 칸(높이 570)에 그린다."""
    box(ax, 50, top, W - 100, 570)
    text(ax, 100, top + 40, f"{name}띠", 76, TEXT, bold=True)
    # 합/충 태그
    tag_color = ACCENT if a["relation"] == "충" else "#2E8B57" if "합" in a["relation"] else SUB
    text(ax, W - 100, top + 62, a["tag"], 36, tag_color, bold=True, ha="right")
    text(ax, 100, top + 140, years_label(a["years"]), 42, SUB, bold=True)

    fit_text(ax, 100, top + 210, a["overall"], 46, W - 85, bold=True)

    for k, cat in enumerate(CATEGORIES):
        y = top + 330 + k * 76
        info = a[cat]
        text(ax, 100, y, cat, 40, CAT_COLORS[cat], bold=True)
        text(ax, 245, y + 2, stars(info["stars"]), 36, GOLD)
        fit_text(ax, 450, y, info["text"], 38, W - 85)


def fit_text(ax, x, y, s, size, right, bold=False):
    """오른쪽 끝(right px)을 넘으면 넘지 않을 때까지 글씨를 줄인다."""
    t = text(ax, x, y, s, size, TEXT, bold=bold)
    renderer = ax.figure.canvas.get_renderer()
    while size > 28:
        bb = t.get_window_extent(renderer)
        if bb.x1 <= right:
            break
        size -= 2
        t.set_fontsize(px(size))
    return t


def draw_pair(d, names, page, out):
    fig, ax = new_canvas()
    text(ax, 60, 45, date_label(d) + " 띠별 운세", 40, ACCENT, bold=True)
    text(ax, W - 60, 45, f"{page}/6", 40, SUB, bold=True, ha="right")
    draw_animal(ax, names[0], d["animals"][names[0]], 130)
    draw_animal(ax, names[1], d["animals"][names[1]], 730)
    save(fig, out)


def main(date_str=None):
    setup_font()
    data_dir = ROOT / "data"
    if date_str:
        src = data_dir / f"{date_str}.json"
    else:
        src = sorted(data_dir.glob("*.json"))[-1]
    d = json.loads(src.read_text(encoding="utf-8"))

    out_dir = ROOT / "docs" / "cards" / d["date"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()
    print(f"카드 생성 → {out_dir}")

    draw_cover(d, out_dir / "00.png")

    names = list(d["animals"])
    for i in range(6):
        draw_pair(d, names[i * 2:i * 2 + 2], i + 1, out_dir / f"{i + 1:02d}.png")

    print("완료: 7장")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
