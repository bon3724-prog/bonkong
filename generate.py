"""
generate.py — 오늘의 별자리 / 띠별 운세 텍스트 생성

1) 그날의 일진(日辰) 간지를 구한다
2) 일지(日支)와 12띠의 삼합/육합/충 관계를 계산한다  → 매일 달라지는 '근거'
3) 그 근거를 Claude API에 넘겨 운세 문구를 생성한다
4) data/YYYY-MM-DD.json 으로 저장

핵심 아이디어: 그냥 LLM한테 "오늘 운세 써줘" 하면 매일 비슷한 글이 나온다.
일진 기반 관계(합/충)를 계산해서 넣어주면 날마다 논리적으로 다른 결과가 나오고,
양산형/유사문서 판정도 피할 수 있다.
"""

import os
import json
import datetime
import zoneinfo
import pathlib
import anthropic

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


def build_prompt(d: datetime.date, gj: dict) -> str:
    rel_lines = []
    for i, br in enumerate(BRANCHES):
        rel_lines.append(f"- {ANIMALS[i]}띠({br}): {relation(gj['branch'], br)}")
    rels = "\n".join(rel_lines)
    sign_list = ", ".join(name for name, _ in SIGNS)

    return f"""오늘은 {d.year}년 {d.month}월 {d.day}일, 일진은 {gj['full']} 입니다.

아래는 오늘의 일지({gj['branch']})와 12띠의 관계를 명리 규칙으로 계산한 결과입니다.
띠별 운세를 쓸 때 이 관계를 반드시 근거로 삼으세요.

{rels}

다음을 작성해 주세요.

[별자리 운세] {sign_list} — 12개 전부
[띠별 운세] 쥐, 소, 호랑이, 토끼, 용, 뱀, 말, 양, 원숭이, 닭, 개, 돼지 — 12개 전부

작성 규칙:
- 각 항목은 한국어 2문장, 총 55~75자. 반말 아닌 부드러운 존댓말.
- 첫 문장은 오늘의 흐름, 두 번째 문장은 구체적인 행동 조언 하나.
- 띠별은 위 관계(충/합/평)와 결과가 어긋나면 안 됩니다. 충이면 조심, 합이면 순조롭게.
- 겁주거나 단정하지 마세요. 금전 손실, 사고, 질병 같은 불안 유발 표현 금지.
- 매일 반복되는 상투어("좋은 하루 되세요", "긍정적인 마음으로") 금지.
- 12개 항목이 서로 확실히 달라야 합니다.

추가로 아래 항목도 작성:
- headline: 오늘 전체 분위기 한 줄 (20자 이내)
- lucky_color, lucky_number, lucky_item: 각각 짧게

반드시 아래 JSON 형식으로만, 다른 말 없이, 코드블록 없이 응답하세요:
{{"headline":"...","lucky_color":"...","lucky_number":"...","lucky_item":"...",
"signs":{{"물병자리":"...","물고기자리":"...", ...12개 전부}},
"animals":{{"쥐":"...","소":"...", ...12개 전부}}}}"""


def main():
    today = datetime.datetime.now(KST).date()
    gj = day_gapja(today)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=4000,
        temperature=1.0,  # 매일 다른 표현이 나오도록
        messages=[{"role": "user", "content": build_prompt(today, gj)}],
    )

    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(raw)

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
