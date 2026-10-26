"""'놓치면 손해' 초안(data/deals/<게시일>.json) → 세로 릴스 모션그래픽 영상(1080x1920).

장면: 인트로(헤드라인·항목 목록) → 항목별 장면(분류 칩·제목·혜택·대상·D-day 배지·방법·출처) → 마무리
글자·배지가 차례로 등장(아래서 떠오름 / 옆에서 밀려옴 / 튀어나옴)하고, 배경 원이 천천히 움직인다.
음성: edge-tts AI 음성(장면마다 한 번 읽음). 장면 길이는 음성 길이에 맞춘다.

사용법:
  python deals_video.py 2026-10-27            # data/deals/video/2026-10-27.mp4
  python deals_video.py 2026-10-27 --no-voice # 음성 없이
  python deals_video.py 2026-10-27 2026-10-26 --as-of  # 10/27 초안을 10/26 기준(D-day)으로
출력은 공개 저장소에 올리지 않도록 data/deals/video/ 에 둔다(.gitignore 대상 폴더로 관리).
"""
import asyncio
import json
import math
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
W, H, FPS = 1080, 1920, 30
FONT_R, FONT_B = "C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"
BG, PANEL, TEXT, SUB, LINE, ACCENT = "#FFFFFF", "#F6F7F9", "#1F2328", "#5B6470", "#E3E6EA", "#E5484D"
CAT_COLORS = {"지원금": "#12A150", "신청 마감": "#E5484D", "할인": "#F08C00"}
VOICE, RATE = "ko-KR-SunHiNeural", "+8%"
WEEK = "월화수목금토일"
MX = 80          # 좌우 여백
MAXW = W - MX * 2


def rgb(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def font(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT_R, size)


def wrap(text, f, maxw):
    lines, cur = [], ""
    for word in text.split(" "):
        test = (cur + " " + word).strip()
        if f.getlength(test) <= maxw:
            cur = test
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:  # 한 단어가 너무 길면 글자 단위로
            if f.getlength(cur + ch) > maxw:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
    if cur:
        lines.append(cur)
    return lines


def text_layer(text, size, color, bold=False, maxw=MAXW, lh=1.32, align="left"):
    f = font(size, bold)
    lines = wrap(text, f, maxw)
    step = int(size * lh)
    w = int(max(f.getlength(l) for l in lines)) + 4
    lay = Image.new("RGBA", (w, step * len(lines) + int(size * 0.25)), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for i, ln in enumerate(lines):
        x = (w - f.getlength(ln)) / 2 if align == "center" else 0
        d.text((x, i * step), ln, font=f, fill=rgb(color))
    return lay


def chip_layer(text, color, size=40):
    f = font(size, True)
    pw, ph = 30, 14
    w, h = int(f.getlength(text)) + pw * 2, int(size * 1.25) + ph * 2
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=rgb(color))
    d.text((pw, ph - 2), text, font=f, fill=(255, 255, 255, 255))
    return lay


def panel_layer(label, body, color, width=MAXW, body_size=52):
    lab = text_layer(label, 34, color, bold=True)
    bod = text_layer(body, body_size, TEXT, bold=True, maxw=width - 80)
    h = 36 + lab.height + 10 + bod.height + 30
    lay = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, width - 1, h - 1), 32, fill=rgb(PANEL))
    d.rounded_rectangle((0, 0, 14, h - 1), 7, fill=rgb(color))
    lay.alpha_composite(lab, (44, 30))
    lay.alpha_composite(bod, (44, 30 + lab.height + 10))
    return lay


def dday_layer(dday, deadline_txt):
    big = font(120, True)
    small = font(42, True)
    label = "오늘 마감" if dday == 0 else f"D-{dday}"
    w = int(max(big.getlength(label), small.getlength(deadline_txt))) + 120
    h = 300
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 48, fill=rgb(ACCENT))
    d.text(((w - big.getlength(label)) / 2, 22), label, font=big, fill=(255, 255, 255, 255))
    d.text(((w - small.getlength(deadline_txt)) / 2, 200), deadline_txt, font=small, fill=(255, 255, 255, 235))
    return lay


def labeled_line(label, body, color, size=42):
    lab = chip_layer(label, color, size=30)
    bod = text_layer(body, size, TEXT, maxw=MAXW - lab.width - 24)
    h = max(lab.height, bod.height)
    lay = Image.new("RGBA", (MAXW, h), (0, 0, 0, 0))
    lay.alpha_composite(lab, (0, 2))
    lay.alpha_composite(bod, (lab.width + 24, 0))
    return lay


def md(d):  # "2026-10-31" → "10/31(토)"
    y, m, dd = map(int, d.split("-"))
    return f"{m}/{dd}({WEEK[date(y, m, dd).weekday()]})"


# ---------- 장면 구성 ----------
# 요소: (레이어, x, y, 등장 시각(초), 효과)  효과: up / left / pop

def intro_scene(data, pub):
    els, y = [], 300
    kicker = chip_layer("오늘 놓치면 손해", ACCENT, 44)
    els.append((kicker, MX, y, 0.1, "left")); y += kicker.height + 40
    when = text_layer(f"{pub.month}월 {pub.day}일({WEEK[pub.weekday()]}) 확인", 40, SUB)
    els.append((when, MX, y, 0.3, "up")); y += when.height + 30
    head = text_layer(data["headline"], 96, TEXT, bold=True)
    els.append((head, MX, y, 0.45, "up")); y += head.height + 70
    for i, it in enumerate(data["items"]):
        row = Image.new("RGBA", (MAXW, 120), (0, 0, 0, 0))
        d = ImageDraw.Draw(row)
        d.rounded_rectangle((0, 0, MAXW - 1, 119), 30, fill=rgb(PANEL))
        c = rgb(CAT_COLORS.get(it["category"], ACCENT))
        d.ellipse((34, 42, 70, 78), fill=c)
        t = it["title"] if len(it["title"]) <= 16 else it["title"][:15] + "…"
        d.text((96, 28), t, font=font(50, True), fill=rgb(TEXT))
        els.append((row, MX, y, 0.9 + i * 0.25, "left")); y += 145
    tail = text_layer("끝까지 보고 저장해 두세요", 40, SUB)
    els.append((tail, MX, y + 30, 1.8, "up"))
    narr = f"오늘 놓치면 손해 보는 정보, {data['headline']}입니다."
    return {"els": els, "narration": narr, "accent": ACCENT}


def item_scene(it, idx, total, pub):
    color = CAT_COLORS.get(it["category"], ACCENT)
    els, y = [], 150
    els.append((text_layer(f"{idx} / {total}", 34, SUB), MX, y, 0.0, "up")); y += 70
    chip = chip_layer(it["category"], color, 42)
    els.append((chip, MX, y, 0.1, "left")); y += chip.height + 30
    title = text_layer(it["title"], 80, TEXT, bold=True)
    els.append((title, MX, y, 0.3, "up")); y += title.height + 40
    ben = panel_layer("혜택", it["benefit"], color)
    els.append((ben, MX, y, 0.6, "pop")); y += ben.height + 40
    who = labeled_line("대상", it["who"], SUB)
    els.append((who, MX, y, 0.9, "up")); y += who.height + 30
    how = labeled_line("방법", it["how"], SUB)
    els.append((how, MX, y, 1.1, "up")); y += how.height + 50
    dd = (date.fromisoformat(it["deadline"]) - pub).days
    badge = dday_layer(dd, f"{md(it['deadline'])} 마감")
    els.append((badge, (W - badge.width) // 2, y, 1.4, "pop")); y += badge.height + 26
    if it.get("deadline_note"):
        note = text_layer(it["deadline_note"], 40, ACCENT, bold=True, align="center")
        els.append((note, (W - note.width) // 2, y, 1.7, "up"))
    src = text_layer(f"출처: {it['source_name']} · {it.get('checked', '')[:10]} 확인", 28, "#9AA0A6", maxw=MAXW)
    els.append((src, MX, H - 150, 1.0, "up"))
    m, d_ = map(int, it["deadline"].split("-")[1:])
    narr = f"{idx}번, {it['title']}. {it['benefit']}. {m}월 {d_}일까지예요. {it.get('deadline_note', '')}"
    return {"els": els, "narration": narr, "accent": color}


def outro_scene():
    els = []
    head = text_layer("저장해 두고\n놓치지 마세요".replace("\n", " "), 96, TEXT, bold=True, maxw=700, align="center")
    els.append((head, (W - head.width) // 2, 640, 0.1, "pop"))
    line = Image.new("RGBA", (140, 12), (0, 0, 0, 0))
    ImageDraw.Draw(line).rounded_rectangle((0, 0, 139, 11), 6, fill=rgb(ACCENT))
    els.append((line, (W - 140) // 2, 640 + head.height + 30, 0.4, "left"))
    note = text_layer("마감일·금액은 공식 페이지에서 꼭 확인하세요", 42, SUB, align="center", maxw=880)
    els.append((note, (W - note.width) // 2, 640 + head.height + 90, 0.6, "up"))
    narr = "마감일과 금액은 공식 페이지에서 꼭 확인하세요. 저장해 두고 놓치지 마세요."
    return {"els": els, "narration": narr, "accent": ACCENT}


# ---------- 음성 ----------

async def _tts(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


# ---------- 렌더링 ----------

def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_back(x):  # 살짝 튀어나왔다 돌아옴
    x = min(max(x, 0.0), 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def with_alpha(img, a):
    if a >= 1:
        return img
    out = img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * a)))
    return out


def background(t, accent):
    bg = Image.new("RGBA", (W, H), rgb(BG))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    cx = W * 0.85 + 60 * math.sin(t * 0.6)
    cy = H * 0.12 + 40 * math.cos(t * 0.5)
    d.ellipse((cx - 330, cy - 330, cx + 330, cy + 330), fill=rgb(accent, 34))
    cx2 = W * 0.1 + 50 * math.cos(t * 0.4)
    cy2 = H * 0.9 + 50 * math.sin(t * 0.55)
    d.ellipse((cx2 - 260, cy2 - 260, cx2 + 260, cy2 + 260), fill=rgb(accent, 22))
    bg.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)))
    return bg


def render_scene_frame(sc, lt, span, t, total):
    frame = background(t, sc["accent"])
    out_a = 1 - ease_out((lt - (span - 0.3)) / 0.3) if lt > span - 0.3 else 1.0  # 장면 끝 페이드아웃
    for lay, x, y, start, fx in sc["els"]:
        p = (lt - start) / 0.45
        if p <= 0:
            continue
        a = ease_out(p) * out_a
        if fx == "up":
            frame.alpha_composite(with_alpha(lay, a), (int(x), int(y + (1 - ease_out(p)) * 50)))
        elif fx == "left":
            frame.alpha_composite(with_alpha(lay, a), (int(x - (1 - ease_out(p)) * 140), int(y)))
        else:  # pop
            k = 0.6 + 0.4 * ease_back(p)
            im = lay.resize((max(1, int(lay.width * k)), max(1, int(lay.height * k))), Image.BILINEAR)
            frame.alpha_composite(with_alpha(im, a),
                                  (int(x + (lay.width - im.width) / 2), int(y + (lay.height - im.height) / 2)))
    ImageDraw.Draw(frame).rectangle((0, 0, int(W * t / total), 10), fill=rgb(sc["accent"]))
    return frame.convert("RGB")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src_day = date.fromisoformat(args[0]) if args else date.today()
    # --as-of YYYY-MM-DD: 다른 날 초안을 이 날짜 기준(표시 날짜·D-day)으로 렌더링
    pub = date.fromisoformat(args[1]) if len(args) > 1 and "--as-of" in sys.argv else src_day
    voice = "--no-voice" not in sys.argv
    data = json.loads((BASE / "data" / "deals" / f"{src_day}.json").read_text(encoding="utf-8"))
    data["items"] = [it for it in data["items"] if date.fromisoformat(it["deadline"]) >= pub]
    outdir = BASE / "data" / "deals" / "video"
    work = outdir / f"_{pub}"
    work.mkdir(parents=True, exist_ok=True)

    scenes = [intro_scene(data, pub)]
    scenes += [item_scene(it, i, len(data["items"]), pub) for i, it in enumerate(data["items"], 1)]
    scenes.append(outro_scene())

    # 장면 길이 = 음성 길이 + 여유
    starts, t = [], 0.0
    for i, sc in enumerate(scenes):
        sc["audio"] = None
        if voice:
            p = work / f"v{i}.mp3"
            asyncio.run(_tts(sc["narration"], p))
            sc["audio"], ad = p, dur(p)
        else:
            ad = 0
        min_len = 4.0 if 0 < i < len(scenes) - 1 else 3.2
        sc["span"] = max(ad + 1.0, min_len)
        starts.append(t)
        t += sc["span"]
    total = t

    silent = work / "video.mp4"
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                             "-preset", "medium", "-crf", "20", str(silent)], stdin=subprocess.PIPE)
    n = int(total * FPS)
    for f in range(n):
        tt = f / FPS
        i = max(k for k, s in enumerate(starts) if s <= tt)
        proc.stdin.write(render_scene_frame(scenes[i], tt - starts[i], scenes[i]["span"], tt, total).tobytes())
        if f % (FPS * 5) == 0:
            print(f"  렌더링 {tt:4.1f}s / {total:.1f}s")
    proc.stdin.close()
    proc.wait()

    out = outdir / f"{pub}.mp4"
    if voice:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent)]
        parts = []
        for k, sc in enumerate(scenes):
            cmd += ["-i", str(sc["audio"])]
            ms = int((starts[k] + 0.35) * 1000)
            parts.append(f"[{k + 1}:a]adelay={ms}|{ms}[a{k}]")
        mix = "".join(f"[a{k}]" for k in range(len(scenes)))
        fc = ";".join(parts) + f";{mix}amix=inputs={len(scenes)}:normalize=0[aout]"
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac",
                "-b:a", "160k", "-shortest", str(out)]
        subprocess.run(cmd, check=True)
    else:
        silent.replace(out)
    print(f"완료: {out}  ({total:.1f}초, 장면 {len(scenes)}개)")


if __name__ == "__main__":
    main()
