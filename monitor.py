#!/usr/bin/env python3
"""
NetGrid Monitor — проверка доступности сайтов.
Запускается из GitHub Actions каждый час.
"""

import os
import sys
import json
import time
import ssl
import socket
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# === НАСТРОЙКИ ===
SITES = [
    {"name": "babycloud.by",    "url": "https://babycloud.by/",    "expected": 200},
    {"name": "premiumfuji.by",  "url": "https://premiumfuji.by/",  "expected": 200},
    {"name": "refgroup.by",     "url": "http://188.255.163.132/",  "expected": 200, "host": "refgroup.by"},
]
TIMEOUT = 15  # секунд
SSL_WARNING_DAYS = 14  # за сколько дней до истечения предупреждать

# Telegram (берутся из env при запуске в GitHub Actions)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def check_site(site: dict) -> dict:
    """Проверяет один сайт. Возвращает словарь с результатами."""
    name = site["name"]
    url = site["url"]
    expected = site.get("expected", 200)
    host_header = site.get("host")

    result = {
        "name": name,
        "url": url,
        "status": "unknown",
        "http_code": None,
        "response_time_ms": None,
        "ssl_days_left": None,
        "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        req = Request(url, headers={"User-Agent": "NetGrid-Monitor/1.0"})
        if host_header:
            req.add_header("Host", host_header)

        start = time.time()
        with urlopen(req, timeout=TIMEOUT) as resp:
            result["response_time_ms"] = round((time.time() - start) * 1000, 1)
            result["http_code"] = resp.status

            if resp.status == expected:
                result["status"] = "up"
            else:
                result["status"] = "unexpected_code"
                result["error"] = f"Expected {expected}, got {resp.status}"

    except HTTPError as e:
        result["http_code"] = e.code
        result["status"] = "down"
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except URLError as e:
        result["status"] = "down"
        result["error"] = str(e.reason)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    # SSL check for HTTPS
    if url.startswith("https://"):
        try:
            hostname = url.split("//")[1].split("/")[0].split(":")[0]
            context = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=TIMEOUT) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    if cert and "notAfter" in cert:
                        expire = datetime.strptime(str(cert["notAfter"]), "%b %d %H:%M:%S %Y %Z")
                        expire = expire.replace(tzinfo=timezone.utc)
                        days_left = (expire - datetime.now(timezone.utc)).days
                        result["ssl_days_left"] = days_left
        except Exception as e:
            result["ssl_days_left"] = None
            if not result["error"]:
                result["error"] = f"SSL error: {e}"

    return result


def send_telegram(text: str) -> bool:
    """Отправляет сообщение в Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram credentials not set")
        return False

    import urllib.request
    import urllib.parse

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()

    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")
        return False


def create_github_issue(title: str, body: str) -> bool:
    """Создаёт GitHub Issue как fallback, если Telegram недоступен."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("[WARN] GITHUB_TOKEN not set, cannot create issue")
        return False

    import urllib.request
    import urllib.parse

    # Определяем repo из GITHUB_REPOSITORY или используем дефолт
    repo = os.environ.get("GITHUB_REPOSITORY", "ClarenceFerreiro/netgrid-monitor")
    url = f"https://api.github.com/repos/{repo}/issues"
    data = json.dumps({"title": title, "body": body, "labels": ["alert"]}).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/vnd.github.v3+json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 201
    except Exception as e:
        print(f"[ERROR] GitHub issue creation failed: {e}")
        return False


def format_alert(results: list) -> str:
    """Форматирует сообщение об ошибках."""
    lines = ["🚨 <b>NetGrid Alert</b> 🚨", ""]
    has_alert = False

    for r in results:
        icon = "✅" if r["status"] == "up" else "❌"
        if r["status"] != "up":
            has_alert = True
            lines.append(f"{icon} <b>{r['name']}</b>")
            lines.append(f"   Code: {r['http_code'] or 'N/A'}")
            lines.append(f"   Error: {r['error']}")
            if r["response_time_ms"]:
                lines.append(f"   Time: {r['response_time_ms']}ms")
            lines.append("")

        # SSL warning
        if r.get("ssl_days_left") is not None and r["ssl_days_left"] <= SSL_WARNING_DAYS:
            has_alert = True
            lines.append(f"⚠️ <b>{r['name']}</b> — SSL expires in {r['ssl_days_left']} days!")
            lines.append("")

    if not has_alert:
        return ""

    lines.append(f"<i>Checked: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</i>")
    return "\n".join(lines)


def format_github_issue(results: list) -> tuple:
    """Форматирует title и body для GitHub Issue."""
    down_sites = [r for r in results if r["status"] != "up"]
    ssl_warnings = [r for r in results if r.get("ssl_days_left") is not None and r["ssl_days_left"] <= SSL_WARNING_DAYS]

    title_parts = []
    if down_sites:
        names = ", ".join([r["name"] for r in down_sites])
        title_parts.append(f"DOWN: {names}")
    if ssl_warnings:
        names = ", ".join([r["name"] for r in ssl_warnings])
        title_parts.append(f"SSL expire: {names}")

    title = " | ".join(title_parts) if title_parts else "NetGrid Alert"
    if len(title) > 120:
        title = title[:117] + "..."

    body_lines = ["## NetGrid Monitor Alert", ""]
    for r in results:
        status_icon = "✅" if r["status"] == "up" else "❌"
        body_lines.append(f"### {status_icon} {r['name']}")
        body_lines.append(f"- **URL:** {r['url']}")
        body_lines.append(f"- **Status:** {r['status']}")
        body_lines.append(f"- **HTTP Code:** {r['http_code'] or 'N/A'}")
        if r["response_time_ms"]:
            body_lines.append(f"- **Response Time:** {r['response_time_ms']}ms")
        if r.get("ssl_days_left") is not None:
            body_lines.append(f"- **SSL Days Left:** {r['ssl_days_left']}")
        if r["error"]:
            body_lines.append(f"- **Error:** {r['error']}")
        body_lines.append("")

    body_lines.append(f"_Checked at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    return title, "\n".join(body_lines)


def main():
    print("=" * 50)
    print("NetGrid Monitor started")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 50)

    results = []
    all_ok = True

    for site in SITES:
        print(f"\nChecking {site['name']}...", end=" ")
        r = check_site(site)
        results.append(r)

        if r["status"] == "up":
            ssl_info = ""
            if r.get("ssl_days_left"):
                ssl_info = f" (SSL: {r['ssl_days_left']}d)"
            print(f"OK {r['http_code']} ({r['response_time_ms']}ms){ssl_info}")
        else:
            print(f"FAIL: {r['error']}")
            all_ok = False

    # Save status
    status = {
        "status": "up" if all_ok else "down",
        "last_check": datetime.now(timezone.utc).isoformat(),
        "sites": results,
    }
    with open("status.json", "w") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)

    # Send alert if needed
    alert_text = format_alert(results)
    if alert_text:
        print("\n[SENDING ALERT]")
        ok = send_telegram(alert_text)
        if ok:
            print("Telegram: sent")
        else:
            print("Telegram: failed, creating GitHub Issue...")
            issue_title, issue_body = format_github_issue(results)
            ok = create_github_issue(issue_title, issue_body)
            print(f"GitHub Issue: {'created' if ok else 'failed'}")
    else:
        print("\n[ALL OK — no alerts needed]")

    # Exit with error code if any site is down
    if not all_ok:
        print("\n[EXIT 1] Some sites are down")
        sys.exit(1)

    print("\n[EXIT 0] All sites operational")
    sys.exit(0)


if __name__ == "__main__":
    main()
