"""
IMC 일정 알림 — Teams DM (Adaptive Card)

매주 월요일 09:00 KST 실행.
- data.json에서 (BRAND, CHANNEL)별 마지막 END_DATE 추출
- 이미 종료 / 7일 이내 종료 예정 항목 분류
- Teams Workflow Webhook으로 Adaptive Card 발송

dry-run: DRY_RUN=1 환경변수 주면 발송 없이 출력만
"""

import os
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ALERT_WINDOW_DAYS = 7
ROOT = Path(__file__).parent


def load_data():
    with open(ROOT / "data.json", encoding="utf-8") as f:
        return json.load(f)


def last_end_dates(items):
    last = {}
    for item in items:
        brand = item.get("BRAND")
        channel = item.get("CHANNEL")
        end = item.get("END_DATE")
        if not (brand and channel and end):
            continue
        key = (brand, channel)
        if key not in last or end > last[key]:
            last[key] = end
    return last


def parse_date(s):
    """다양한 형식 허용: 2026-05-10, 2026.5.10, 2026/5/10, 2026. 5. 10. 등"""
    if not isinstance(s, str):
        return None
    cleaned = s.replace(".", "-").replace("/", "-").replace(" ", "").rstrip("-")
    parts = cleaned.split("-")
    if len(parts) != 3:
        return None
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return datetime(y, m, d).date()
    except ValueError:
        return None


def classify(end_str, today):
    end = parse_date(end_str)
    if end is None:
        return None, None
    delta = (end - today).days
    if delta < 0:
        return "expired", abs(delta)
    if delta <= ALERT_WINDOW_DAYS:
        return "expiring", delta
    return None, None


def build_adaptive_card(expired, expiring, opening, today):
    body = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "text": "🔔 IMC 일정 알림"
        },
        {
            "type": "TextBlock",
            "wrap": True,
            "isSubtle": True,
            "text": f"기준일: {today.strftime('%Y-%m-%d')} (KST)"
        }
    ]

    if opening:
        body.append({
            "type": "TextBlock",
            "weight": "Bolder",
            "color": "Good",
            "text": "🎉 오늘 오픈 기획전"
        })
        lines = []
        for brand, channel, name, end in opening:
            label = name if name else "(기획전명 없음)"
            end_label = f"  `~{end}`" if end else ""
            lines.append(f"• **[{brand}] {channel}** — {label}{end_label}")
        body.append({
            "type": "TextBlock",
            "wrap": True,
            "text": "\n\n".join(lines)
        })

    if expired:
        body.append({
            "type": "TextBlock",
            "weight": "Bolder",
            "color": "Attention",
            "text": "🚨 이미 종료된 채널 (재등록 필요)"
        })
        lines = []
        for brand, channel, days, end in expired:
            lines.append(f"• **[{brand}] {channel}** — {end} 종료  `({days}일 경과)`")
        body.append({
            "type": "TextBlock",
            "wrap": True,
            "text": "\n\n".join(lines)
        })

    if expiring:
        body.append({
            "type": "TextBlock",
            "weight": "Bolder",
            "color": "Warning",
            "text": f"⚠️ {ALERT_WINDOW_DAYS}일 이내 종료 예정"
        })
        lines = []
        for brand, channel, days, end in expiring:
            d_label = "D-Day" if days == 0 else f"D-{days}"
            lines.append(f"• **[{brand}] {channel}** — {end} 종료  `({d_label})`")
        body.append({
            "type": "TextBlock",
            "wrap": True,
            "text": "\n\n".join(lines)
        })

    body.append({
        "type": "TextBlock",
        "wrap": True,
        "isSubtle": True,
        "size": "Small",
        "text": "📅 매주 월요일 09:00 KST 자동 발송"
    })

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body
    }


def send_to_teams(card, webhook_url):
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card
        }]
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as res:
        return res.status


def collect_webhooks():
    """발송 대상 수집. TARGET 환경변수로 필터 가능: all / channel / dm"""
    target_filter = os.environ.get("TARGET", "all").lower()
    targets = {}
    channel_url = os.environ.get("TEAMS_WEBHOOK_URL_CHANNEL")
    dm_url = os.environ.get("TEAMS_WEBHOOK_URL_DM")
    if channel_url and target_filter in ("all", "channel"):
        targets["채널"] = channel_url
    if dm_url and target_filter in ("all", "dm"):
        targets["담당자 DM"] = dm_url
    return targets


def main():
    dry_run = os.environ.get("DRY_RUN") == "1"
    targets = collect_webhooks()

    if not targets and not dry_run:
        sys.exit("❌ TEAMS_WEBHOOK_URL_CHANNEL 또는 TEAMS_WEBHOOK_URL_DM 환경변수가 필요합니다.")

    items = load_data()
    today = datetime.now(KST).date()
    print(f"[info] today (KST) = {today}, dry_run = {dry_run}")
    print(f"[info] 발송 대상: {list(targets.keys()) if targets else '(dry-run only)'}")

    last = last_end_dates(items)

    expired, expiring = [], []
    for (brand, channel), end_str in last.items():
        status, days = classify(end_str, today)
        if status == "expired":
            expired.append((brand, channel, days, end_str))
        elif status == "expiring":
            expiring.append((brand, channel, days, end_str))

    opening = []
    for item in items:
        start = parse_date(item.get("START_DATE"))
        if start == today:
            opening.append((
                item.get("BRAND"),
                item.get("CHANNEL"),
                item.get("PROMOTION_NAME", ""),
                item.get("END_DATE", "")
            ))

    expired.sort(key=lambda x: -x[2])
    expiring.sort(key=lambda x: x[2])
    opening.sort(key=lambda x: (x[0] or "", x[1] or ""))

    print(f"[info] expired={len(expired)}, expiring={len(expiring)}, opening={len(opening)}")

    if not expired and not expiring and not opening:
        print("✅ 알림 대상 없음. 발송 스킵.")
        return

    card = build_adaptive_card(expired, expiring, opening, today)

    if dry_run:
        print("[dry-run] 발송 생략. Adaptive Card 미리보기:")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    for label, url in targets.items():
        status = send_to_teams(card, url)
        print(f"✅ Teams 발송 완료 [{label}] (HTTP {status})")


if __name__ == "__main__":
    main()
