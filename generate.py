"""
generate.py — 오늘의 별자리 / 띠별 운세 텍스트 생성

1) 그날의 일진(日辰) 간지를 구한다
2) 일지(日支)와 12띠의 삼합/육합/충 관계를 계산한다
3) 날짜와 관계에 맞는 문구를 조합한다
4) data/YYYY-MM-DD.json 으로 저장

핵심 아이디어: 그냥 LLM한테 "오늘 운세 써줘" 하면 매일 비슷한 글이 나온다.
일진 기반 관계(합/충)를 계산해서 넣어주면 날마다 논리적으로 다른 결과가 나오고,
양산형/유사문서 판정도 피할 수 있다.
"""

import json
import datetime
import zoneinfo
import pathlib

KST = zoneinfo.ZoneInfo("Asia/Seoul")
OUT_DIR = pathlib.Path(__file__).parent / "data"

BRANCHES = ["자", "축", "인", "묘", "진", "사", "오", "미", "신", "유", "술", "해"]
ANIMALS = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"]

# 12지 관계
SAMHAP = [{"신", "자", "진"}, {"해", "묘", "미"}, {"인", "오", "술"}, {"사", "유", "축"}]
YUKHAP = [{"자", "축"}, {"인", "해"}, {"묘", "술"}, {"진", "유"}, {"사", "신"}, {"오", "미"}]
CHUNG = [{"자", "오"}, {"축", "미"}, {"인", "신"}, {"묘", "유"}, {"진", "술"}, {"사", "해"}]

SIGNS = [
    ("물병자리", "1.20~2.18"), ("물고기자리", "2.19~3.20"),
    ("양자리", "3.21~4.19"), ("황소자리", "4.20~5.20"),
    ("쌍둥이자리", "5.21~6.21"), ("게자리", "6.22~7.22"),
    ("사자자리", "7.23~8.22"), ("처녀자리", "8.23~9.22"),
    ("천칭자리", "9.23~10.22"), ("전갈자리", "10.23~11.22"),
    ("사수자리", "11.23~12.21"), ("염소자리", "12.22~1.19"),
]


def day_gapja(d: datetime.date) -> dict:
    """그날의 일진(천간+지지)을 구한다.

    korean_lunar_calendar 라이브러리 사용. 설치: pip install korean-lunar-calendar
    ⚠️ 첫 실행 시 네이버 만세력에서 같은 날짜를 조회해 결과가 일치하는지 반드시 확인할 것.
    """
    from korean_lunar_calendar import KoreanLunarCalendar

    cal = KoreanLunarCalendar()
    cal.setSolarDate(d.year, d.month, d.day)
    gapja = cal.getGapJaString()  # 예: '병오년 정유월 갑진일'
    day_token = [t for t in gapja.split() if t.endswith("일")][0]
    day_token = day_token.replace("일", "")  # '갑진'
    stem, branch = day_token[0], day_token[1]
    return {"full": gapja, "day": day_token, "stem": stem, "branch": branch}


def relation(day_branch: str, target: str) -> str:
    """일지와 특정 띠 지지의 관계를 판정한다."""
    if day_branch == target:
        return "복음(같은 기운, 힘이 겹침)"
    for s in CHUNG:
        if {day_branch, target} == s:
            return "충(부딪힘, 변동수)"
    for s in YUKHAP:
        if {day_branch, target} == s:
            return "육합(조화, 인연운)"
    for s in SAMHAP:
        if day_branch in s and target in s:
            return "삼합(협력, 일이 풀림)"
    return "평(무난)"


SIGN_FLOWS = [
    "새로운 흐름이 천천히 자리를 잡습니다.",
    "작은 변화가 하루의 분위기를 바꿉니다.",
    "미뤄둔 일에 다시 속도가 붙습니다.",
    "주변의 제안에서 실마리를 찾습니다.",
    "차분히 고른 선택이 좋은 방향으로 이어집니다.",
    "익숙한 일에서 뜻밖의 재미를 발견합니다.",
]
SIGN_ACTIONS = [
    "오전에 가장 중요한 일 하나를 먼저 정리해 보세요.",
    "연락을 미룬 사람에게 짧게 안부를 전해 보세요.",
    "일정 사이에 십 분의 여유를 남겨 두세요.",
    "눈에 띄는 아이디어는 메모해 두면 좋습니다.",
    "결정 전 장단점을 한 번씩 적어 보세요.",
    "작은 정리부터 시작하면 집중하기 쉽습니다.",
]

ANIMAL_LINES = {
    "충": [
        "오늘은 속도를 조금 낮추면 흐름을 안정적으로 다룰 수 있습니다.",
        "중요한 결정은 한 번 더 확인하고 여유 있게 움직여 보세요.",
    ],
    "합": [
        "주변과 호흡이 잘 맞아 협력할수록 기회가 커지는 날입니다.",
        "혼자 정하기보다 믿을 만한 사람과 의견을 나눠 보세요.",
    ],
    "평": [
        "무리한 변화보다 하던 일을 고르게 이어가기 좋은 날입니다.",
        "작은 목표 하나를 정해 끝까지 마무리해 보세요.",
    ],
}

LUCKY_COLORS = ["청록", "연보라", "살구색", "짙은 초록", "하늘색", "코랄"]
LUCKY_ITEMS = ["금속 펜", "작은 노트", "손수건", "책갈피", "머그컵", "헤어핀"]


def build_template_data(d: datetime.date, gj: dict) -> dict:
    """외부 API 없이 날짜와 일진을 바탕으로 카드용 문구를 만든다."""
    seed = d.toordinal() + BRANCHES.index(gj["branch"])
    signs = {
        name: f"{SIGN_FLOWS[(seed + i) % len(SIGN_FLOWS)]} "
        f"{SIGN_ACTIONS[(seed + i * 2) % len(SIGN_ACTIONS)]}"
        for i, (name, _) in enumerate(SIGNS)
    }

    animals = {}
    for i, animal in enumerate(ANIMALS):
        label = relation(gj["branch"], BRANCHES[i]).split("(", 1)[0]
        kind = "충" if label.startswith("충") else "합" if "합" in label else "평"
        lines = ANIMAL_LINES[kind]
        animals[animal] = f"{lines[0]} {lines[1]}"

    return {
        "headline": ["차분한 선택이 빛나는 날", "작은 변화가 흐름을 엽니다", "협력에서 답을 찾는 날"][seed % 3],
        "lucky_color": LUCKY_COLORS[seed % len(LUCKY_COLORS)],
        "lucky_number": str(seed % 9 + 1),
        "lucky_item": LUCKY_ITEMS[seed % len(LUCKY_ITEMS)],
        "signs": signs,
        "animals": animals,
    }


def main():
    today = datetime.datetime.now(KST).date()
    gj = day_gapja(today)

    data = build_template_data(today, gj)

    # 12개씩 다 왔는지 검증 — 빠지면 카드가 깨지므로 여기서 죽이는 게 낫다
    assert len(data["signs"]) == 12, f"별자리 {len(data['signs'])}개만 생성됨"
    assert len(data["animals"]) == 12, f"띠 {len(data['animals'])}개만 생성됨"

    data["date"] = today.isoformat()
    data["gapja"] = gj["full"]
    data["day_gapja"] = gj["day"]
    data["relations"] = {ANIMALS[i]: relation(gj["branch"], br)
                         for i, br in enumerate(BRANCHES)}

    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"{today.isoformat()}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"생성 완료: {path}")
    print(f"일진: {gj['full']} / {data['headline']}")


if __name__ == "__main__":
    main()
