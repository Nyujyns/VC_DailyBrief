import anthropic
import json
import os
import shutil
from datetime import datetime, timezone, timedelta

# ── 설정 ──
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
date_str = today.strftime('%Y.%m.%d')
date_iso = today.strftime('%Y-%m-%d')
day_names = ['월', '화', '수', '목', '금', '토', '일']
day_str = day_names[today.weekday()]

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ══════════════════════════════════════════════════════════════
# PHASE 1: 웹 검색으로 최신 뉴스 수집
# ══════════════════════════════════════════════════════════════

COLLECT_SYSTEM = f"""너는 한국 VC 심사역을 위한 뉴스 수집 전문 리서처야.
오늘은 {date_iso} ({day_str})이다.

목표: 최근 24~72시간 이내의 스타트업/VC/테크 뉴스를 웹 검색으로 수집해서 정리해라.

수집 카테고리:

1. 한국 스타트업 투자 딜 (바이오/헬스케어 완전 제외)
   - 시드/프리시드 포함, 금액 비공개도 포함
   - 전수 수집 목표 (빠짐없이)
   - 검색 키워드 예: "스타트업 투자", "시리즈A", "시드 투자", "VC 투자" + 최근 날짜

2. 글로벌 주요 VC 딜
   - $200M 이상 대형 딜
   - $200M 미만이라도 주목할 섹터(AI, 로보틱스, 핀테크, 우주, 기후테크, 에이전트, 사이버보안 등)의 의미 있는 딜
   - 검색 키워드 예: "startup funding", "series round", "venture capital" + 최근 날짜

3. CVC / 전략적 투자
   - 대기업의 스타트업 투자, 전략적 파트너십

4. 정부/정책 자금
   - 스타트업 지원 정책, 정부 펀드, 규제 변화

5. 기술 시그널
   - AI 모델 발표, 오픈소스, 인프라, 하드웨어, 신제품 런칭

6. 대기업/빅테크 동향
   - 국내외 대기업 전략 변화, 조직개편, M&A, 인력 이동

7. 산업/시장 트렌드
   - VC/PE 시장 동향, IPO, M&A 트렌드, 글로벌 자본 흐름

8. 현재 주목받는 섹터의 기술 동향
   - 이번 주 딜이 몰리는 섹터가 어디인지 파악
   - 해당 섹터의 최신 기술 발전, 제품 동향

9. 워치리스트 기업 관련 뉴스
   - PortOne, DSRV, Spendit, GhostPass, CrossHub, TokenSquare, DeepX, A ROBOT, 맥킨리라이스
   - 각 기업명으로 직접 검색

수집 규칙:
- 각 뉴스 항목마다 반드시 포함: 팩트, 출처 URL, 날짜, 신뢰도(🟢공식/🟡언론/🔴루머)
- 바이오/헬스케어/제약/의료기기 관련은 절대 수집하지 마
- 한국어와 영어 소스 모두 검색해
- 가능한 한 많이 수집하되, 팩트가 확인된 것만

출력 형식: 카테고리별로 정리된 텍스트. JSON 아님."""

COLLECT_USER = f"""오늘({date_iso}) 기준으로 최근 24~72시간 이내 뉴스를 웹 검색해서 수집해줘.

검색해야 할 것:
- "한국 스타트업 투자 2026" 최신
- "startup funding this week 2026"
- "AI startup funding round"
- "robotics funding 2026"
- "한국 VC 투자 동향"
- 워치리스트 각 기업명 (PortOne, DSRV 등)
- "tech news today"
- 현재 핫한 섹터 키워드

각 뉴스마다 출처 URL을 반드시 포함해줘."""


def collect_raw_news():
    """Phase 1: 웹 검색으로 최신 뉴스 수집"""
    print("Phase 1: 웹 검색으로 뉴스 수집 중...")

    messages = [{"role": "user", "content": COLLECT_USER}]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system=COLLECT_SYSTEM,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 25
        }],
        messages=messages
    )

    # 텍스트 블록 추출
    text_parts = []
    for block in response.content:
        if hasattr(block, 'text'):
            text_parts.append(block.text)

    raw_news = "\n".join(text_parts)
    print(f"Phase 1 완료: {len(raw_news)}자 수집")
    return raw_news


# ══════════════════════════════════════════════════════════════
# PHASE 2: 수집된 뉴스를 구조화된 브리프로 변환
# ══════════════════════════════════════════════════════════════

GENERATE_SYSTEM = f"""너는 한국 VC 심사역을 위한 Daily Brief를 생성하는 전문 AI야.
오늘은 {date_iso} ({day_str})이다.

너에게 웹 검색으로 수집된 최신 뉴스 원문이 주어진다.
이 원문을 아래 기준에 따라 구조화된 JSON으로 변환해라.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 섹션 1: 오늘의 핵심 3줄 (top3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

선정 기준: "오늘 아침 투자심의위원회 시작 전에 팀한테 30초 만에 공유할 3가지"

이것은 단순 뉴스 요약이 아니다. 각 항목에 반드시 "So What"이 있어야 한다.
= "이게 우리의 투자 판단에 왜 중요한지"

선정 우선순위:
1순위: 워치리스트 기업에 직접 영향 (후속 라운드, 경쟁사 딜, M&A 등)
2순위: 시장 구조 변화 시그널 (자본 흐름 방향 전환, IPO 윈도우, 밸류에이션 기준 변동)
3순위: 판단이 필요한 대형 이벤트 (이게 버블이냐 인플렉션이냐 같은 것)

형식: 팩트 헤드라인 → So What (투자 함의)
단, 금액이 크다고 무조건 뽑지 마. "그래서 뭐?"에 답이 되는 것만.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 섹션 2: 딜 플로우 (deals)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

● 국내 (deal_domestic_weeks):
  - 바이오/헬스케어 완전 제외
  - 전수 수집: 시드, 프리시드, 금액 비공개 모두 포함
  - 이유: 한국 시장은 작아서 빠짐없이 봐야 하고, 초기 딜에서 다음 투자 기회가 나옴
  - 주차별로 구분 (이번 주 / 지난 주)
  - 각 딜에 날짜 표시

● 글로벌 (deal_global):
  - $200M+ 대형 딜
  - $200M 미만이라도 주목 섹터의 의미 있는 딜 포함
    (AI, 로보틱스, 핀테크, 우주, 에이전트, 사이버보안, 기후테크 등)
  - 요즘 주목받는 섹터 위주로 구성 — 이 구성은 매번 달라질 수 있음
  - 분량 넉넉하게. 10~15건 수준.

● CVC / 전략적 투자 (deal_cvc): 대기업의 스타트업 투자
● 정부 / 정책 자금 (deal_gov): 정부 펀드, 지원 정책

● 요약 칩 (summary_chips): 국내 이번주 건수/금액, 글로벌 월간, YTD 등

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 섹션 3: 시그널 (signals)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

기존 4개 섹션(기술 시그널, 대기업 동향, 산업/시장, 수요 변화)을 하나로 통합.

각 항목에 태그를 붙여라: 기술 | 대기업 | 산업 | 수요 | 정책

규칙:
- 중복 금지. 같은 뉴스가 여러 태그에 해당되면 가장 핵심적인 태그 하나만.
  (예: 삼성-AMD MOU는 "대기업"으로 한 번만)
- 시간순 정렬 (최신이 위)
- 분량: 6~10개

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 섹션 4: 섹터 Deep Dive (sector_trends)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

오늘/이번 주 뉴스에서 가장 뜨거운 2~3개 섹터를 골라서 기술 동향을 정리.

각 섹터별로:
- sector: 섹터명
- why_hot: 왜 지금 이 섹터가 뜨거운지 (이번 주 딜/뉴스 기반)
- tech_trend: 해당 섹터의 최신 기술 동향 (구체적으로. "AI가 발전하고 있다" 같은 뻔한 말 금지)
- key_players: 글로벌 + 국내 주요 플레이어
- investment_angle: VC 관점에서의 투자 포인트
- source_html: 출처 링크

매일 섹터 구성이 달라져야 한다. 이번 주 로보틱스가 뜨면 로보틱스, 다음 주 우주가 뜨면 우주.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 섹션 5: 워치리스트 (watchlist)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

고정 목록: PortOne, DSRV, Spendit, GhostPass, CrossHub, TokenSquare, DeepX, A ROBOT, 맥킨리라이스

각 기업마다:
- status: 상태 아이콘
  🔴 = 직접적 부정 뉴스/이슈
  🟢 = 직접적 긍정 뉴스 (투자 유치, 파트너십 등)
  🟡 = 간접 영향 (섹터 트렌드, 경쟁사 움직임 등)
  ⚪ = 변동 없음
- note: 상태에 대한 한 줄 설명 (변동 없으면 "변동 없음"이 아니라, 마지막으로 확인된 상태를 적어)
- last_checked: 마지막 확인 날짜

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 섹션 6: 특별 이벤트 (special_events)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

조건부 표시: 진짜 중요한 이벤트가 있을 때만 포함.
없으면 빈 배열 [].

기준: 규제 변화, 시장 충격, 대형 M&A, 스타트업 생태계에 직접 영향을 주는 정책 변화.
어제와 같은 이벤트를 반복하지 마.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 섹션 7: 오늘의 숙제 (homework)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

선정 기준: "오늘 브리프를 읽고 나서, 아직 답이 안 나온 질문"
= "이걸 안 파보면 다음 투자 판단에서 빈 구멍이 생기는 것"

3가지 유형 중에서 2~3개 선정:

유형 1 — 판단 필요 (judge):
  팩트는 있는데 해석이 갈리는 것.
  예: "로보틱스에 $1.2B 몰렸다 → 이게 2021년 크립토 같은 버블이냐, 진짜 인플렉션이냐?"
  밸류에이션 비교, 매출 유무, 기술 성숙도를 파봐야 답이 나오는 것.

유형 2 — 연결 필요 (connect):
  딜 두세 개가 같은 방향을 가리키는데 명시적으로 연결이 안 된 것.
  예: "텔레픽스 150억 + 캠프 시드 → 한국 우주테크가 섹터로 형성되고 있나?"
  개별로는 보이지만 묶어서 밸류체인을 그려봐야 투자 기회가 보이는 것.

유형 3 — 이해 필요 (understand):
  큰 돈이 움직였는데 기술 자체를 모르면 판단이 안 되는 것.
  예: "JEPA 월드모델에 $1B → 이게 뭔지 모르면 이 베팅이 맞는지 판단 자체가 불가능"

각 항목에 type 필드로 유형을 명시해라.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 섹션 8: 소스 (sources)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

사용한 검색 키워드, 참고 매체, 한계사항, 신뢰도 범례.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 공통 규칙
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 바이오/헬스케어/제약/의료기기는 모든 섹션에서 완전 제외
- 팩트 중심. 뇌피셜 금지. 출처 없는 정보 금지.
- source_html 필드에는 반드시 실제 URL이 포함된 HTML 링크를 넣어라
- 신뢰도 표시: 🟢 공식 발표 · 🟡 언론 보도 · 🔴 루머/관계자
- 순수 JSON만 반환. 마크다운 코드블록(```) 절대 금지.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ JSON 스키마
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "top3": [
    {{
      "headline": "팩트 헤드라인",
      "so_what": "→ 투자 함의 (So What)",
      "source_html": "🟢 <a href='URL' target='_blank'>출처</a>"
    }}
  ],
  "summary_chips": [
    {{"color": "#1a56db", "text": "국내 이번주 XX건 / XXX억"}},
    {{"color": "#7c3aed", "text": "글로벌 X월 $XXXB"}},
    {{"color": "#b7791f", "text": "YTD XXX건"}}
  ],
  "deal_domestic_weeks": [
    {{
      "label": "국내 (X월 X주차, X/XX~XX) — 바이오/헬스케어 제외",
      "rows": [
        {{"co": "회사명", "round": "라운드", "amount": "금액", "investor": "투자자", "sector": "섹터", "date": "3/25"}}
      ],
      "source_html": "🟢 <a href='URL' target='_blank'>출처명</a>"
    }}
  ],
  "deal_global": {{
    "label": "글로벌 (주요 딜) — 바이오/헬스케어 제외",
    "rows": [
      {{"co": "회사명 (국가)", "round": "라운드", "amount": "$XXM", "investor": "투자자", "sector": "섹터"}}
    ],
    "source_html": "🟢 <a href='URL' target='_blank'>출처명</a>"
  }},
  "deal_cvc": "CVC/전략적 투자 내용 텍스트",
  "deal_cvc_source_html": "<a href='URL' target='_blank'>출처명</a>",
  "deal_gov": "정부/정책 자금 내용 텍스트",
  "deal_gov_source_html": "<a href='URL' target='_blank'>출처명</a>",
  "signals": [
    {{
      "tag": "기술|대기업|산업|수요|정책",
      "fact": "팩트 내용",
      "source_html": "🟢 <a href='URL' target='_blank'>출처</a> · 날짜"
    }}
  ],
  "sector_trends": [
    {{
      "sector": "섹터명",
      "emoji": "🤖",
      "why_hot": "왜 지금 이 섹터가 뜨거운지",
      "tech_trend": "최신 기술 동향 구체적으로",
      "key_players": "글로벌: A, B / 국내: C, D",
      "investment_angle": "VC 관점 투자 포인트",
      "source_html": "<a href='URL' target='_blank'>출처</a>"
    }}
  ],
  "watchlist": [
    {{
      "name": "회사명",
      "status": "🟢|🟡|🔴|⚪",
      "note": "상태 설명",
      "last_checked": "{date_iso}"
    }}
  ],
  "special_events": [
    {{
      "tag": "정책|시장구조|규제|M&A",
      "title": "이벤트 제목",
      "body_html": "<strong>팩트:</strong> ...<br><strong>영향:</strong> ...<br><strong>출처:</strong> <a href='URL' target='_blank'>출처명</a>",
      "urgency_class": "urg-now|urg-watch|urg-long",
      "urgency_label": "즉시|모니터링|장기 영향"
    }}
  ],
  "homework": [
    {{
      "type": "judge|connect|understand",
      "type_label": "판단|연결|이해",
      "title": "숙제 제목",
      "desc": "구체적 내용. 무엇을 왜 파봐야 하는지.",
      "tags": [{{"class": "industry|startup|tech", "label": "산업|스타트업|기술"}}]
    }}
  ],
  "sources": {{
    "keywords": "사용한 서치 키워드",
    "media_html": "<a href='URL' target='_blank'>매체명</a> · ...",
    "limits": "한계사항",
    "reliability": "🟢 공식 발표 · 🟡 언론 보도 · 🔴 루머/관계자"
  }}
}}"""


def generate_brief(raw_news):
    """Phase 2: 수집된 뉴스를 구조화된 JSON으로 변환"""
    print("Phase 2: 구조화된 브리프 생성 중...")

    user_msg = f"""아래는 웹 검색으로 수집된 최신 뉴스 원문이다.
이 내용을 기반으로 VC Daily Brief JSON을 생성해라.

수집된 원문에 있는 팩트만 사용해라. 없는 뉴스를 만들지 마.
출처 URL은 원문에 있는 것을 그대로 사용해라.

━━━ 수집된 뉴스 원문 ━━━
{raw_news}
━━━ 원문 끝 ━━━

위 내용을 기반으로 순수 JSON만 반환해라. 마크다운 코드블록 없이."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system=GENERATE_SYSTEM,
        messages=[{"role": "user", "content": user_msg}]
    )

    raw = response.content[0].text.strip()
    # 코드블록 제거 (혹시라도 포함된 경우)
    raw = raw.replace("```json", "").replace("```", "").strip()
    b = json.loads(raw)
    print("Phase 2 완료: JSON 파싱 성공")
    return b


# ══════════════════════════════════════════════════════════════
# HTML 생성
# ══════════════════════════════════════════════════════════════

def esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_html(b):
    """JSON 데이터를 HTML로 변환"""

    # ── 오늘의 핵심 3줄 ──
    top3_html = ""
    for i, item in enumerate(b.get("top3", []), 1):
        top3_html += f"""
        <div class="top3-item">
          <span class="top3-num">{i}</span>
          <div class="top3-content">
            <p class="top3-headline">{esc(item["headline"])}</p>
            <p class="top3-sowhat">{esc(item["so_what"])}</p>
            <p class="top3-source">{item.get("source_html", "")}</p>
          </div>
        </div>"""

    # ── 딜 요약 칩 ──
    chips_html = "".join(
        f'<div class="sum-chip"><span class="sum-dot" style="background:{esc(c["color"])}"></span>'
        f'<span>{esc(c["text"])}</span></div>'
        for c in b.get("summary_chips", [])
    )

    # ── 국내 딜 테이블 ──
    domestic_html = ""
    for week in b.get("deal_domestic_weeks", []):
        rows = "".join(
            f'<tr><td class="co">{esc(r["co"])}</td><td>{esc(r["round"])}</td>'
            f'<td>{esc(r["amount"])}</td><td>{esc(r.get("investor",""))}</td>'
            f'<td>{esc(r["sector"])}</td></tr>'
            for r in week.get("rows", [])
        )
        domestic_html += f"""
        <div class="card">
          <p class="sub-label">{esc(week["label"])}</p>
          <table class="deal-table">
            <tr><th>회사</th><th>라운드</th><th>금액</th><th>투자자</th><th>섹터</th></tr>
            {rows}
          </table>
          <p class="sig-source">{week.get("source_html","")}</p>
        </div>"""

    # ── 글로벌 딜 ──
    dg = b.get("deal_global", {})
    global_rows = "".join(
        f'<tr><td class="co">{esc(r["co"])}</td><td>{esc(r["round"])}</td>'
        f'<td>{esc(r["amount"])}</td><td>{esc(r.get("investor",""))}</td>'
        f'<td>{esc(r["sector"])}</td></tr>'
        for r in dg.get("rows", [])
    )
    global_html = f"""
      <div class="card">
        <p class="sub-label">{esc(dg.get("label","글로벌 주요 딜"))}</p>
        <table class="deal-table">
          <tr><th>회사</th><th>라운드</th><th>금액</th><th>투자자</th><th>섹터</th></tr>
          {global_rows}
        </table>
        <p class="sig-source">{dg.get("source_html","")}</p>
      </div>"""

    # ── 시그널 (통합) ──
    signals_html = ""
    for s in b.get("signals", []):
        tag = s.get("tag", "기술")
        tag_class = {
            "기술": "tag-tech", "대기업": "tag-bigco", "산업": "tag-industry",
            "수요": "tag-demand", "정책": "tag-policy"
        }.get(tag, "tag-tech")
        signals_html += f"""
        <div class="sig">
          <span class="sig-tag {tag_class}">{esc(tag)}</span>
          <p class="sig-fact">{esc(s["fact"])}</p>
          <p class="sig-source">{s.get("source_html","")}</p>
        </div>"""

    # ── 섹터 Deep Dive ──
    sector_html = ""
    for sec in b.get("sector_trends", []):
        sector_html += f"""
        <div class="sector-card">
          <p class="sector-name">{esc(sec.get("emoji","📊"))} {esc(sec["sector"])}</p>
          <p class="sector-label">왜 지금 뜨거운가</p>
          <p class="sector-text">{esc(sec.get("why_hot",""))}</p>
          <p class="sector-label">기술 동향</p>
          <p class="sector-text">{esc(sec.get("tech_trend",""))}</p>
          <p class="sector-label">주요 플레이어</p>
          <p class="sector-text">{esc(sec.get("key_players",""))}</p>
          <p class="sector-label">투자 관점</p>
          <p class="sector-text sector-angle">{esc(sec.get("investment_angle",""))}</p>
          <p class="sig-source">{sec.get("source_html","")}</p>
        </div>"""

    # ── 워치리스트 ──
    watchlist_html = ""
    for w in b.get("watchlist", []):
        status = w.get("status", "⚪")
        status_class = {"🔴": "ws-red", "🟢": "ws-green", "🟡": "ws-yellow", "⚪": "ws-gray"}.get(status, "ws-gray")
        watchlist_html += f"""
        <div class="watch-row">
          <span class="watch-status {status_class}">{status}</span>
          <span class="watch-name">{esc(w["name"])}</span>
          <span class="watch-note">{esc(w.get("note",""))}</span>
          <span class="watch-date">{esc(w.get("last_checked",""))}</span>
        </div>"""

    # ── 특별 이벤트 ──
    events = b.get("special_events", [])
    events_section = ""
    if events:
        events_html = "".join(
            f'''<div class="event-box">
              <p class="event-tag">{esc(e["tag"])}</p>
              <p class="event-title">{esc(e["title"])}</p>
              <p class="event-body">{e.get("body_html","")}</p>
              <span class="event-urgency {esc(e.get("urgency_class","urg-watch"))}">{esc(e.get("urgency_label","모니터링"))}</span>
            </div>'''
            for e in events
        )
        events_section = f"""
        <p class="sec">⚡ 특별 이벤트 (ALERTS)</p>
        {events_html}"""

    # ── 숙제 ──
    hw_html = ""
    for i, h in enumerate(b.get("homework", []), 1):
        hw_type = h.get("type", "judge")
        type_class = {"judge": "hwt-judge", "connect": "hwt-connect", "understand": "hwt-understand"}.get(hw_type, "hwt-judge")
        type_label = h.get("type_label", "판단")
        tags = "".join(
            f'<span class="hw-tag {esc(t["class"])}">{esc(t["label"])}</span>'
            for t in h.get("tags", [])
        )
        hw_html += f"""
        <div class="hw-item">
          <div class="hw-title-row">
            <span class="hw-num">{i}</span>
            <span class="hw-type {type_class}">{esc(type_label)}</span>
            <span class="hw-title-text">{esc(h["title"])}</span>
          </div>
          <p class="hw-desc">{esc(h["desc"])}</p>
          <div class="hw-tags">{tags}</div>
        </div>"""

    src = b.get("sources", {})

    # ── 어제 브리프 링크 ──
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime('%m/%d')
    yesterday_day = day_names[yesterday.weekday()]

    HTML = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VC Daily Brief</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f7f7f5;color:#1a1a1a;font-size:14px}}
  .wrap{{max-width:960px;margin:0 auto;padding:24px 16px 48px}}

  /* 헤더 */
  .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}}
  .header h1{{font-size:18px;font-weight:600}}
  .updated{{font-size:12px;color:#888}}
  .subtitle{{font-size:11px;color:#bbb;margin-bottom:24px;font-style:italic}}

  /* 공통 */
  .sec{{font-size:11px;color:#999;letter-spacing:.08em;text-transform:uppercase;margin:28px 0 10px;display:flex;align-items:center;gap:6px}}
  .card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;padding:16px;margin-bottom:10px}}
  .card-muted{{background:#fafaf8;border-radius:8px;border:.5px solid #e8e8e5;padding:14px;margin-bottom:10px}}
  .sub-label{{font-size:11px;color:#888;margin-bottom:8px;font-weight:500}}
  .section-note{{font-size:11px;color:#bbb;margin-bottom:12px;font-style:italic}}
  .divider{{height:1px;background:#e8e8e5;margin:32px 0}}

  /* 오늘의 핵심 3줄 */
  .top3-card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;border-left:3px solid #1a56db;padding:16px;margin-bottom:10px}}
  .top3-item{{display:flex;gap:12px;padding:12px 0;border-bottom:.5px solid #f0f0ec}}
  .top3-item:last-child{{border-bottom:none;padding-bottom:0}}
  .top3-item:first-child{{padding-top:0}}
  .top3-num{{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:#1a56db;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;margin-top:2px}}
  .top3-content{{flex:1}}
  .top3-headline{{font-size:13px;font-weight:600;color:#1a1a1a;line-height:1.5}}
  .top3-sowhat{{font-size:12px;color:#1a56db;line-height:1.5;margin-top:3px;font-weight:500}}
  .top3-source{{font-size:10px;color:#aaa;margin-top:4px}}
  .top3-source a{{color:#1a56db;text-decoration:none}}
  .top3-source a:hover{{text-decoration:underline}}

  /* 딜 플로우 */
  .summary-bar{{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}}
  .sum-chip{{display:flex;align-items:center;gap:5px;font-size:11px;padding:4px 10px;border-radius:99px;border:.5px solid #e0e0db;background:#fff}}
  .sum-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
  .deal-table{{width:100%;border-collapse:collapse;font-size:12px}}
  .deal-table th{{text-align:left;font-size:10px;color:#aaa;font-weight:500;padding:6px 8px;border-bottom:1px solid #f0f0ec;text-transform:uppercase;letter-spacing:.05em}}
  .deal-table td{{padding:8px;border-bottom:.5px solid #f0f0ec;color:#444;vertical-align:top}}
  .deal-table tr:last-child td{{border-bottom:none}}
  .deal-table .co{{font-weight:600;color:#1a1a1a}}

  /* 시그널 */
  .sig{{padding:12px 0;border-bottom:.5px solid #f0f0ec}}
  .sig:last-child{{border-bottom:none;padding-bottom:0}}
  .sig-tag{{display:inline-block;font-size:9px;font-weight:600;padding:2px 8px;border-radius:4px;margin-bottom:6px;letter-spacing:.03em}}
  .tag-tech{{background:#e6f4ea;color:#276749}}
  .tag-bigco{{background:#e8f0fe;color:#1a56db}}
  .tag-industry{{background:#f3e8ff;color:#7c3aed}}
  .tag-demand{{background:#fef3cd;color:#b7791f}}
  .tag-policy{{background:#fde8e8;color:#c0392b}}
  .sig-fact{{font-size:13px;color:#1a1a1a;line-height:1.65}}
  .sig-source{{font-size:10px;color:#aaa;margin-top:4px;display:inline-block}}
  .sig-source a{{color:#1a56db;text-decoration:none}}
  .sig-source a:hover{{text-decoration:underline}}

  /* 섹터 Deep Dive */
  .sector-card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;padding:16px;margin-bottom:10px}}
  .sector-name{{font-size:14px;font-weight:700;color:#1a1a1a;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #f0f0ec}}
  .sector-label{{font-size:10px;color:#999;font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin-top:10px;margin-bottom:4px}}
  .sector-label:first-of-type{{margin-top:0}}
  .sector-text{{font-size:12px;color:#444;line-height:1.65}}
  .sector-angle{{color:#1a56db;font-weight:500}}

  /* 워치리스트 */
  .watch-card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;padding:8px 16px}}
  .watch-row{{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:.5px solid #f0f0ec;font-size:12px}}
  .watch-row:last-child{{border-bottom:none}}
  .watch-status{{font-size:14px;flex-shrink:0;width:20px;text-align:center}}
  .watch-name{{font-weight:600;color:#1a1a1a;min-width:100px}}
  .watch-note{{flex:1;color:#666}}
  .watch-date{{font-size:10px;color:#bbb;flex-shrink:0}}

  /* 특별 이벤트 */
  .event-box{{background:#fff;border-radius:8px;border-left:3px solid #e24b4a;padding:14px 16px;margin-bottom:10px}}
  .event-tag{{font-size:10px;font-weight:600;color:#e24b4a;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}}
  .event-title{{font-size:13px;font-weight:600;color:#1a1a1a;margin-bottom:6px}}
  .event-body{{font-size:12px;color:#666;line-height:1.6}}
  .event-body strong{{color:#444;font-weight:500}}
  .event-urgency{{display:inline-block;font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;margin-top:6px}}
  .urg-now{{background:#fde8e8;color:#c0392b}}
  .urg-watch{{background:#fef3cd;color:#b7791f}}
  .urg-long{{background:#e8f0fe;color:#1a56db}}

  /* 숙제 */
  .hw-card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;border-top:2px solid #1a56db;padding:16px;margin-bottom:10px}}
  .hw-item{{padding:12px 0;border-bottom:.5px solid #f0f0ec}}
  .hw-item:last-child{{border-bottom:none;padding-bottom:0}}
  .hw-title-row{{display:flex;align-items:center;gap:8px}}
  .hw-num{{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#1a56db;color:#fff;font-size:10px;font-weight:700;flex-shrink:0}}
  .hw-type{{font-size:9px;font-weight:600;padding:2px 8px;border-radius:4px;flex-shrink:0}}
  .hwt-judge{{background:#fef3cd;color:#b7791f}}
  .hwt-connect{{background:#f3e8ff;color:#7c3aed}}
  .hwt-understand{{background:#e6f4ea;color:#276749}}
  .hw-title-text{{font-size:13px;font-weight:600;color:#1a1a1a}}
  .hw-desc{{font-size:12px;color:#666;line-height:1.6;margin-top:6px;margin-left:28px}}
  .hw-tags{{margin-top:6px;margin-left:28px;display:flex;gap:4px;flex-wrap:wrap}}
  .hw-tag{{font-size:9px;font-weight:600;padding:2px 6px;border-radius:4px}}
  .hw-tag.industry{{background:#e8f0fe;color:#1a56db}}
  .hw-tag.startup{{background:#f3e8ff;color:#7c3aed}}
  .hw-tag.tech{{background:#e6f4ea;color:#276749}}

  /* 소스 */
  .source-list{{font-size:11px;color:#aaa;line-height:1.8}}
  .source-list strong{{color:#888;font-weight:500}}
  .source-list a{{color:#1a56db;text-decoration:none}}
  .source-list a:hover{{text-decoration:underline}}

  /* 접이식 소스 */
  details summary{{cursor:pointer;font-size:11px;color:#999;letter-spacing:.08em;text-transform:uppercase;padding:4px 0}}
  details summary:hover{{color:#666}}

  /* 어제 브리프 링크 */
  .prev-link{{text-align:center;padding:16px 0;font-size:12px}}
  .prev-link a{{color:#1a56db;text-decoration:none}}
  .prev-link a:hover{{text-decoration:underline}}

  @media(max-width:560px){{
    .deal-table{{font-size:11px}}
    .deal-table th,.deal-table td{{padding:6px 4px}}
    .watch-name{{min-width:70px}}
    .hw-title-row{{flex-wrap:wrap}}
  }}
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <h1>📡 VC Daily Brief</h1>
    <span class="updated">업데이트: {date_str} ({day_str})</span>
  </div>
  <p class="subtitle">Raw Feed — 팩트만. 판단은 네가 직접.</p>

  <!-- 1. 오늘의 핵심 3줄 -->
  <p class="sec">🎯 오늘의 핵심 (TODAY'S TOP 3)</p>
  <p class="section-note">투심 전 30초 브리핑 — 팩트 + So What</p>
  <div class="top3-card">
    {top3_html}
  </div>

  <!-- 2. 딜 플로우 -->
  <p class="sec">💰 딜 플로우 (DEAL FLOW)</p>
  <div class="summary-bar">{chips_html}</div>
  {domestic_html}
  {global_html}

  <div class="card-muted">
    <p class="sub-label">CVC / 전략적 투자</p>
    <p style="font-size:12px;color:#444;line-height:1.6;">{esc(b.get("deal_cvc",""))}</p>
    <p class="sig-source">{b.get("deal_cvc_source_html","")}</p>
  </div>

  <div class="card-muted">
    <p class="sub-label">정부 / 정책 자금</p>
    <p style="font-size:12px;color:#444;line-height:1.6;">{esc(b.get("deal_gov",""))}</p>
    <p class="sig-source">{b.get("deal_gov_source_html","")}</p>
  </div>

  <!-- 3. 시그널 -->
  <p class="sec">📡 시그널 (SIGNALS)</p>
  <p class="section-note">기술 · 대기업 · 산업 · 수요 · 정책 — 태그로 구분, 중복 없이, 시간순</p>
  <div class="card">
    {signals_html}
  </div>

  <!-- 4. 섹터 Deep Dive -->
  <p class="sec">🔬 섹터 DEEP DIVE (SECTOR TRENDS)</p>
  <p class="section-note">이번 주 가장 뜨거운 섹터의 기술 동향 — 매일 구성이 달라짐</p>
  {sector_html}

  <!-- 5. 워치리스트 -->
  <p class="sec">👁️ 워치리스트 (WATCHLIST)</p>
  <div class="watch-card">
    {watchlist_html}
  </div>

  <!-- 6. 특별 이벤트 (조건부) -->
  {events_section}

  <div class="divider"></div>

  <!-- 7. 오늘의 숙제 -->
  <p class="sec">📚 오늘의 숙제 (TODAY'S HOMEWORK)</p>
  <p class="section-note">오늘 브리프에서 아직 답이 안 나온 질문. 안 파보면 투자 판단에 빈 구멍이 생기는 것.</p>
  <div class="hw-card">
    {hw_html}
  </div>

  <div class="divider"></div>

  <!-- 8. 소스 -->
  <details>
    <summary>📎 소스 &amp; 방법론</summary>
    <div class="card-muted" style="margin-top:8px;">
      <div class="source-list">
        <strong>서치 키워드:</strong> {esc(src.get("keywords",""))}<br>
        <strong>참고 매체:</strong> {src.get("media_html","")}<br>
        <strong>한계:</strong> {esc(src.get("limits",""))}<br>
        <strong>신뢰도:</strong> {esc(src.get("reliability","🟢 공식 발표 · 🟡 언론 보도 · 🔴 루머/관계자"))}
      </div>
    </div>
  </details>

  <!-- 어제 브리프 -->
  <div class="prev-link">
    <a href="prev.html">← 어제 브리프 ({yesterday_str} {yesterday_day})</a>
  </div>

</div>
</body>
</html>"""

    return HTML


# ══════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import traceback
    try:
        # 어제 브리프 아카이브
        if os.path.exists("index.html"):
            shutil.copy("index.html", "prev.html")
            print("기존 index.html → prev.html 아카이브 완료")

        # Phase 1: 웹 검색 수집
        print("=== Phase 1 시작 ===")
        raw_news = collect_raw_news()
        print(f"=== Phase 1 완료: {len(raw_news)}자 ===")

        # Phase 2: 구조화
        print("=== Phase 2 시작 ===")
        brief_data = generate_brief(raw_news)
        print(f"=== Phase 2 완료: {len(brief_data)} keys ===")

        # HTML 생성
        html = build_html(brief_data)

        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"index.html 생성 완료 ({date_str})")

    except Exception as e:
        print(f"❌ 오류 발생: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise
