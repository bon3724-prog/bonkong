"""
cards.py — 운세 JSON을 카드 이미지 7장으로 렌더링

출력: docs/cards/YYYY-MM-DD/00.png ~ 06.png  (1080x1350, 4:5)
  00 커버 (날짜 + 일진 + 헤드라인 + 행운 아이템)
  01~03 별자리 4개씩
  04~06 띠 4개씩

인스타 캐러셀 API 한도가 10장이라 7장으로 맞췄다.
4:5(1080x1350)가 피드에서 가장 넓은 면적을 차지한다.
"""

import json
import sys
import pathlib
import textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = pathlib.Path(__file__).parent
W, H = 1080, 1350
DPI = 100

# ── 색상 팔레트 (밤하늘 톤) ───────────────────────────────
BG = "#141225"
BG_ALT = "#1C1930"
ACCENT = "#E8C56B"   # 금색
TEXT = "#F2EFE6"
SUB = "#9A93B5"

SIGN_ICONS = {
    "물병자리": "♒", "물고기자리": "♓", "양자리": "♈", "황소자리": "♉",
    "쌍둥이자리": "♊", "게자리": "♋", "사자자리": "♌", "처녀자리": "♍",
    "천칭자리": "♎", "전갈자리": "♏", "사수자리": "♐", "염소자리": "♑",
}


def setup_font():
    """한글 폰트 등록. GitHub Actions에서는 fonts-nanum 설치 필요."""
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/malgun.ttf",
    ]
    for p in candidates:
        if pathlib.Path(p).exists():
            font_manager.fontManager.addfont(p)
            name = font_manager.FontProperties(fname=p).get_name()
            plt.rcParams["font.family"] = name
            return name
    raise SystemExit(
        "한글 폰트를 찾을 수 없습니다.\n"
        "  Ubuntu: sudo apt-get install -y fonts-nanum\n"
        "  Windows: 맑은 고딕이 기본 설치되어 있어야 합니다."
    )


def new_canvas(alt=False):
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor(BG_ALT if alt else BG)
    return fig, ax


def save(fig, path):
    fig.savefig(path, facecolor=fig.get_facecolor(), dpi=DPI)
    plt.close(fig)
    print(f"  {path.name}")


def draw_cover(d, out):
    fig, ax = new_canvas()
    ax.text(0.5, 0.80, "오늘의 운세", ha="center", color=ACCENT,
            fontsize=54, fontweight="bold")
    ax.text(0.5, 0.73, d["date"].replace("-", "."), ha="center", color=SUB, fontsize=30)
    ax.plot([0.25, 0.75], [0.68, 0.68], color=ACCENT, lw=1.5, alpha=0.5)
    ax.text(0.5, 0.60, d["gapja"], ha="center", color=TEXT, fontsize=34)

    head = "\n".join(textwrap.wrap(d["headline"], 12))
    ax.text(0.5, 0.45, head, ha="center", va="center", color=TEXT,
            fontsize=46, fontweight="bold", linespacing=1.5)

    lucky = (f"행운의 색  {d['lucky_color']}      "
             f"행운의 숫자  {d['lucky_number']}\n"
             f"행운의 아이템  {d['lucky_item']}")
    ax.text(0.5, 0.22, lucky, ha="center", va="center", color=SUB,
            fontsize=26, linespacing=2.0)
    ax.text(0.5, 0.07, "재미로 보는 운세입니다", ha="center", color=SUB,
            fontsize=18, alpha=0.6)
    save(fig, out)


def draw_items(title, items, out, alt=False, icons=None, rels=None):
    """4개 항목을 한 장에 배치."""
    fig, ax = new_canvas(alt=alt)
    ax.text(0.5, 0.93, title, ha="center", color=ACCENT,
            fontsize=38, fontweight="bold")

    slots = [0.755, 0.545, 0.335, 0.125]
    for (name, body), y in zip(items, slots):
        label = f"{icons.get(name, '')} {name}".strip() if icons else name
        ax.text(0.08, y + 0.075, label, color=TEXT, fontsize=32, fontweight="bold")

        if rels and name in rels:
            tag = rels[name].split("(")[0]
            ax.text(0.92, y + 0.078, tag, ha="right", color=ACCENT,
                    fontsize=22, alpha=0.85)

        wrapped = "\n".join(textwrap.wrap(body, 26))
        ax.text(0.08, y + 0.035, wrapped, color=SUB, fontsize=24,
                va="top", linespacing=1.7)
        ax.plot([0.08, 0.92], [y - 0.055, y - 0.055], color=SUB, lw=0.8, alpha=0.25)
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
    print(f"카드 생성 → {out_dir}")

    draw_cover(d, out_dir / "00.png")

    signs = list(d["signs"].items())
    for i in range(3):
        draw_items(f"별자리 운세 {i+1}/3", signs[i*4:(i+1)*4],
                   out_dir / f"{i+1:02d}.png", alt=(i % 2 == 1), icons=SIGN_ICONS)

    animals = list(d["animals"].items())
    for i in range(3):
        draw_items(f"띠별 운세 {i+1}/3", animals[i*4:(i+1)*4],
                   out_dir / f"{i+4:02d}.png", alt=(i % 2 == 0),
                   rels=d.get("relations"))

    print("완료: 7장")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
