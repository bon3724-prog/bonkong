"""
generate.py — 오늘의 띠별 운세 텍스트 생성 (총운 + 애정운·금전운·사업운)

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


BIRTH_RANGE = range(1950, 2014)  # 카드에 표시할 출생연도 범위

# 관계별 총운 (관계 판정과 어긋나지 않게 관계마다 따로 쓴다)
OVERALL = {
    "육합": ["인연운이 활짝, 사람이 복을 데려와요",
             "누군가와 손잡으면 일이 쉬워지는 날",
             "좋은 소식이 사람을 통해 들어와요"],
    "삼합": ["협력할수록 일이 술술 풀리는 날",
             "주변의 도움으로 막힌 일이 뚫려요",
             "함께하는 일에 행운이 따라요"],
    "복음": ["같은 기운이 겹쳐 힘이 세지는 날",
             "자신감은 살리되 고집은 내려놓아요",
             "하던 일에 힘이 실려요, 과욕은 금물"],
    "충": ["변동이 많은 날, 속도를 낮춰요",
           "부딪힘이 생겨도 한 박자 쉬면 괜찮아요",
           "중요한 결정은 하루 미루는 게 좋아요"],
    "평": ["무난하고 차분하게 흘러가는 하루",
           "평소 리듬을 지키면 좋은 날",
           "작은 목표 하나를 끝내 보세요",
           "큰 일 없이 편안한 흐름이에요"],
}

TAGS = {"육합": "육합 · 인연운", "삼합": "삼합 · 협력운", "복음": "복음 · 기운 겹침",
        "충": "충 · 변동 주의", "평": "평 · 무난"}

CATEGORIES = ["애정운", "금전운", "사업운"]

# 분야별 문구: good(별 4~5) / mid(별 3) / care(별 1~2)
LINES = {
    "애정운": {
        "good": ["마음 표현이 잘 통하는 날", "먼저 건넨 연락이 반가움으로",
                 "솔로라면 소개 자리에 나가 보세요", "연인과 대화가 술술 풀려요",
                 "작은 선물이 큰 감동이 돼요", "새 인연이 가까이 와 있어요"],
        "mid": ["평소처럼 다정하면 충분해요", "가벼운 안부가 관계를 지켜요",
                "서두르지 말고 천천히 다가가요", "함께 밥 한 끼가 좋은 날",
                "상대 이야기를 먼저 들어 주세요", "무난하고 편안한 하루예요"],
        "care": ["말 한마디에 오해가 생길 수 있어요", "예민한 주제는 내일로 미뤄요",
                 "기대를 낮추면 서운함도 줄어요", "감정보다 사실로 이야기해요",
                 "혼자만의 시간이 약이 돼요", "지난 일은 꺼내지 않는 게 좋아요"],
    },
    "금전운": {
        "good": ["뜻밖의 수입이 들어올 수 있어요", "미뤄둔 정산을 받기 좋은 날",
                 "알뜰한 선택이 이득으로 돌아와요", "재테크 공부가 결실을 보는 날",
                 "작은 투자 아이디어를 메모해요", "지갑이 든든해지는 흐름이에요"],
        "mid": ["들어온 만큼 나가는 하루예요", "계획한 지출만 지키면 무난해요",
                "가계부 정리하기 좋은 날", "할인보다 필요한지 먼저 따져요",
                "큰 변동 없이 안정적이에요", "고정비를 한 번 점검해 보세요"],
        "care": ["충동구매를 조심하세요", "돈 빌려주는 일은 피하세요",
                 "큰 결제는 하루 미뤄요", "계약서는 꼼꼼히 확인해요",
                 "새는 돈이 없는지 살펴보세요", "투자 결정은 오늘 쉬어 가요"],
    },
    "사업운": {
        "good": ["제안서·미팅에 힘이 실려요", "협업 상대와 호흡이 척척 맞아요",
                 "윗사람에게 인정받기 좋은 날", "새 거래처와 인연이 닿아요",
                 "밀린 일이 한 번에 풀려요", "아이디어를 꺼내면 반응이 좋아요"],
        "mid": ["하던 일을 꾸준히 이어가요", "오전에 중요한 일을 끝내 두세요",
                "작은 성과를 차곡차곡 쌓는 날", "일정 정리만 잘해도 충분해요",
                "확인 메일 한 통이 실수를 막아요", "무리한 확장보다 내실을 다져요"],
        "care": ["계약·결재는 한 번 더 확인해요", "말 바뀌는 상대를 조심하세요",
                 "일정이 꼬일 수 있으니 여유를", "급한 결정보다 보류가 나아요",
                 "문서 실수에 주의하세요", "감정 섞인 회의는 피하세요"],
    },
}

# 관계별 기본 별점과 범위 — 합은 3~5, 충은 1~3으로 묶어 판정과 어긋나지 않게 한다
BASE = {"육합": 4, "삼합": 4, "복음": 3, "평": 3, "충": 2}
CLAMP = {"육합": (3, 5), "삼합": (3, 5), "복음": (2, 4), "평": (2, 4), "충": (1, 3)}
BONUS = {"육합": "애정운", "삼합": "사업운"}  # 육합은 인연, 삼합은 협력이 강점

LUCKY_COLORS = ["청록", "연보라", "살구색", "짙은 초록", "하늘색", "코랄"]
LUCKY_ITEMS = ["금속 펜", "작은 노트", "손수건", "책갈피", "머그컵", "헤어핀"]


def birth_years(i: int) -> list:
    """i번째 띠(쥐=0)의 출생연도. 띠는 양력 연도 기준(설·입춘 전 출생은 앞 띠)."""
    return [y for y in BIRTH_RANGE if (y - 4) % 12 == i]


def build_template_data(d: datetime.date, gj: dict) -> dict:
    """외부 API 없이 날짜와 일진(합/충 판정)을 바탕으로 카드용 문구를 만든다."""
    seed = d.toordinal() + BRANCHES.index(gj["branch"])

    animals = {}
    for i, animal in enumerate(ANIMALS):
        kind = relation(gj["branch"], BRANCHES[i]).split("(", 1)[0]
        pool = OVERALL[kind]
        entry = {
            "years": birth_years(i),
            "relation": kind,
            "tag": TAGS[kind],
            "overall": pool[(seed + i) % len(pool)],
        }
        for c, cat in enumerate(CATEGORIES):
            jitter = (seed * 31 + i * 17 + c * 13) % 3 - 1  # 날마다 -1/0/+1
            score = BASE[kind] + jitter + (1 if BONUS.get(kind) == cat else 0)
            lo, hi = CLAMP[kind]
            score = max(lo, min(hi, score))
            level = "good" if score >= 4 else "mid" if score == 3 else "care"
            lines = LINES[cat][level]
            entry[cat] = {"stars": score,
                          "text": lines[(seed + i * 5 + c * 7) % len(lines)]}
        entry["total"] = sum(entry[cat]["stars"] for cat in CATEGORIES)
        animals[animal] = entry

    best = sorted(ANIMALS, key=lambda a: -animals[a]["total"])[:3]
    return {
        "headline": ["차분한 선택이 빛나는 날", "작은 변화가 흐름을 엽니다", "협력에서 답을 찾는 날"][seed % 3],
        "lucky_color": LUCKY_COLORS[seed % len(LUCKY_COLORS)],
        "lucky_number": str(seed % 9 + 1),
        "lucky_item": LUCKY_ITEMS[seed % len(LUCKY_ITEMS)],
        "best": best,
        "animals": animals,
    }


def main():
    today = datetime.datetime.now(KST).date()
    gj = day_gapja(today)

    data = build_template_data(today, gj)

    # 12개씩 다 왔는지 검증 — 빠지면 카드가 깨지므로 여기서 죽이는 게 낫다
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
