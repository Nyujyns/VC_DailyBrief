import feedparser
import json
import os
import shutil
import re
import traceback
import time
from datetime import datetime, timezone, timedelta
from google import genai

# ── 설정 ──
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
date_str = today.strftime('%Y.%m.%d')
date_iso = today.strftime('%Y-%m-%d')
day_names = ['월', '화', '수', '목', '금', '토', '일']
day_str = day_names[today.weekday()]

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# ══════════════════════════════════════════════════════════════
# PHASE 1: RSS 피드로 최신 뉴스 수집
# ══════════════════════════════════════════════════════════════

RSS_FEEDS = {
    # 국내 스타트업/VC
    "플래텀": "https://platum.kr/feed",
    "벤처스퀘어": "https://www.venturesquare.net/feed",
    # 글로벌
    "TechCrunch": "https://techcrunch.com/feed/",
    "VentureBeat": "https://venturebeat.com/feed/",
    # Google News 키워드 검색 (한국어)
    "GN_스타트업투자": "https://news.google.com/rss/search?q=%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85+%ED%88%AC%EC%9E%90+%EC%9C%A0%EC%B9%98&hl=ko&gl=KR&ceid=KR:ko",
    "GN_VC투자": "https://news.google.com/rss/search?q=VC+%ED%88%AC%EC%9E%90+2026&hl=ko&gl=KR&ceid=KR:ko",
    "GN_시리즈투자": "https://news.google.com/rss/search?q=%EC%8B%9C%EB%A6%AC%EC%A6%88+%ED%88%AC%EC%9E%90+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85&hl=ko&gl=KR&ceid=KR:ko",
    "GN_AI스타트업": "https://news.google.com/rss/search?q=AI+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85&hl=ko&gl=KR&ceid=KR:ko",
    "GN_대기업동향": "https://news.google.com/rss/search?q=%EB%8C%80%EA%B8%B0%EC%97%85+%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85+%ED%88%AC%EC%9E%90&hl=ko&gl=KR&ceid=KR:ko",
    # Google News 키워드 검색 (영어)
    "GN_startup_funding": "https://news.google.com/rss/search?q=startup+funding+round+2026&hl=en&gl=US&ceid=US:en",
    "GN_AI_funding": "https://news.google.com/rss/search?q=AI+startup+funding&hl=en&gl=US&ceid=US:en",
    "GN_robotics": "https://news.google.com/rss/search?q=robotics+startup+funding&hl=en&gl=US&ceid=US:en",
    "GN_fintech": "https://news.google.com/rss/search?q=fintech+startup+funding&hl=en&gl=US&ceid=US:en",
    "GN_cybersecurity": "https://news.google.com/rss/search?q=cybersecurity+startup+funding&hl=en&gl=US&ceid=US:en",
    # 워치리스트 기업 검색
    "GN_PortOne": "https://news.google.com/rss/search?q=PortOne+%ED%8F%AC%ED%8A%B8%EC%9B%90&hl=ko&gl=KR&ceid=KR:ko",
    "GN_DSRV": "https://news.google.com/rss/search?q=DSRV+%EB%B8%94%EB%A1%9D%EC%B2%B4%EC%9D%B8&hl=ko&gl=KR&ceid=KR:ko",
    "GN_Spendit": "https://news.google.com/rss/search?q=Spendit+%EC%8A%A4%ED%8E%9C%EB%94%A7&hl=ko&gl=KR&ceid=KR:ko",
    "GN_DeepX": "https://news.google.com/rss/search?q=DeepX+%EB%A1%9C%EB%B4%87&hl=ko&gl=KR&ceid=KR:ko",
}

# 바이오/헬스케어 필터
BIO_KEYWORDS = re.compile(
    r'바이오|헬스케어|제약|의료기기|임상|신약|healthcare|biotech|pharma|clinical trial|drug',
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
                if BIO_KEYWORDS.search(title) or BIO_KEYWORDS.search(summary):
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

    # 최대 30건으로 제한 (Gemini 무료 티어 입력 토큰 한도 대응)
    if len(articles) > 30:
        articles = articles[:30]
        print(f"  >> 30건으로 제한됨")

    print(f"Phase 1 완료: 총 {len(articles)}건 수집")
    return articles


def articles_to_text(articles):
    """수집된 기사를 텍스트로 변환 (토큰 절약: 요약 100자 제한, 날짜 생략)"""
    lines = []
    for a in articles:
        lines.append(f"[{a['source']}] {a['title']}")
        summary = a.get('summary', '')[:100]
        if summary:
            lines.append(f"  {summary}")
        lines.append(f"  {a['link']}")
        lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# PHASE 2: Gemini로 구조화된 브리프 생성
# ══════════════════════════════════════════════════════════════

GENERATE_SYSTEM = f"""한국 VC 심사역용 Daily Brief JSON 생성. 오늘: {date_iso} ({day_str}).
바이오 제외. 팩트 중심. source_html에 실제 URL <a> 태그 필수. 순수 JSON만 반환(코드블록 금지).

섹션:
1. top3: 투심 전 30초 브리핑 3건. headline+so_what+source_html
2. deals: 국내(바이오제외), 글로벌($200M+), CVC, 정부자금
3. signals: 태그(기술|대기업|산업|수요|정책) 6~10개
4. sector_trends: 뜨거운 2~3섹터. why_hot/tech_trend/key_players/investment_angle
5. watchlist: PortOne,DSRV,Spendit,GhostPass,CrossHub,TokenSquare,DeepX,A ROBOT,맥킨리라이스. 상태 🔴🟢🟡⚪
6. special_events: 없으면 []
7. homework: judge/connect/understand 2~3개
8. sources: keywords/media_html/limits/reliability

JSON:
{{"top3":[{{"headline":"","so_what":"","source_html":""}}],"summary_chips":[{{"color":"#1a56db","text":""}}],"deal_domestic_weeks":[{{"label":"","rows":[{{"co":"","round":"","amount":"","investor":"","sector":"","date":""}}],"source_html":""}}],"deal_global":{{"label":"","rows":[{{"co":"","round":"","amount":"","investor":"","sector":""}}],"source_html":""}},"deal_cvc":"","deal_cvc_source_html":"","deal_gov":"","deal_gov_source_html":"","signals":[{{"tag":"","fact":"","source_html":""}}],"sector_trends":[{{"sector":"","emoji":"","why_hot":"","tech_trend":"","key_players":"","investment_angle":"","source_html":""}}],"watchlist":[{{"name":"","status":"","note":"","last_checked":""}}],"special_events":[],"homework":[{{"type":"","type_label":"","title":"","desc":"","tags":[{{"class":"","label":""}}]}}],"sources":{{"keywords":"","media_html":"","limits":"","reliability":""}}}}"
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


def generate_brief(raw_news_text):
    """Phase 2: Gemini로 구조화된 JSON 생성"""
    print("Phase 2: Gemini로 브리프 생성 중...")

    user_msg = f"""아래는 RSS 피드로 수집된 최신 뉴스 목록이다.
이 내용을 기반으로 VC Daily Brief JSON을 생성해라.

수집된 뉴스에 있는 팩트만 사용해라. 없는 뉴스를 만들지 마.
출처 URL은 수집된 뉴스의 링크를 그대로 사용해라.

━━━ 수집된 뉴스 ━━━
{raw_news_text}
━━━ 끝 ━━━

위 내용을 기반으로 순수 JSON만 반환해라. 마크다운 코드블록 없이."""

    # 재시도 로직 (무료 티어 분당 제한 대응)
    response = None
    last_error = None
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=user_msg,
                config={
                    "system_instruction": GENERATE_SYSTEM,
                    "max_output_tokens": 8000,
                    "temperature": 0.3,
                }
            )
            break
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if "429" in str(e) or "rate" in err_str or "quota" in err_str or "resource" in err_str:
                # retryDelay 파싱 시도
                delay_match = re.search(r'"retryDelay"\s*:\s*"(\d+)s"', str(e))
                if delay_match:
                    wait = int(delay_match.group(1)) + 5
                else:
                    wait = 65 * (attempt + 1)
                print(f"  >> 속도 제한 — {wait}초 대기 후 재시도 ({attempt+1}/5)")
                time.sleep(wait)
            else:
                raise

    # 5번 모두 실패한 경우
    if response is None:
        raise RuntimeError(f"Gemini API 5회 재시도 모두 실패: {last_error}")

    raw = response.text.strip()
    b = extract_json(raw)
    print(f"Phase 2 완료: JSON 파싱 성공 ({len(b)} keys)")
    return b


# ══════════════════════════════════════════════════════════════
# HTML 생성
# ══════════════════════════════════════════════════════════════

def esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_html(b):
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

    chips_html = "".join(
        f'<div class="sum-chip"><span class="sum-dot" style="background:{esc(c["color"])}"></span>'
        f'<span>{esc(c["text"])}</span></div>'
        for c in b.get("summary_chips", [])
    )

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

    signals_html = ""
    for s in b.get("signals", []):
        tag = s.get("tag", "기술")
        tag_class = {"기술":"tag-tech","대기업":"tag-bigco","산업":"tag-industry","수요":"tag-demand","정책":"tag-policy"}.get(tag, "tag-tech")
        signals_html += f"""
        <div class="sig">
          <span class="sig-tag {tag_class}">{esc(tag)}</span>
          <p class="sig-fact">{esc(s["fact"])}</p>
          <p class="sig-source">{s.get("source_html","")}</p>
        </div>"""

    sector_html = ""
    for sec in b.get("sector_trends", []):
        sector_html += f"""
        <div class="sector-card">
          <p class="sector-name">{esc(sec.get("emoji",""))} {esc(sec["sector"])}</p>
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
    for w in b.get("watchlist", []):
        watchlist_html += f"""
        <div class="watch-row">
          <span class="watch-status">{w.get("status","⚪")}</span>
          <span class="watch-name">{esc(w["name"])}</span>
          <span class="watch-note">{esc(w.get("note",""))}</span>
          <span class="watch-date">{esc(w.get("last_checked",""))}</span>
        </div>"""

    events = b.get("special_events", [])
    events_section = ""
    if events:
        events_html = "".join(
            f'<div class="event-box"><p class="event-tag">{esc(e.get("tag",""))}</p>'
            f'<p class="event-title">{esc(e.get("title",""))}</p>'
            f'<p class="event-body">{e.get("body_html","")}</p>'
            f'<span class="event-urgency {esc(e.get("urgency_class","urg-watch"))}">{esc(e.get("urgency_label","모니터링"))}</span></div>'
            for e in events
        )
        events_section = f'<p class="sec">특별 이벤트 (ALERTS)</p>{events_html}'

    hw_html = ""
    for i, h in enumerate(b.get("homework", []), 1):
        hw_type = h.get("type", "judge")
        type_class = {"judge":"hwt-judge","connect":"hwt-connect","understand":"hwt-understand"}.get(hw_type, "hwt-judge")
        tags = "".join(f'<span class="hw-tag {esc(t.get("class",""))}">{esc(t.get("label",""))}</span>' for t in h.get("tags", []))
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

    src = b.get("sources", {})
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
  .watch-name{{font-weight:600;color:#1a1a1a;min-width:100px}}
  .watch-note{{flex:1;color:#666}}
  .watch-date{{font-size:10px;color:#bbb;flex-shrink:0}}
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

  <p class="sec">워치리스트 (WATCHLIST)</p>
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
        <strong>분석 엔진:</strong> Google Gemini 2.0 Flash (무료)<br>
        <strong>서치 키워드:</strong> {esc(src.get("keywords",""))}<br>
        <strong>참고 매체:</strong> {src.get("media_html","")}<br>
        <strong>한계:</strong> {esc(src.get("limits",""))}<br>
        <strong>신뢰도:</strong> {esc(src.get("reliability","공식 발표 · 언론 보도 · 루머/관계자"))}
      </div>
    </div>
  </details>
  <div class="prev-link">
    <a href="prev.html">이전 브리프 ({yesterday_str} {yesterday_day})</a>
  </div>
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

        raw_text = articles_to_text(articles)
        print(f"=== Phase 1 완료: {len(articles)}건, {len(raw_text)}자 ===")

        print("=== Phase 2 시작 ===")
        brief_data = generate_brief(raw_text)
        print(f"=== Phase 2 완료: {len(brief_data)} keys ===")

        html = build_html(brief_data)
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"index.html 생성 완료 ({date_str})")

    except Exception as e:
        print(f"오류 발생: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise
