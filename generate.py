import feedparser
import json
import os
import shutil
import re
import traceback
import time
from datetime import datetime, timezone, timedelta
from openai import OpenAI

try:
    from google import genai
    HAS_GEMINI = bool(os.environ.get("GEMINI_API_KEY"))
except ImportError:
    HAS_GEMINI = False

# ── 설정 ──
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
date_str = today.strftime('%Y.%m.%d')
date_iso = today.strftime('%Y-%m-%d')
day_names = ['월', '화', '수', '목', '금', '토', '일']
day_str = day_names[today.weekday()]

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"]) if HAS_GEMINI else None
groq_client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", ""),
    base_url="https://api.groq.com/openai/v1"
)

# ══════════════════════════════════════════════════════════════
# PHASE 1: RSS 피드로 최신 뉴스 수집
# ══════════════════════════════════════════════════════════════

RSS_FEEDS = {
    # ── 국내 스타트업/VC/테크 ──
    "플래텀": "https://platum.kr/feed",
    "벤처스퀘어": "https://www.venturesquare.net/feed",
    "GeekNews": "https://news.hada.io/rss",
    # ── 글로벌 테크/VC 매체 (미국 트렌드 중심) ──
    "TechCrunch": "https://techcrunch.com/feed/",
    "VentureBeat": "https://venturebeat.com/feed/",
    "TheVerge": "https://www.theverge.com/rss/index.xml",
    "ArsTechnica": "https://feeds.arstechnica.com/arstechnica/index",
    "Crunchbase": "https://news.crunchbase.com/feed/",
    # ── 한국 VC/스타트업/딜 ──
    "GN_스타트업투자": "https://news.google.com/rss/search?q=%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85+%ED%88%AC%EC%9E%90+%EC%9C%A0%EC%B9%98&hl=ko&gl=KR&ceid=KR:ko",
    "GN_VC투자": "https://news.google.com/rss/search?q=VC+%ED%88%AC%EC%9E%90+2026&hl=ko&gl=KR&ceid=KR:ko",
    "GN_시리즈투자": "https://news.google.com/rss/search?q=%EC%8B%9C%EB%A6%AC%EC%A6%88+%ED%88%AC%EC%9E%90+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85&hl=ko&gl=KR&ceid=KR:ko",
    "GN_투자유치": "https://news.google.com/rss/search?q=%ED%88%AC%EC%9E%90%EC%9C%A0%EC%B9%98+%EC%96%B5%EC%9B%90&hl=ko&gl=KR&ceid=KR:ko",
    "GN_시드투자": "https://news.google.com/rss/search?q=%EC%8B%9C%EB%93%9C+%ED%88%AC%EC%9E%90+%ED%94%84%EB%A6%AC%EC%8B%9C%EB%A6%AC%EC%A6%88&hl=ko&gl=KR&ceid=KR:ko",
    # ── AI / 소프트웨어 ──
    "GN_AI스타트업": "https://news.google.com/rss/search?q=AI+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85&hl=ko&gl=KR&ceid=KR:ko",
    "GN_AI_funding": "https://news.google.com/rss/search?q=AI+startup+funding&hl=en&gl=US&ceid=US:en",
    "GN_SaaS": "https://news.google.com/rss/search?q=SaaS+startup+funding&hl=en&gl=US&ceid=US:en",
    "GN_cybersecurity": "https://news.google.com/rss/search?q=cybersecurity+startup+funding&hl=en&gl=US&ceid=US:en",
    # ── 대기업 동향 (신규) ──
    "GN_대기업동향": "https://news.google.com/rss/search?q=%EB%8C%80%EA%B8%B0%EC%97%85+%ED%88%AC%EC%9E%90+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85&hl=ko&gl=KR&ceid=KR:ko",
    "GN_삼성전자": "https://news.google.com/rss/search?q=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90+%ED%88%AC%EC%9E%90+%EC%82%AC%EC%97%85&hl=ko&gl=KR&ceid=KR:ko",
    "GN_SK하이닉스": "https://news.google.com/rss/search?q=SK%ED%95%98%EC%9D%B4%EB%8B%89%EC%8A%A4+%EB%B0%98%EB%8F%84%EC%B2%B4&hl=ko&gl=KR&ceid=KR:ko",
    "GN_현대차그룹": "https://news.google.com/rss/search?q=%ED%98%84%EB%8C%80%EC%B0%A8+%EB%A1%9C%EB%B4%87+%EB%AA%A8%EB%B9%8C%EB%A6%AC%ED%8B%B0&hl=ko&gl=KR&ceid=KR:ko",
    "GN_bigtech": "https://news.google.com/rss/search?q=Google+Microsoft+Apple+Nvidia+investment+acquisition&hl=en&gl=US&ceid=US:en",
    "GN_대기업CVC": "https://news.google.com/rss/search?q=%EB%8C%80%EA%B8%B0%EC%97%85+CVC+%EB%B2%A4%EC%B2%98%ED%88%AC%EC%9E%90&hl=ko&gl=KR&ceid=KR:ko",
    # ── 제조 / 하드웨어 / 로봇 (신규) ──
    "GN_robotics": "https://news.google.com/rss/search?q=robotics+startup+funding&hl=en&gl=US&ceid=US:en",
    "GN_제조스타트업": "https://news.google.com/rss/search?q=%EC%A0%9C%EC%A1%B0+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85+%ED%88%AC%EC%9E%90&hl=ko&gl=KR&ceid=KR:ko",
    "GN_스마트팩토리": "https://news.google.com/rss/search?q=%EC%8A%A4%EB%A7%88%ED%8A%B8%ED%8C%A9%ED%86%A0%EB%A6%AC+%EC%9E%90%EB%8F%99%ED%99%94&hl=ko&gl=KR&ceid=KR:ko",
    "GN_hardware": "https://news.google.com/rss/search?q=hardware+startup+funding+2026&hl=en&gl=US&ceid=US:en",
    # ── 반도체 (신규) ──
    "GN_반도체": "https://news.google.com/rss/search?q=%EB%B0%98%EB%8F%84%EC%B2%B4+%ED%88%AC%EC%9E%90+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85&hl=ko&gl=KR&ceid=KR:ko",
    "GN_semiconductor": "https://news.google.com/rss/search?q=semiconductor+chip+startup+funding&hl=en&gl=US&ceid=US:en",
    # ── 에너지 / 기후테크 (신규) ──
    "GN_climate_tech": "https://news.google.com/rss/search?q=climate+tech+startup+funding&hl=en&gl=US&ceid=US:en",
    "GN_에너지": "https://news.google.com/rss/search?q=%EC%97%90%EB%84%88%EC%A7%80+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85+%ED%88%AC%EC%9E%90&hl=ko&gl=KR&ceid=KR:ko",
    # ── 모빌리티 / 자율주행 (신규) ──
    "GN_모빌리티": "https://news.google.com/rss/search?q=%EB%AA%A8%EB%B9%8C%EB%A6%AC%ED%8B%B0+%EC%9E%90%EC%9C%A8%EC%A3%BC%ED%96%89+%ED%88%AC%EC%9E%90&hl=ko&gl=KR&ceid=KR:ko",
    "GN_autonomous": "https://news.google.com/rss/search?q=autonomous+vehicle+startup+funding&hl=en&gl=US&ceid=US:en",
    # ── 우주 / 방산 (신규) ──
    "GN_우주방산": "https://news.google.com/rss/search?q=%EC%9A%B0%EC%A3%BC+%EB%B0%A9%EC%82%B0+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85&hl=ko&gl=KR&ceid=KR:ko",
    "GN_space_defense": "https://news.google.com/rss/search?q=space+defense+startup+funding&hl=en&gl=US&ceid=US:en",
    # ── 핀테크 ──
    "GN_fintech": "https://news.google.com/rss/search?q=fintech+startup+funding&hl=en&gl=US&ceid=US:en",
    # ── M&A / IPO ──
    "GN_스타트업인수합병": "https://news.google.com/rss/search?q=%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85+%EC%9D%B8%EC%88%98+%ED%95%A9%EB%B3%91&hl=ko&gl=KR&ceid=KR:ko",
    "GN_스타트업IPO": "https://news.google.com/rss/search?q=%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85+IPO+%EC%83%81%EC%9E%A5&hl=ko&gl=KR&ceid=KR:ko",
    "GN_startup_funding": "https://news.google.com/rss/search?q=startup+funding+round+2026&hl=en&gl=US&ceid=US:en",
}

# 바이오/헬스케어/디지털헬스케어/소재 필터
EXCLUDE_KEYWORDS = re.compile(
    # 바이오/헬스케어/디지털헬스케어
    r'바이오|헬스케어|디지털\s*헬스|제약|의료기기|의료\s*AI|임상|신약|치료제|'
    r'디지털\s*치료|진단키트|진단\s*기기|의약품|셀트리온|삼성바이오|에이비엘|'
    r'유전자|게놈|줄기세포|항체|백신|의료|병원|환자|질환|FDA\s*승인|'
    r'healthcare|biotech|pharma|clinical\s*trial|drug|medtech|health\s*tech|'
    r'therapeutics|diagnostic|genomic|vaccine|medical\s*device|digital\s*health|'
    # 소재
    r'소재\s*기업|화학\s*소재|2차전지\s*소재|양극재|음극재|전해질|분리막|'
    r'materials\s*science|chemical\s*materials',
    re.IGNORECASE
)


def fetch_rss_feeds():
    """RSS 피드에서 뉴스 수집"""
    print("Phase 1: RSS 피드 수집 중...")
    articles = []
    seen_titles = set()

    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                summary = entry.get("summary", "")[:300]
                pub = entry.get("published", entry.get("updated", ""))

                # 중복 제거
                title_key = re.sub(r'\s+', '', title)[:40]
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)

                # 바이오/헬스케어 필터
                if EXCLUDE_KEYWORDS.search(title) or EXCLUDE_KEYWORDS.search(summary):
                    continue

                articles.append({
                    "source": name,
                    "title": title,
                    "link": link,
                    "published": pub,
                    "summary": re.sub(r'<[^>]+>', '', summary).strip()
                })
                count += 1
            if count > 0:
                print(f"  [OK] {name}: {count}건")
            else:
                print(f"  [--] {name}: 0건")
        except Exception as e:
            print(f"  [ERR] {name}: {e}")

    # 최대 60건으로 제한 (피드 확장 반영)
    if len(articles) > 60:
        articles = articles[:60]
        print(f"  >> 60건으로 제한됨")

    print(f"Phase 1 완료: 총 {len(articles)}건 수집")
    return articles


def articles_to_text(articles, compact=False):
    """수집된 기사를 텍스트로 변환. compact=True면 제목+링크만."""
    lines = []
    for a in articles:
        if compact:
            lines.append(f"[{a['source']}] {a['title']} | {a['link']}")
        else:
            lines.append(f"[{a['source']}] {a['title']}")
            summary = a.get('summary', '')[:150]
            if summary:
                lines.append(f"  {summary}")
            lines.append(f"  {a['link']}")
            lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# PHASE 2: Gemini로 구조화된 브리프 생성
# ══════════════════════════════════════════════════════════════

GENERATE_SYSTEM = f"""한국 VC 심사역용 Daily Brief JSON 생성기. 오늘: {date_iso} ({day_str}).

[절대 규칙]
1. 바이오/헬스케어/디지털헬스케어/제약/의료/소재 관련은 전부 제외.
2. 같은 기업을 여러 섹션에 중복 배치 금지. 한 기업은 가장 관련 높은 섹션 1곳에만.
3. 모든 항목에 source_html(<a href="실제URL">매체명</a>) 필수. 출처 없는 항목은 만들지 마.
4. 수집된 뉴스에 있는 팩트만 사용. 없는 뉴스 만들지 마.
5. 대기업(삼성/SK/현대/Google/Microsoft/Nvidia 등) 동향, 제조/하드웨어/반도체 뉴스도 적극 반영.

[선별 기준]
- top3 우선순위: 시장 구조 변화(규제/M&A/대형라운드) > 판단 필요 대형 이벤트 > 주목할 스타트업 뉴스
- so_what: 단순 요약 아니라 VC 투자 판단에 미치는 영향 분석
- signals: 5종 태그(기술/대기업/산업/수요/정책) 골고루. top3와 겹치지 않는 뉴스 선택
- sector_trends: AI/SaaS에 편중되지 않게 다양한 섹터(제조/하드웨어/반도체 등도 뉴스 있으면 포함). investment_angle은 "어디에 투자 기회가 있는가" 관점
- watchlist: 오늘 뉴스에서 VC가 주목해야 할 기업(스타트업+대기업) 6~10개를 직접 선정. 선정 기준:
  ① 투자 유치 발표 ② 제품/서비스 주요 업데이트 ③ 시장 확장/피벗 ④ 경쟁 구도 변화
  뉴스에 등장한 실제 기업만. 상태: 🟢(긍정/성장) 🔴(리스크/위기) 🟡(주목할 변화)
- homework: type은 judge(판단)/connect(연결)/understand(이해). top3/signals에서 파생되는 후속 과제
- deals: 구체적 금액/라운드 나온 것만. 루머/검토중 제외. 국내+글로벌 합쳐 10~15건 목표.

JSON 스키마:
{{"top3":[{{"headline":"","so_what":"","source_html":""}}],"summary_chips":[{{"color":"#1a56db","text":""}}],"deal_domestic_weeks":[{{"label":"","rows":[{{"co":"","round":"","amount":"","investor":"","sector":"","date":""}}],"source_html":""}}],"deal_global":{{"label":"","rows":[{{"co":"","round":"","amount":"","investor":"","sector":""}}],"source_html":""}},"deal_cvc":"","deal_cvc_source_html":"","deal_gov":"","deal_gov_source_html":"","signals":[{{"tag":"","fact":"","source_html":""}}],"sector_trends":[{{"sector":"","emoji":"","why_hot":"","tech_trend":"","key_players":"","investment_angle":"","source_html":""}}],"watchlist":[{{"name":"","sector":"","status":"","note":"","source_html":""}}],"special_events":[],"homework":[{{"type":"","type_label":"","title":"","desc":"","tags":[{{"class":"","label":""}}]}}],"sources":{{"keywords":"","media_html":"","limits":"","reliability":""}}}}"
"""


def extract_json(text):
    """Gemini 응답에서 JSON을 안전하게 추출"""
    text = text.strip()
    # 마크다운 코드블록 제거
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```\s*$', '', text)
    text = text.strip()

    # 첫 번째 { 부터 마지막 } 까지 추출
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


def make_user_msg(raw_news_text):
    return f"""아래는 RSS 피드로 수집된 최신 뉴스 목록이다.
이 내용을 기반으로 VC Daily Brief JSON을 생성해라.

수집된 뉴스에 있는 팩트만 사용해라. 없는 뉴스를 만들지 마.
출처 URL은 수집된 뉴스의 링크를 그대로 사용해라.

━━━ 수집된 뉴스 ━━━
{raw_news_text}
━━━ 끝 ━━━

위 내용을 기반으로 순수 JSON만 반환해라. 마크다운 코드블록 없이."""


def try_gemini(user_msg):
    """1순위: Gemini 2.0 Flash"""
    print("  [Gemini] 시도 중...")
    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=user_msg,
        config={
            "system_instruction": GENERATE_SYSTEM,
            "max_output_tokens": 16000,
            "temperature": 0.3,
        }
    )
    return response.text.strip()


def groq_call(system_prompt, user_prompt, max_tokens=2000):
    """Groq API 단일 호출 (섹션별 분할용)"""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


# ── Groq 섹션별 프롬프트 (퀄리티 강화) ──

GROQ_BASE = f"""한국 VC 심사역용 Daily Brief 생성기. 오늘: {date_iso} ({day_str}).

절대 규칙:
1. 바이오/헬스케어/디지털헬스케어/제약/의료/소재 관련 뉴스는 전부 제외 — 딜, 시그널, 섹터, 워치리스트 어디에도 포함하지 마.
2. 같은 기업을 여러 섹션에 중복해서 넣지 마. 한 기업은 가장 관련 높은 섹션 1곳에만 배치.
3. 모든 항목에 반드시 source_html(<a href="실제URL">매체명</a>)을 포함. 출처 없는 항목은 만들지 마.
4. 수집된 뉴스에 있는 팩트만 사용. 없는 뉴스를 만들지 마.
5. 대기업 동향, 제조/하드웨어/반도체 뉴스도 빠지지 않게 균형 있게 포함해라. AI/SaaS에 편중되지 않도록.

순수 JSON만 반환(코드블록/마크다운 금지)."""

GROQ_SECTIONS = [
    {
        "name": "top3+chips+signals",
        "system": GROQ_BASE + """

[Call 1] 아래 뉴스에서 3가지를 추출해라:

1. top3: 투심(투자심의) 전 30초 브리핑 3건.
   - 선별 우선순위: ① 시장 구조 변화(규제, M&A, 대형 라운드) > ② 판단이 필요한 대형 이벤트 > ③ 주목할 스타트업 관련 뉴스
   - headline: 한 문장으로 팩트 요약 (30자 내외)
   - so_what: VC 심사역에게 "그래서 뭐?" 에 답하는 임팩트 분석 (50자 내외). 단순 요약이 아니라 투자 판단에 어떤 영향이 있는지 써라.
   - source_html: 반드시 <a href="실제URL">매체명</a> 형식

2. summary_chips: 오늘 수집된 뉴스를 실제로 세어서 통계 칩 2~4개 생성.
   - 뉴스에서 실제 건수/금액을 세서 구체적 숫자를 넣어라. "N건"이나 "$XB+" 같은 플레이스홀더 금지.
   - color: hex 색상코드, text: 실제 숫자가 포함된 텍스트 (예시: "국내 딜 3건", "글로벌 $1.2B")

3. signals: 시장 시그널 6~10개. 태그 5종(기술/대기업/산업/수요/정책) 골고루 분배. 시간순 정렬.
   - tag: "기술"|"대기업"|"산업"|"수요"|"정책" 중 하나
   - fact: 1~2문장 팩트 (뉴스 원문 기반, 추측 금지)
   - source_html: <a> 태그로 출처 링크
   - 절대 규칙: top3에 이미 나온 뉴스는 여기서 다시 쓰지 마. 같은 뉴스가 여러 섹션에 중복되면 안 됨.

JSON: {"top3":[{"headline":"","so_what":"","source_html":""}],"summary_chips":[{"color":"","text":""}],"signals":[{"tag":"","fact":"","source_html":""}]}""",
        "max_tokens": 2500,
    },
    {
        "name": "deals",
        "system": GROQ_BASE + """

[Call 2] 아래 뉴스에서 딜 플로우(투자 거래)를 추출해라:

1. deal_domestic_weeks: 국내 딜 (바이오/헬스케어/의료/제약/소재 완전 제외)
   - label: "이번 주 국내 주요 딜"
   - rows: [{co: 회사명, round: "시리즈A" 등, amount: "50억원" 등 (금액 미공개면 "미공개"), investor: 주요 투자자, sector: 섹터, date: 날짜}]
   - source_html: <a> 태그 출처
   - "투자 유치", "시리즈", "억원", "만달러", "funding", "raised", "round" 등이 포함된 뉴스를 빠짐없이 찾아라.
   - 금액이 명시되지 않아도 투자 유치 사실이 확인되면 amount를 "미공개"로 넣고 포함해라.

2. deal_global: 글로벌 딜 (금액 무관, 주목할 만한 딜이면 포함. 바이오/헬스케어/소재 제외)
   - 같은 rows 구조. label: "글로벌 주요 딜"
   - $200M 이상 대형 딜 우선, 그 외 트렌드 섹터 딜도 포함.

3. deal_cvc: CVC(대기업 벤처투자) 또는 전략적 투자 관련 뉴스 요약 텍스트 (1~2문장). 없으면 "해당 뉴스 없음".
   - deal_cvc_source_html: 출처

4. deal_gov: 정부/정책 자금 관련 뉴스 요약 텍스트. 없으면 "해당 뉴스 없음".
   - deal_gov_source_html: 출처

딜 정보를 적극적으로 찾아라. 뉴스 제목에 "투자", "유치", "funding", "raised" 등이 있으면 딜이다.

JSON: {"deal_domestic_weeks":[{"label":"","rows":[],"source_html":""}],"deal_global":{"label":"","rows":[],"source_html":""},"deal_cvc":"","deal_cvc_source_html":"","deal_gov":"","deal_gov_source_html":""}""",
        "max_tokens": 2500,
    },
    {
        "name": "sectors+watchlist+homework",
        "system": GROQ_BASE + """

[Call 3] 아래 뉴스와 [이전 호출 결과]를 참고하여 5가지를 생성해라:

1. sector_trends: 이번 주 가장 뜨거운 2~3개 섹터 딥다이브
   - sector: 섹터명 (예: "AI 인프라", "로보틱스", "핀테크")
   - emoji: 대표 이모지
   - why_hot: 왜 지금 뜨거운지 2~3문장 (구체적 뉴스/데이터 인용)
   - tech_trend: 핵심 기술 동향 1~2문장
   - key_players: 주요 플레이어 (스타트업+대기업 mix)
   - investment_angle: VC 투자 관점에서의 시사점 1~2문장. "어디에 투자 기회가 있는가"
   - source_html: <a> 태그 출처
   - 주의: [이전 호출 결과]의 signals와 겹치는 내용은 피하고 더 깊은 분석을 제공해라.

2. watchlist: 오늘 뉴스에서 VC가 주목해야 할 스타트업 6~10개를 직접 선정해라. 고정 리스트 없음.
   선정 기준 (우선순위순):
   ① 투자 유치를 발표한 스타트업 (딜 뉴스에 나온 기업)
   ② 제품/서비스 주요 업데이트가 있는 기업
   ③ 시장 확장, 피벗, 인수 등 전략적 변화가 있는 기업
   ④ 경쟁 구도 변화에 영향받는 기업
   - 뉴스에 실제로 등장한 기업만 포함. 만들어내지 마.
   - name: 기업명
   - sector: 섹터 (예: "AI", "핀테크", "로보틱스")
   - status: 🟢(긍정/성장) / 🔴(리스크/위기) / 🟡(주목할 변화)
   - note: 왜 주목해야 하는지 1문장
   - source_html: <a> 태그 출처

3. homework: 오늘 브리프에서 아직 답이 안 나온 질문 2~3개.
   [이전 호출 결과]의 top3, signals를 참고하여, 그 뉴스들에서 파생되는 후속 조사 과제를 만들어라.
   - type: "judge"(판단 필요) / "connect"(미팅/네트워킹 필요) / "understand"(기술/시장 이해 필요)
   - type_label: "판단" / "연결" / "이해"
   - title: 과제 제목 (질문 형태, 15자 내외)
   - desc: 왜 이걸 조사해야 하는지 2문장
   - tags: [{class: "industry"|"startup"|"tech", label: 태그명}]

4. sources: 이 브리프의 데이터 소스 메타정보
   - keywords: 주요 검색 키워드
   - media_html: 참고 매체 링크 (<a> 태그)
   - limits: 데이터 한계점
   - reliability: "공식 발표 · 언론 보도 · 루머/관계자"

5. special_events: 긴급하거나 특별한 이벤트. 없으면 빈 배열 [].

JSON: {"sector_trends":[],"watchlist":[],"homework":[],"sources":{},"special_events":[]}""",
        "max_tokens": 3000,
    },
]


def try_groq_split(articles):
    """Groq: 섹션별 분할 호출 후 병합 (체이닝으로 섹션 간 맥락 유지)"""
    print("  [Groq] 섹션별 분할 호출 (체이닝 모드)...")

    # 기사 30개까지, 요약 포함 (퀄리티 유지)
    news_text = articles_to_text(articles[:30], compact=False)
    # 입력이 너무 길면 compact로 폴백 (Groq TPM 보호)
    if len(news_text) > 12000:
        news_text = articles_to_text(articles[:25], compact=False)
    if len(news_text) > 12000:
        news_text = articles_to_text(articles[:30], compact=True)
        print("    >> 입력이 길어 compact 모드로 전환")

    merged = {}
    call1_summary = ""  # Call 1 결과 요약 (Call 3에 전달용)

    for i, sec in enumerate(GROQ_SECTIONS):
        print(f"    [{i+1}/{len(GROQ_SECTIONS)}] {sec['name']}...")

        # 기본 사용자 프롬프트
        user_prompt = f"━━━ 수집된 뉴스 ━━━\n{news_text}\n━━━ 끝 ━━━\n\n"

        # Call 3(sectors+watchlist+homework)에는 Call 1 결과를 컨텍스트로 전달
        if i == 2 and call1_summary:
            user_prompt += f"""━━━ 이전 호출 결과 (참고용) ━━━
{call1_summary}
━━━ 끝 ━━━

위 이전 호출 결과의 top3, signals와 겹치지 않는 내용으로 sector_trends를 작성하고,
homework는 위 top3/signals에서 파생되는 후속 조사 과제로 만들어라.

"""

        user_prompt += "순수 JSON만 반환해라. 코드블록 없이."

        raw = groq_call(sec["system"], user_prompt, sec["max_tokens"])
        part = extract_json(raw)
        merged.update(part)

        # Call 1 결과를 요약으로 저장 (Call 3에 전달하기 위해)
        if i == 0:
            try:
                top3_titles = [t.get("headline", "") for t in part.get("top3", [])]
                signal_facts = [s.get("fact", "") for s in part.get("signals", [])[:5]]
                call1_summary = "top3 헤드라인:\n" + "\n".join(f"- {t}" for t in top3_titles)
                call1_summary += "\n\nsignals 주요 팩트:\n" + "\n".join(f"- {f}" for f in signal_facts)
            except Exception:
                call1_summary = ""

        if i < len(GROQ_SECTIONS) - 1:
            print(f"    >> 62초 대기 (TPM 리셋)...")
            time.sleep(62)

    return merged


REQUIRED_KEYS = {
    "top3": list, "summary_chips": list, "signals": list,
    "deal_domestic_weeks": list, "deal_global": dict,
    "deal_cvc": str, "deal_gov": str,
    "sector_trends": list, "watchlist": list, "homework": list,
    "sources": dict, "special_events": list,
}


def validate_and_fix(b):
    """JSON 구조 검증 및 누락 키 보완"""
    fixed = 0
    for key, expected_type in REQUIRED_KEYS.items():
        if key not in b:
            b[key] = [] if expected_type == list else ({} if expected_type == dict else "")
            fixed += 1
            print(f"  [검증] 누락 키 보완: {key}")
        elif not isinstance(b[key], expected_type):
            # 타입이 틀린 경우 (예: dict여야 하는데 str로 옴)
            old_val = b[key]
            b[key] = [] if expected_type == list else ({} if expected_type == dict else str(old_val))
            fixed += 1
            print(f"  [검증] 타입 교정: {key} ({type(old_val).__name__} → {expected_type.__name__})")

    # list 안의 원소가 dict가 아니라 str인 경우 필터링
    for key in ["top3", "summary_chips", "signals", "deal_domestic_weeks",
                "sector_trends", "watchlist", "homework", "special_events"]:
        if isinstance(b.get(key), list):
            b[key] = [item for item in b[key] if isinstance(item, dict)]

    # deal_global 내부 rows도 검증
    dg = b.get("deal_global", {})
    if isinstance(dg, dict) and "rows" in dg:
        if not isinstance(dg["rows"], list):
            dg["rows"] = []
        else:
            dg["rows"] = [r for r in dg["rows"] if isinstance(r, dict)]

    # deal_domestic_weeks 내부 rows도 검증
    for week in b.get("deal_domestic_weeks", []):
        if isinstance(week, dict) and "rows" in week:
            if not isinstance(week["rows"], list):
                week["rows"] = []
            else:
                week["rows"] = [r for r in week["rows"] if isinstance(r, dict)]

    # watchlist가 비어있으면 경고
    if len(b.get("watchlist", [])) == 0:
        print("  [검증] 경고: watchlist가 비어있음 — LLM이 주목 기업을 선정하지 못함")

    # top3가 3개 미만 경고
    if len(b.get("top3", [])) < 3:
        print(f"  [검증] 경고: top3가 {len(b.get('top3',[]))}개밖에 없음")

    # homework 유형 검증
    valid_types = {"judge", "connect", "understand"}
    for h in b.get("homework", []):
        if h.get("type") not in valid_types:
            h["type"] = "judge"
            h["type_label"] = "판단"

    # source_html이 없는 signals/sector_trends 항목 필터링
    for key in ["signals", "sector_trends"]:
        original_len = len(b.get(key, []))
        b[key] = [item for item in b.get(key, [])
                  if isinstance(item, dict) and item.get("source_html", "").strip()]
        removed = original_len - len(b[key])
        if removed > 0:
            print(f"  [검증] {key}에서 출처 없는 항목 {removed}개 제거")

    if fixed > 0:
        print(f"  [검증] 총 {fixed}개 항목 보완됨")
    else:
        print("  [검증] 모든 키 정상")
    return b


# ── 딜 플로우 주간 누적 ──
DEALS_FILE = "deals.json"


def load_weekly_deals():
    """이번 주 누적 딜 로드. 월요일이면 리셋."""
    if today.weekday() == 0:  # 월요일
        print("  [딜 누적] 월요일 — 이번 주 딜 리셋")
        return {"domestic": [], "global": [], "week_start": date_iso}

    if os.path.exists(DEALS_FILE):
        try:
            with open(DEALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"  [딜 누적] 기존 딜 로드: 국내 {len(data.get('domestic',[]))}건, 글로벌 {len(data.get('global',[]))}건")
            return data
        except Exception as e:
            print(f"  [딜 누적] 로드 실패: {e}")

    return {"domestic": [], "global": [], "week_start": date_iso}


def merge_deals(existing, new_brief):
    """기존 주간 딜에 오늘 새 딜을 중복 없이 추가"""
    # 기존 기업명 셋
    existing_domestic_cos = {r.get("co", "") for r in existing.get("domestic", [])}
    existing_global_cos = {r.get("co", "") for r in existing.get("global", [])}

    # 오늘 새 국내 딜 추가
    new_domestic = 0
    for week in safe_list(new_brief.get("deal_domestic_weeks", [])):
        week = safe_dict(week)
        for row in safe_list(week.get("rows", [])):
            row = safe_dict(row)
            co = row.get("co", "")
            if co and co not in existing_domestic_cos:
                row["added_date"] = date_iso
                row["source_html"] = week.get("source_html", "")
                existing["domestic"].append(row)
                existing_domestic_cos.add(co)
                new_domestic += 1

    # 오늘 새 글로벌 딜 추가
    new_global = 0
    dg = safe_dict(new_brief.get("deal_global", {}))
    for row in safe_list(dg.get("rows", [])):
        row = safe_dict(row)
        co = row.get("co", "")
        if co and co not in existing_global_cos:
            row["added_date"] = date_iso
            row["source_html"] = dg.get("source_html", "")
            existing["global"].append(row)
            existing_global_cos.add(co)
            new_global += 1

    print(f"  [딜 누적] 오늘 추가: 국내 {new_domestic}건, 글로벌 {new_global}건")
    print(f"  [딜 누적] 주간 합계: 국내 {len(existing['domestic'])}건, 글로벌 {len(existing['global'])}건")
    return existing


def save_weekly_deals(deals_data):
    """주간 딜 데이터 저장"""
    with open(DEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(deals_data, f, ensure_ascii=False, indent=2)
    print(f"  [딜 누적] {DEALS_FILE} 저장 완료")


def apply_weekly_deals(brief, deals_data):
    """브리프의 딜 섹션을 주간 누적 데이터로 교체"""
    if deals_data.get("domestic"):
        brief["deal_domestic_weeks"] = [{
            "label": f"이번 주 국내 주요 딜 ({deals_data.get('week_start', date_iso)} ~)",
            "rows": deals_data["domestic"],
            "source_html": ""
        }]
    if deals_data.get("global"):
        brief["deal_global"] = {
            "label": "이번 주 글로벌 주요 딜",
            "rows": deals_data["global"],
            "source_html": ""
        }
    return brief


def generate_brief(articles):
    """Phase 2: Gemini 먼저 시도, 실패 시 Groq 섹션별 분할"""
    print("Phase 2: 브리프 생성 중...")

    # 1순위: Gemini (한 번에 전체)
    if HAS_GEMINI:
        try:
            full_text = articles_to_text(articles, compact=False)
            user_msg_full = make_user_msg(full_text)
            raw = try_gemini(user_msg_full)
            print("  [Gemini] 성공!")
            b = extract_json(raw)
            b = validate_and_fix(b)
            print(f"Phase 2 완료: JSON 파싱 성공 ({len(b)} keys)")
            return b
        except Exception as e:
            print(f"  [Gemini] 실패: {e}")

    # 2순위: Groq 섹션 분할
    if os.environ.get("GROQ_API_KEY"):
        try:
            b = try_groq_split(articles)
            b = validate_and_fix(b)
            print(f"  [Groq] 성공! ({len(b)} keys)")
            return b
        except Exception as e:
            print(f"  [Groq] 실패: {e}")

    raise RuntimeError("Gemini, Groq 모두 실패")


# ══════════════════════════════════════════════════════════════
# HTML 생성
# ══════════════════════════════════════════════════════════════

def safe_dict(v, fallback=None):
    """값이 dict가 아니면 빈 dict 또는 fallback 반환"""
    return v if isinstance(v, dict) else (fallback or {})


def safe_list(v):
    """값이 list가 아니면 빈 list 반환"""
    return v if isinstance(v, list) else []


def esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_html(b):
    top3_html = ""
    for i, item in enumerate(safe_list(b.get("top3", [])), 1):
        item = safe_dict(item)
        if not item:
            continue
        top3_html += f"""
        <div class="top3-item">
          <span class="top3-num">{i}</span>
          <div class="top3-content">
            <p class="top3-headline">{esc(item.get("headline",""))}</p>
            <p class="top3-sowhat">{esc(item.get("so_what",""))}</p>
            <p class="top3-source">{item.get("source_html", "")}</p>
          </div>
        </div>"""

    chips_html = "".join(
        f'<div class="sum-chip"><span class="sum-dot" style="background:{esc(safe_dict(c).get("color","#1a56db"))}"></span>'
        f'<span>{esc(safe_dict(c).get("text",""))}</span></div>'
        for c in safe_list(b.get("summary_chips", []))
    )

    domestic_html = ""
    for week in safe_list(b.get("deal_domestic_weeks", [])):
        week = safe_dict(week)
        if not week:
            continue
        rows = "".join(
            f'<tr><td class="co">{esc(safe_dict(r).get("co",""))}</td><td>{esc(safe_dict(r).get("round",""))}</td>'
            f'<td>{esc(safe_dict(r).get("amount",""))}</td><td>{esc(safe_dict(r).get("investor",""))}</td>'
            f'<td>{esc(safe_dict(r).get("sector",""))}</td></tr>'
            for r in safe_list(week.get("rows", []))
        )
        domestic_html += f"""
        <div class="card">
          <p class="sub-label">{esc(week.get("label",""))}</p>
          <table class="deal-table">
            <tr><th>회사</th><th>라운드</th><th>금액</th><th>투자자</th><th>섹터</th></tr>
            {rows}
          </table>
          <p class="sig-source">{week.get("source_html","")}</p>
        </div>"""

    dg = safe_dict(b.get("deal_global", {}))
    global_rows = "".join(
        f'<tr><td class="co">{esc(safe_dict(r).get("co",""))}</td><td>{esc(safe_dict(r).get("round",""))}</td>'
        f'<td>{esc(safe_dict(r).get("amount",""))}</td><td>{esc(safe_dict(r).get("investor",""))}</td>'
        f'<td>{esc(safe_dict(r).get("sector",""))}</td></tr>'
        for r in safe_list(dg.get("rows", []))
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

    signals_html = ""
    for s in safe_list(b.get("signals", [])):
        s = safe_dict(s)
        if not s:
            continue
        tag = s.get("tag", "기술")
        tag_class = {"기술":"tag-tech","대기업":"tag-bigco","산업":"tag-industry","수요":"tag-demand","정책":"tag-policy"}.get(tag, "tag-tech")
        signals_html += f"""
        <div class="sig">
          <span class="sig-tag {tag_class}">{esc(tag)}</span>
          <p class="sig-fact">{esc(s.get("fact",""))}</p>
          <p class="sig-source">{s.get("source_html","")}</p>
        </div>"""

    sector_html = ""
    for sec in safe_list(b.get("sector_trends", [])):
        sec = safe_dict(sec)
        if not sec:
            continue
        sector_html += f"""
        <div class="sector-card">
          <p class="sector-name">{esc(sec.get("emoji",""))} {esc(sec.get("sector",""))}</p>
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

    watchlist_html = ""
    for w in safe_list(b.get("watchlist", [])):
        w = safe_dict(w)
        if not w:
            continue
        sector_tag = f'<span class="watch-sector">{esc(w.get("sector",""))}</span>' if w.get("sector") else ""
        source = w.get("source_html", "")
        watchlist_html += f"""
        <div class="watch-row">
          <span class="watch-status">{w.get("status","🟡")}</span>
          <span class="watch-name">{esc(w.get("name",""))}</span>
          {sector_tag}
          <span class="watch-note">{esc(w.get("note",""))}</span>
          <span class="watch-source">{source}</span>
        </div>"""

    events = safe_list(b.get("special_events", []))
    events_section = ""
    if events:
        events_html = "".join(
            f'<div class="event-box"><p class="event-tag">{esc(safe_dict(e).get("tag",""))}</p>'
            f'<p class="event-title">{esc(safe_dict(e).get("title",""))}</p>'
            f'<p class="event-body">{safe_dict(e).get("body_html","")}</p>'
            f'<span class="event-urgency {esc(safe_dict(e).get("urgency_class","urg-watch"))}">{esc(safe_dict(e).get("urgency_label","모니터링"))}</span></div>'
            for e in events
        )
        events_section = f'<p class="sec">특별 이벤트 (ALERTS)</p>{events_html}'

    hw_html = ""
    for i, h in enumerate(safe_list(b.get("homework", [])), 1):
        h = safe_dict(h)
        if not h:
            continue
        hw_type = h.get("type", "judge")
        type_class = {"judge":"hwt-judge","connect":"hwt-connect","understand":"hwt-understand"}.get(hw_type, "hwt-judge")
        tags = "".join(f'<span class="hw-tag {esc(safe_dict(t).get("class",""))}">{esc(safe_dict(t).get("label",""))}</span>' for t in safe_list(h.get("tags", [])))
        hw_html += f"""
        <div class="hw-item">
          <div class="hw-title-row">
            <span class="hw-num">{i}</span>
            <span class="hw-type {type_class}">{esc(h.get("type_label","판단"))}</span>
            <span class="hw-title-text">{esc(h.get("title",""))}</span>
          </div>
          <p class="hw-desc">{esc(h.get("desc",""))}</p>
          <div class="hw-tags">{tags}</div>
        </div>"""

    src = safe_dict(b.get("sources", {}))
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
  .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}}
  .header h1{{font-size:18px;font-weight:600}}
  .updated{{font-size:12px;color:#888}}
  .subtitle{{font-size:11px;color:#bbb;margin-bottom:24px;font-style:italic}}
  .sec{{font-size:11px;color:#999;letter-spacing:.08em;text-transform:uppercase;margin:28px 0 10px;display:flex;align-items:center;gap:6px}}
  .card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;padding:16px;margin-bottom:10px}}
  .card-muted{{background:#fafaf8;border-radius:8px;border:.5px solid #e8e8e5;padding:14px;margin-bottom:10px}}
  .sub-label{{font-size:11px;color:#888;margin-bottom:8px;font-weight:500}}
  .section-note{{font-size:11px;color:#bbb;margin-bottom:12px;font-style:italic}}
  .divider{{height:1px;background:#e8e8e5;margin:32px 0}}
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
  .summary-bar{{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}}
  .sum-chip{{display:flex;align-items:center;gap:5px;font-size:11px;padding:4px 10px;border-radius:99px;border:.5px solid #e0e0db;background:#fff}}
  .sum-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
  .deal-table{{width:100%;border-collapse:collapse;font-size:12px}}
  .deal-table th{{text-align:left;font-size:10px;color:#aaa;font-weight:500;padding:6px 8px;border-bottom:1px solid #f0f0ec}}
  .deal-table td{{padding:8px;border-bottom:.5px solid #f0f0ec;color:#444;vertical-align:top}}
  .deal-table tr:last-child td{{border-bottom:none}}
  .deal-table .co{{font-weight:600;color:#1a1a1a}}
  .sig{{padding:12px 0;border-bottom:.5px solid #f0f0ec}}
  .sig:last-child{{border-bottom:none}}
  .sig-tag{{display:inline-block;font-size:9px;font-weight:600;padding:2px 8px;border-radius:4px;margin-bottom:6px}}
  .tag-tech{{background:#e6f4ea;color:#276749}}
  .tag-bigco{{background:#e8f0fe;color:#1a56db}}
  .tag-industry{{background:#f3e8ff;color:#7c3aed}}
  .tag-demand{{background:#fef3cd;color:#b7791f}}
  .tag-policy{{background:#fde8e8;color:#c0392b}}
  .sig-fact{{font-size:13px;color:#1a1a1a;line-height:1.65}}
  .sig-source{{font-size:10px;color:#aaa;margin-top:4px;display:inline-block}}
  .sig-source a{{color:#1a56db;text-decoration:none}}
  .sector-card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;padding:16px;margin-bottom:10px}}
  .sector-name{{font-size:14px;font-weight:700;color:#1a1a1a;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #f0f0ec}}
  .sector-label{{font-size:10px;color:#999;font-weight:600;text-transform:uppercase;margin-top:10px;margin-bottom:4px}}
  .sector-label:first-of-type{{margin-top:0}}
  .sector-text{{font-size:12px;color:#444;line-height:1.65}}
  .sector-angle{{color:#1a56db;font-weight:500}}
  .watch-card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;padding:8px 16px}}
  .watch-row{{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:.5px solid #f0f0ec;font-size:12px}}
  .watch-row:last-child{{border-bottom:none}}
  .watch-status{{font-size:14px;flex-shrink:0;width:20px;text-align:center}}
  .watch-name{{font-weight:600;color:#1a1a1a;min-width:80px}}
  .watch-sector{{font-size:9px;font-weight:600;padding:2px 6px;border-radius:4px;background:#e8f0fe;color:#1a56db;flex-shrink:0}}
  .watch-note{{flex:1;color:#666}}
  .watch-source{{font-size:10px;color:#aaa;flex-shrink:0}}
  .watch-source a{{color:#1a56db;text-decoration:none}}
  .event-box{{background:#fff;border-radius:8px;border-left:3px solid #e24b4a;padding:14px 16px;margin-bottom:10px}}
  .event-tag{{font-size:10px;font-weight:600;color:#e24b4a}}
  .event-title{{font-size:13px;font-weight:600;color:#1a1a1a;margin-bottom:6px}}
  .event-body{{font-size:12px;color:#666;line-height:1.6}}
  .event-urgency{{display:inline-block;font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;margin-top:6px}}
  .urg-now{{background:#fde8e8;color:#c0392b}}
  .urg-watch{{background:#fef3cd;color:#b7791f}}
  .urg-long{{background:#e8f0fe;color:#1a56db}}
  .hw-card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;border-top:2px solid #1a56db;padding:16px;margin-bottom:10px}}
  .hw-item{{padding:12px 0;border-bottom:.5px solid #f0f0ec}}
  .hw-item:last-child{{border-bottom:none}}
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
  .source-list{{font-size:11px;color:#aaa;line-height:1.8}}
  .source-list strong{{color:#888;font-weight:500}}
  .source-list a{{color:#1a56db;text-decoration:none}}
  details summary{{cursor:pointer;font-size:11px;color:#999;letter-spacing:.08em;text-transform:uppercase;padding:4px 0}}
  .prev-link{{text-align:center;padding:16px 0;font-size:12px}}
  .prev-link a{{color:#1a56db;text-decoration:none}}
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
    <h1>VC Daily Brief</h1>
    <span class="updated">업데이트: {date_str} ({day_str})</span>
  </div>
  <p class="subtitle">Raw Feed — 팩트만. 판단은 네가 직접.</p>

  <p class="sec">오늘의 핵심 (TODAY'S TOP 3)</p>
  <p class="section-note">투심 전 30초 브리핑 — 팩트 + So What</p>
  <div class="top3-card">{top3_html}</div>

  <p class="sec">딜 플로우 (DEAL FLOW)</p>
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

  <p class="sec">시그널 (SIGNALS)</p>
  <p class="section-note">기술 · 대기업 · 산업 · 수요 · 정책 — 태그로 구분, 중복 없이, 시간순</p>
  <div class="card">{signals_html}</div>

  <p class="sec">섹터 DEEP DIVE (SECTOR TRENDS)</p>
  <p class="section-note">이번 주 가장 뜨거운 섹터의 기술 동향 — 매일 구성이 달라짐</p>
  {sector_html}

  <p class="sec">오늘의 주목 기업 (TODAY'S WATCHLIST)</p>
  <p class="section-note">오늘 뉴스에서 VC가 눈여겨볼 스타트업 — 매일 트렌드에 따라 자동 선정</p>
  <div class="watch-card">{watchlist_html}</div>

  {events_section}
  <div class="divider"></div>

  <p class="sec">오늘의 숙제 (TODAY'S HOMEWORK)</p>
  <p class="section-note">오늘 브리프에서 아직 답이 안 나온 질문. 안 파보면 투자 판단에 빈 구멍이 생기는 것.</p>
  <div class="hw-card">{hw_html}</div>

  <div class="divider"></div>
  <details>
    <summary>소스 &amp; 방법론</summary>
    <div class="card-muted" style="margin-top:8px;">
      <div class="source-list">
        <strong>데이터 수집:</strong> RSS 피드 (플래텀, 벤처스퀘어, TechCrunch, VentureBeat, Google News RSS)<br>
        <strong>분석 엔진:</strong> Gemini 2.0 Flash + Groq Llama 3.3 70B (무료)<br>
        <strong>서치 키워드:</strong> {esc(src.get("keywords",""))}<br>
        <strong>참고 매체:</strong> {src.get("media_html","")}<br>
        <strong>한계:</strong> {esc(src.get("limits",""))}<br>
        <strong>신뢰도:</strong> {esc(src.get("reliability","공식 발표 · 언론 보도 · 루머/관계자"))}
      </div>
    </div>
  </details>
  {"" if not os.path.exists("prev.html") else f'<div class="prev-link"><a href="prev.html">이전 브리프 ({yesterday_str} {yesterday_day})</a></div>'}
</div>
</body>
</html>"""
    return HTML


# ══════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        if os.path.exists("index.html"):
            shutil.copy("index.html", "prev.html")
            print("기존 index.html → prev.html 아카이브 완료")

        print("=== Phase 1 시작 ===")
        articles = fetch_rss_feeds()

        if len(articles) == 0:
            print("!! RSS 피드 수집 0건 — 빈 목록으로 계속 진행")

        print(f"=== Phase 1 완료: {len(articles)}건 ===")

        print("=== Phase 2 시작 ===")
        brief_data = generate_brief(articles)
        print(f"=== Phase 2 완료: {len(brief_data)} keys ===")

        # 딜 플로우 주간 누적
        print("=== 딜 누적 처리 ===")
        weekly_deals = load_weekly_deals()
        weekly_deals = merge_deals(weekly_deals, brief_data)
        save_weekly_deals(weekly_deals)
        brief_data = apply_weekly_deals(brief_data, weekly_deals)

        html = build_html(brief_data)
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"index.html 생성 완료 ({date_str})")

    except Exception as e:
        print(f"오류 발생: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise
