import anthropic
import json
import os
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
date_str = today.strftime('%Y.%m.%d')
day_names = ['월', '화', '수', '목', '금', '토', '일']
day_str = day_names[today.weekday()]

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM = """너는 한국 VC 심사역을 위한 Daily Brief를 생성하는 전문 AI야.

규칙:
1. 바이오/헬스케어 섹터는 완전히 제외 (딜 플로우, 기술 시그널, 모든 섹션)
2. 팩트 중심 작성. 판단/의견 최소화.
3. 한국 스타트업 생태계 + 글로벌 AI/핀테크/딥테크 중심
4. 워치리스트 고정: PortOne, DSRV, Spendit, GhostPass, CrossHub, TokenSquare, DeepX, A ROBOT, 맥킨리라이스
5. 반드시 순수 JSON만 반환. 마크다운 코드블록(```) 없이.

다음 JSON 스키마를 정확히 따라:
{
  "summary_chips": [
    {"color": "#1a56db", "text": "국내 이번주 XX건 / XXX억"},
    {"color": "#7c3aed", "text": "글로벌 X월 $XXXB"},
    {"color": "#b7791f", "text": "YTD XXX건"}
  ],
  "deal_domestic_weeks": [
    {
      "label": "국내 (3월 X주차, 3/XX~XX) — 바이오/헬스케어 제외",
      "rows": [
        {"co": "회사명", "round": "라운드", "amount": "금액", "investor": "투자자", "sector": "섹터"}
      ],
      "source_html": "🟢 <a href='URL' target='_blank'>출처명</a>"
    }
  ],
  "deal_global": {
    "label": "글로벌 (주요 $50M+ 딜) — 바이오/헬스케어 제외",
    "rows": [
      {"co": "회사명", "round": "라운드", "amount": "$XXX", "investor": "투자자", "sector": "섹터"}
    ],
    "source_html": "🟢 <a href='URL' target='_blank'>출처명</a>"
  },
  "deal_cvc": "CVC/전략적 투자 내용",
  "deal_cvc_source_html": "🟢 <a href='URL' target='_blank'>출처명</a>",
  "deal_gov": "정부/정책 자금 내용",
  "deal_gov_source_html": "🟢 <a href='URL' target='_blank'>출처명</a>",
  "tech_signals": [
    {"fact": "팩트 내용", "source_html": "🟢 <a href='URL' target='_blank'>출처</a> · 날짜"}
  ],
  "bigplayer_moves": [
    {"fact": "팩트 내용", "source_html": "🟢 <a href='URL' target='_blank'>출처</a> · 날짜"}
  ],
  "industry_trends": [
    {"fact": "팩트 내용", "source_html": "🟢 <a href='URL' target='_blank'>출처</a> · 날짜"}
  ],
  "demand_shifts": [
    {"fact": "팩트 내용", "source_html": "🟢 <a href='URL' target='_blank'>출처</a> · 날짜"}
  ],
  "watchlist_note": "워치리스트 변동사항 및 간접 영향 메모",
  "special_events": [
    {
      "tag": "정책|시장구조|규제|M&A",
      "title": "이벤트 제목",
      "body_html": "<strong>팩트:</strong> ...<br><strong>영향:</strong> ...<br><strong>출처:</strong> <a href='URL' target='_blank'>출처명</a>",
      "urgency_class": "urg-now|urg-watch|urg-long",
      "urgency_label": "즉시|모니터링|장기 영향"
    }
  ],
  "homework": [
    {
      "title": "숙제 제목",
      "desc": "구체적 내용. 무엇을 왜 파봐야 하는지.",
      "tags": [{"class": "industry|startup|tech", "label": "산업|스타트업|기술"}]
    }
  ],
  "sources": {
    "keywords": "사용한 서치 키워드",
    "media_html": "<a href='URL' target='_blank'>매체명</a> · ...",
    "limits": "한계사항",
    "reliability": "🟢 공식 발표 · 🟡 언론 보도 · 🔴 루머/관계자"
  }
}"""

USER = f"""오늘({today.strftime('%Y-%m-%d')}) 기준 VC Daily Brief를 작성해줘.
최근 1~2주간 한국 스타트업 투자 뉴스, 글로벌 AI/핀테크/딥테크 주요 딜,
대기업 동향, 기술 시그널을 반영해서 JSON으로 작성해.
바이오/헬스케어 완전 제외. 순수 JSON만 반환."""

print("Claude API 호출 중...")
response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=4096,
    system=SYSTEM,
    messages=[{"role": "user", "content": USER}]
)

raw = response.content[0].text.strip()
# 코드블록 제거 (혹시라도 포함된 경우)
raw = raw.replace("```json", "").replace("```", "").strip()
b = json.loads(raw)
print("JSON 파싱 성공")

def esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

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

# ── 시그널 섹션 공통 ──
def sig_section(items):
    return "".join(
        f'<div class="sig"><p class="sig-fact">{esc(s["fact"])}</p>'
        f'<p class="sig-source">{s.get("source_html","")}</p></div>'
        for s in items
    )

# ── 특별 이벤트 ──
events_html = "".join(
    f'''<div class="event-box">
      <p class="event-tag">{esc(e["tag"])}</p>
      <p class="event-title">{esc(e["title"])}</p>
      <p class="event-body">{e.get("body_html","")}</p>
      <span class="event-urgency {esc(e.get("urgency_class","urg-watch"))}">{esc(e.get("urgency_label","모니터링"))}</span>
    </div>'''
    for e in b.get("special_events", [])
)

# ── 숙제 ──
hw_html = ""
for i, h in enumerate(b.get("homework", []), 1):
    tags = "".join(
        f'<span class="hw-tag {esc(t["class"])}">{esc(t["label"])}</span>'
        for t in h.get("tags", [])
    )
    hw_html += f"""
    <div class="hw-item">
      <p class="hw-title"><span class="hw-num">{i}</span>{esc(h["title"])}</p>
      <p class="hw-desc">{esc(h["desc"])}</p>
      <div class="hw-tags">{tags}</div>
    </div>"""

src = b.get("sources", {})

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
  .empty{{color:#bbb;font-size:12px;font-style:italic;padding:8px 0}}
  .sub-label{{font-size:11px;color:#888;margin-bottom:8px;font-weight:500}}
  .summary-bar{{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}}
  .sum-chip{{display:flex;align-items:center;gap:5px;font-size:11px;padding:4px 10px;border-radius:99px;border:.5px solid #e0e0db;background:#fff}}
  .sum-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
  .deal-table{{width:100%;border-collapse:collapse;font-size:12px}}
  .deal-table th{{text-align:left;font-size:10px;color:#aaa;font-weight:500;padding:6px 8px;border-bottom:1px solid #f0f0ec;text-transform:uppercase;letter-spacing:.05em}}
  .deal-table td{{padding:8px;border-bottom:.5px solid #f0f0ec;color:#444;vertical-align:top}}
  .deal-table tr:last-child td{{border-bottom:none}}
  .deal-table .co{{font-weight:600;color:#1a1a1a}}
  .sig{{padding:12px 0;border-bottom:.5px solid #f0f0ec}}
  .sig:last-child{{border-bottom:none;padding-bottom:0}}
  .sig-fact{{font-size:13px;color:#1a1a1a;line-height:1.65}}
  .sig-source{{font-size:10px;color:#aaa;margin-top:4px;display:inline-block}}
  .sig-source a{{color:#1a56db;text-decoration:none}}
  .sig-source a:hover{{text-decoration:underline}}
  .watch-grid{{display:flex;flex-wrap:wrap;gap:6px}}
  .watch-tag{{font-size:11px;color:#888;padding:4px 10px;border-radius:99px;border:.5px solid #e0e0db;background:#fff}}
  .watch-tag.active{{background:#1a1a1a;color:#fff;border-color:#1a1a1a}}
  .event-box{{background:#fff;border-radius:8px;border-left:3px solid #e24b4a;padding:14px 16px;margin-bottom:10px}}
  .event-tag{{font-size:10px;font-weight:600;color:#e24b4a;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}}
  .event-title{{font-size:13px;font-weight:600;color:#1a1a1a;margin-bottom:6px}}
  .event-body{{font-size:12px;color:#666;line-height:1.6}}
  .event-body strong{{color:#444;font-weight:500}}
  .event-urgency{{display:inline-block;font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;margin-top:6px}}
  .urg-now{{background:#fde8e8;color:#c0392b}}
  .urg-watch{{background:#fef3cd;color:#b7791f}}
  .urg-long{{background:#e8f0fe;color:#1a56db}}
  .hw-card{{background:#fff;border-radius:8px;border:.5px solid #e0e0db;border-top:2px solid #1a56db;padding:16px;margin-bottom:10px}}
  .hw-item{{padding:12px 0;border-bottom:.5px solid #f0f0ec}}
  .hw-item:last-child{{border-bottom:none;padding-bottom:0}}
  .hw-num{{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#1a56db;color:#fff;font-size:10px;font-weight:700;margin-right:8px;flex-shrink:0}}
  .hw-title{{font-size:13px;font-weight:600;color:#1a1a1a;display:flex;align-items:center}}
  .hw-desc{{font-size:12px;color:#666;line-height:1.6;margin-top:4px;margin-left:28px}}
  .hw-tags{{margin-top:6px;margin-left:28px;display:flex;gap:4px;flex-wrap:wrap}}
  .hw-tag{{font-size:9px;font-weight:600;padding:2px 6px;border-radius:4px}}
  .hw-tag.industry{{background:#e8f0fe;color:#1a56db}}
  .hw-tag.startup{{background:#f3e8ff;color:#7c3aed}}
  .hw-tag.tech{{background:#e6f4ea;color:#276749}}
  .source-list{{font-size:11px;color:#aaa;line-height:1.8}}
  .source-list strong{{color:#888;font-weight:500}}
  .source-list a{{color:#1a56db;text-decoration:none}}
  .source-list a:hover{{text-decoration:underline}}
  .section-note{{font-size:11px;color:#bbb;margin-bottom:12px;font-style:italic}}
  .divider{{height:1px;background:#e8e8e5;margin:32px 0}}
  @media(max-width:560px){{.deal-table{{font-size:11px}}.deal-table th,.deal-table td{{padding:6px 4px}}}}
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <h1>📡 VC Daily Brief</h1>
    <span class="updated">업데이트: {date_str} ({day_str})</span>
  </div>
  <p class="subtitle">Raw Feed — 팩트만. 판단은 네가 직접.</p>

  <!-- 1. 딜 플로우 -->
  <p class="sec">💰 딜 플로우 (CAPITAL FLOW)</p>
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

  <!-- 2. 기술 시그널 -->
  <p class="sec">⚙️ 기술 &amp; 제품 시그널 (TECHNOLOGY READINESS)</p>
  <p class="section-note">AI 모델 · 오픈소스 · 인프라 · API/SDK · 하드웨어 · 비용 곡선 변화 · 신규 제품 런칭 · 기술 파트너십 등</p>
  <div class="card">{sig_section(b.get("tech_signals",[]))}</div>

  <!-- 3. 대기업 동향 -->
  <p class="sec">🏢 대기업 동향 (BIG PLAYER MOVES)</p>
  <p class="section-note">국내외 주요 대기업 · 빅테크의 전략적 움직임 — 신사업, 조직개편, CVC, M&amp;A, 제품 출시/폐지, 인력 이동</p>
  <div class="card">{sig_section(b.get("bigplayer_moves",[]))}</div>

  <!-- 4. 산업 & 시장 -->
  <p class="sec">🌐 산업 &amp; 시장 동향 (INDUSTRY &amp; MARKET TRENDS)</p>
  <p class="section-note">섹터별 시장 구조 변화 · VC/PE 시장 트렌드 · M&amp;A · IPO 파이프라인 · 산업 재편 · 글로벌 경쟁 구도 등</p>
  <div class="card">{sig_section(b.get("industry_trends",[]))}</div>

  <!-- 5. 수요 변화 -->
  <p class="sec">📈 수요 변화 (DEMAND SHIFT)</p>
  <p class="section-note">엔터프라이즈 채택 · 디지털 전환 · 고객 행동 변화 · 산업별 지출 이동 · 신규 시장 형성 등</p>
  <div class="card">{sig_section(b.get("demand_shifts",[]))}</div>

  <!-- 6. 워치리스트 -->
  <p class="sec">👁️ 워치리스트 트래커</p>
  <div class="card">
    <div class="watch-grid">
      <span class="watch-tag">PortOne</span>
      <span class="watch-tag">DSRV</span>
      <span class="watch-tag">Spendit</span>
      <span class="watch-tag">GhostPass</span>
      <span class="watch-tag">CrossHub</span>
      <span class="watch-tag">TokenSquare</span>
      <span class="watch-tag">DeepX</span>
      <span class="watch-tag">A ROBOT</span>
      <span class="watch-tag">맥킨리라이스</span>
    </div>
    <p class="empty" style="margin-top:8px;">{esc(b.get("watchlist_note",""))}</p>
  </div>

  <!-- 7. 특별 이벤트 -->
  <p class="sec">⚡ 특별 이벤트</p>
  {events_html}

  <div class="divider"></div>

  <!-- 8. 오늘의 숙제 -->
  <p class="sec">📚 오늘의 숙제 (TODAY'S HOMEWORK)</p>
  <p class="section-note">오늘 브리프에서 파생된 딥다이브 주제. 30분~1시간 파보고, 걸리는 게 있으면 Weekly Signal에 기록.</p>
  <div class="hw-card">{hw_html}</div>

  <div class="divider"></div>

  <!-- 9. 소스 -->
  <p class="sec">📎 소스 &amp; 방법론</p>
  <div class="card-muted">
    <div class="source-list">
      <strong>서치 키워드:</strong> {esc(src.get("keywords",""))}<br>
      <strong>참고 매체:</strong> {src.get("media_html","")}<br>
      <strong>한계:</strong> {esc(src.get("limits",""))}<br>
      <strong>신뢰도:</strong> {esc(src.get("reliability","🟢 공식 발표 · 🟡 언론 보도 · 🔴 루머/관계자"))}
    </div>
  </div>

</div>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(HTML)

print(f"index.html 생성 완료 ({date_str})")
