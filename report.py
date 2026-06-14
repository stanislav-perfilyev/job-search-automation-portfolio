#!/usr/bin/env python3
"""
report.py — Job search session report sent to Telegram.

Usage:
  python report.py --mode full    # after a full search session
  python report.py --mode check   # after a notifications-check session

Required env vars (see .env.example):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
  SPREADSHEET_ID
  (auth via sheets_key.json or GOOGLE_SERVICE_ACCOUNT_JSON)
"""

import argparse
import io
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# ── Config ──────────────────────────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
SHEET_NAME     = "Вакансии"
KEY_FILE       = Path(__file__).parent / "sheets_key.json"
SCOPES         = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

TG_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

if not TG_BOT_TOKEN or not TG_CHAT_ID:
    sys.exit("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
if not SPREADSHEET_ID:
    sys.exit("ERROR: SPREADSHEET_ID must be set.")
if not KEY_FILE.exists():
    sys.exit(f"ERROR: {KEY_FILE} not found. See sheets_key.json.example.")

TOKENS_PER_APP  = 5_000   # estimate per application
MINUTES_PER_APP = 3
STALE_DAYS      = 7

DATE_COLS = [5, 6, 7]     # columns F, G, H (0-indexed)

STATUS_COLORS = {
    "ожидание": "#4fc3f7",
    "интервью": "#81c784",
    "оффер":    "#ffd54f",
    "отказ":    "#e57373",
    "другое":   "#b0bec5",
}

BG_DARK = "#1a1a2e"
BG_MID  = "#16213e"
SPINE_C = "#444"


# ── Google Sheets ────────────────────────────────────────────────────────────
def get_token() -> str:
    creds = service_account.Credentials.from_service_account_file(
        str(KEY_FILE), scopes=SCOPES
    )
    creds.refresh(Request())
    return creds.token


def fetch_rows(token: str) -> list[list[str]]:
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
        f"/values/{SHEET_NAME}!A:K"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    values = r.json().get("values", [])
    rows = values[1:] if values else []
    return [row + [""] * (11 - len(row)) for row in rows]


def parse_date(s: str) -> datetime | None:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            pass
    return None


def normalize_status(raw: str) -> str:
    s = raw.lower().strip()
    if "интервью" in s or "собес" in s or "приглаш" in s:
        return "интервью"
    if "оффер" in s:
        return "оффер"
    if "отказ" in s:
        return "отказ"
    if (s == "" or "ожидание" in s or "ответа" in s
            or "просмотр" in s or "процесс" in s
            or "настроен" in s or "статус" in s):
        return "ожидание"
    return "другое"


def analyze(rows: list[list[str]]) -> tuple[dict, dict, int, list[str]]:
    by_date: dict[datetime, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    stale_count = 0
    stale_list: list[str] = []
    today = datetime.now().date()

    for row in rows:
        date_found: datetime | None = None
        for col in DATE_COLS:
            if row[col]:
                d = parse_date(row[col])
                if d:
                    date_found = d
                    break

        status = normalize_status(row[8])
        by_status[status] += 1

        if date_found:
            by_date[date_found] += 1
            if status == "ожидание":
                age = (today - date_found.date()).days
                if age >= STALE_DAYS:
                    stale_count += 1
                    stale_list.append(f"{row[0][:40]} / {row[1][:25]} ({age}д)")

    return dict(by_date), dict(by_status), stale_count, stale_list[:5]


# ── Telegram ─────────────────────────────────────────────────────────────────
def send_photo(image_bytes: bytes, caption: str):
    r = requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
        data={"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"},
        files={"photo": ("report.png", image_bytes, "image/png")},
    )
    r.raise_for_status()


# ── Chart: full session ───────────────────────────────────────────────────────
def build_chart_full(by_date: dict[datetime, int]) -> bytes:
    sessions = sorted(by_date.keys())
    labels   = [d.strftime("%d.%m") for d in sessions]
    apps     = [by_date[d] for d in sessions]
    minutes  = [a * MINUTES_PER_APP for a in apps]
    tokens_k = [a * TOKENS_PER_APP / 1000 for a in apps]
    cumulative, total = [], 0
    for a in apps:
        total += a
        cumulative.append(total)

    fig, axes = plt.subplots(2, 1, figsize=(max(8, len(sessions) * 0.9), 9))
    fig.patch.set_facecolor(BG_DARK)
    x = range(len(sessions))

    ax1 = axes[0]
    ax1.set_facecolor(BG_MID)
    bars = ax1.bar(x, apps, color="#4fc3f7", alpha=0.85, zorder=3)
    for bar, val in zip(bars, apps):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                 str(val), ha="center", va="bottom", color="white", fontsize=9, fontweight="bold")
    ax2 = ax1.twinx()
    ax2.plot(x, minutes, color="#f06292", marker="o", linewidth=2, markersize=6)
    ax2.set_ylabel("Time (min)", color="#f06292", fontsize=9)
    ax2.tick_params(axis="y", labelcolor="#f06292")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(labels, rotation=45, ha="right", color="white", fontsize=8)
    ax1.set_ylabel("Applications", color="#4fc3f7", fontsize=9)
    ax1.tick_params(axis="y", labelcolor="#4fc3f7")
    ax1.tick_params(axis="x", colors="white")
    ax1.set_title("Applications & time per session", color="white", fontsize=11, pad=8)
    ax1.grid(axis="y", alpha=0.2, zorder=0)
    ax1.spines[["top", "right", "bottom", "left"]].set_color(SPINE_C)

    ax3 = axes[1]
    ax3.set_facecolor(BG_MID)
    ax3.plot(x, cumulative, color="#81c784", marker="s", linewidth=2, markersize=6)
    for i, val in enumerate(cumulative):
        ax3.annotate(str(val), (i, val), textcoords="offset points",
                     xytext=(0, 6), ha="center", color="#81c784", fontsize=8)
    ax4 = ax3.twinx()
    ax4.fill_between(x, tokens_k, alpha=0.3, color="#ffb74d")
    ax4.plot(x, tokens_k, color="#ffb74d", marker="^", linewidth=1.5, markersize=5)
    ax4.set_ylabel("Tokens (k, estimate)", color="#ffb74d", fontsize=9)
    ax4.tick_params(axis="y", labelcolor="#ffb74d")
    ax3.set_xticks(list(x))
    ax3.set_xticklabels(labels, rotation=45, ha="right", color="white", fontsize=8)
    ax3.set_ylabel("Cumulative applications", color="#81c784", fontsize=9)
    ax3.tick_params(axis="y", labelcolor="#81c784")
    ax3.tick_params(axis="x", colors="white")
    ax3.set_title("Cumulative progress & token usage", color="white", fontsize=11, pad=8)
    ax3.grid(axis="y", alpha=0.2, zorder=0)
    ax3.spines[["top", "right", "bottom", "left"]].set_color(SPINE_C)

    plt.tight_layout(pad=2.0)
    return _fig_to_bytes(fig)


def build_caption_full(by_date: dict[datetime, int]) -> str:
    today = datetime.now().date()
    today_count = next((cnt for d, cnt in by_date.items() if d.date() == today), 0)
    total = sum(by_date.values())
    sessions_n = len(by_date)
    avg = total / sessions_n if sessions_n else 0
    return "\n".join([
        "📊 <b>Job search session summary</b>",
        f"📅 {today.strftime('%d.%m.%Y')}",
        "",
        "━━━ Today ━━━",
        f"📨 Applications: <b>{today_count}</b>",
        f"⏱ Time:         <b>~{today_count * MINUTES_PER_APP} min</b> (estimate)",
        f"🤖 Tokens:      <b>~{today_count * TOKENS_PER_APP:,}</b> (estimate)",
        "",
        "━━━ Total ━━━",
        f"🗓 Sessions:    {sessions_n}",
        f"📨 Applications: <b>{total}</b>",
        f"📈 Average:     {avg:.1f} per session",
    ])


# ── Chart: check session ──────────────────────────────────────────────────────
def build_chart_check(by_date, by_status, stale_count) -> bytes:
    sessions = sorted(by_date.keys())
    labels   = [d.strftime("%d.%m") for d in sessions]
    apps     = [by_date[d] for d in sessions]
    cumulative, total = [], 0
    for a in apps:
        total += a
        cumulative.append(total)

    fig = plt.figure(figsize=(12, 9), facecolor=BG_DARK)
    fig.suptitle(
        f"📊 C++ Job Search — {datetime.now().strftime('%d.%m.%Y')}",
        color="white", fontsize=13, fontweight="bold", y=0.98,
    )

    ax1 = fig.add_axes([0.06, 0.55, 0.54, 0.36])
    ax1.set_facecolor(BG_MID)
    x = range(len(sessions))
    bars = ax1.bar(x, apps, color="#4fc3f7", alpha=0.85, zorder=3)
    for bar, val in zip(bars, apps):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15,
                 str(val), ha="center", va="bottom", color="white", fontsize=8, fontweight="bold")
    ax1b = ax1.twinx()
    ax1b.plot(x, cumulative, color="#81c784", marker="o", linewidth=2, markersize=5)
    ax1b.set_ylabel("Cumulative", color="#81c784", fontsize=8)
    ax1b.tick_params(axis="y", labelcolor="#81c784")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(labels, rotation=45, ha="right", color="white", fontsize=7)
    ax1.set_ylabel("Applications", color="#4fc3f7", fontsize=8)
    ax1.tick_params(axis="y", labelcolor="#4fc3f7")
    ax1.tick_params(axis="x", colors="white")
    ax1.set_title("Activity by session", color="white", fontsize=10, pad=6)
    ax1.grid(axis="y", alpha=0.15, zorder=0)
    ax1.spines[["top", "right", "bottom", "left"]].set_color(SPINE_C)

    ax2 = fig.add_axes([0.60, 0.50, 0.38, 0.44])
    ax2.set_facecolor(BG_MID)
    status_order = ["ожидание", "интервью", "оффер", "отказ", "другое"]
    labels_pie, sizes, colors_pie = [], [], []
    for s in status_order:
        cnt = by_status.get(s, 0)
        if cnt > 0:
            labels_pie.append(f"{s.capitalize()} ({cnt})")
            sizes.append(cnt)
            colors_pie.append(STATUS_COLORS.get(s, "#b0bec5"))
    if sizes:
        wedges, _, autotexts = ax2.pie(
            sizes, labels=None, colors=colors_pie, autopct="%1.0f%%",
            startangle=90, pctdistance=0.75,
            wedgeprops={"edgecolor": BG_DARK, "linewidth": 2},
        )
        for at in autotexts:
            at.set_color("white")
            at.set_fontsize(8)
            at.set_fontweight("bold")
        ax2.legend(wedges, labels_pie, loc="lower center",
                   bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=7.5,
                   facecolor="#222", labelcolor="white", framealpha=0.8)
    ax2.set_title("Application statuses", color="white", fontsize=10, pad=6)

    total_all = sum(by_status.values())
    fig.text(
        0.5, 0.46,
        f"Total: {total_all}  |  Waiting: {by_status.get('ожидание', 0)}  |  "
        f"Interviews: {by_status.get('интервью', 0)}  |  "
        f"Offers: {by_status.get('оффер', 0)}  |  "
        f"Rejected: {by_status.get('отказ', 0)}  |  "
        f"Stale (>{STALE_DAYS}d): {stale_count}",
        ha="center", va="top", color="#b0bec5", fontsize=8.5,
    )
    fig.add_artist(plt.Line2D(
        [0.05, 0.95], [0.44, 0.44], color=SPINE_C, linewidth=0.8,
        transform=fig.transFigure, figure=fig,
    ))

    ax3 = fig.add_axes([0.06, 0.06, 0.88, 0.33])
    ax3.set_facecolor(BG_MID)
    ax3.axis("off")
    ax3.set_title("Last 7 sessions", color="white", fontsize=10, pad=6, loc="left")
    last_sessions = sessions[-7:]
    cum_so_far = sum(apps[:max(0, len(sessions) - len(last_sessions))])
    table_data = []
    for d in last_sessions:
        cnt = by_date[d]
        cum_so_far += cnt
        table_data.append([d.strftime("%d.%m.%Y"), str(cnt), str(cum_so_far)])
    tbl = ax3.table(
        cellText=table_data, colLabels=["Date", "Applications", "Cumulative"],
        loc="upper left", cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.5)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_facecolor("#1a2a3a" if r % 2 == 0 else BG_MID)
        cell.set_text_props(color="white")
        cell.set_edgecolor("#333")
        if r == 0:
            cell.set_facecolor("#0d47a1")
            cell.set_text_props(color="white", fontweight="bold")

    return _fig_to_bytes(fig)


def build_caption_check(by_status: dict, stale_count: int) -> str:
    total    = sum(by_status.values())
    waiting  = by_status.get("ожидание", 0)
    interview = by_status.get("интервью", 0)
    offer    = by_status.get("оффер", 0)
    rejected = by_status.get("отказ", 0)
    lines = [
        "🔔 <b>Notification check session done</b>",
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "",
        f"📨 Total applications: <b>{total}</b>",
        f"⏳ Waiting for reply:  <b>{waiting}</b>",
    ]
    if interview: lines.append(f"🎯 Interviews: <b>{interview}</b>")
    if offer:     lines.append(f"🏆 Offers:     <b>{offer}</b>")
    if rejected:  lines.append(f"❌ Rejected:   <b>{rejected}</b>")
    if stale_count:
        lines.append(f"⚠️  Stale >{STALE_DAYS}d: <b>{stale_count}</b>")
    return "\n".join(lines)


# ── Util ─────────────────────────────────────────────────────────────────────
def _fig_to_bytes(fig) -> bytes:
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130,
                facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["full", "check"], default="check")
    args = parser.parse_args()

    print(f"Mode: {args.mode.upper()}")
    print("Getting Sheets token...", end=" ", flush=True)
    token = get_token()
    print("✓")

    print("Reading data from Sheets...", end=" ", flush=True)
    rows = fetch_rows(token)
    print(f"✓ ({len(rows)} rows)")

    by_date, by_status, stale_count, stale_list = analyze(rows)
    if not by_date:
        print("No dated rows found in the sheet.")
        sys.exit(1)

    if stale_list:
        print(f"   ⚠️  Stale: {stale_count}")
        for s in stale_list:
            print(f"      — {s}")

    print("Building chart...", end=" ", flush=True)
    if args.mode == "full":
        chart   = build_chart_full(by_date)
        caption = build_caption_full(by_date)
    else:
        chart   = build_chart_check(by_date, by_status, stale_count)
        caption = build_caption_check(by_status, stale_count)
    print("✓")

    print("Sending to Telegram...", end=" ", flush=True)
    send_photo(chart, caption)
    print("✓")
    print("\n✅ Report sent!")


if __name__ == "__main__":
    main()
