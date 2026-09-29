#!/usr/bin/env python3
"""
$HIRED - the Hire Probability Exchange.

Every run (00:05 IST via GitHub Actions):
  1. SETTLE  - if a prediction is pending for a day that has ended, fetch the real
               commit count for that IST day and score it.
  2. PREDICT - forecast today's commit count (rounded mean of the last 7 IST days).
  3. RENDER  - rewrite data.json, assets/ticker.svg and the block inside README.md
               between the HIRE_EXCHANGE markers.

Standard library only. No pip install needed.

Usage:
  python scripts/hire_exchange.py                 # real run (needs GH_TOKEN, GH_LOGIN)
  python scripts/hire_exchange.py --mock          # fake commit counts, no network
  python scripts/hire_exchange.py --render-only   # just re-render from data.json
  python scripts/hire_exchange.py --today 2026-10-01 --mock   # simulate a date
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import textwrap
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib import request
from xml.sax.saxutils import escape

# --------------------------------------------------------------------------- #
# Config - tweak the game here
# --------------------------------------------------------------------------- #
IST = timezone(timedelta(hours=5, minutes=30))  # IST has no DST, fixed offset is safe

START_PROB = 0.42          # listing price (%)
PROB_MIN, PROB_MAX = 0.05, 99.90

TOLERANCE = 1              # |actual - predicted| <= this counts as a "near" hit
REWARD_EXACT = 1.0         # points gained on exact hit
REWARD_NEAR = 0.5          # points gained on near hit
PENALTY_MISS = -0.25
PENALTY_CRASH = -0.5       # zero commits when at least one was predicted
PENALTY_MANIP = -1.5       # suspicious spike
STREAK_BONUS = 0.1         # extra per consecutive hit (after the first)...
STREAK_BONUS_CAP = 5       # ...up to this many steps

MANIP_MIN_COMMITS = 10     # "market manipulation" if actual >= 10
MANIP_MULTIPLIER = 3       # ...and actual >= 3x the prediction

HISTORY_KEEP = 120         # settled sessions kept in data.json

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data.json"
SVG_FILE = ROOT / "assets" / "ticker.svg"
README_FILE = ROOT / "README.md"
START_MARK = "<!--HIRE_EXCHANGE:START-->"
END_MARK = "<!--HIRE_EXCHANGE:END-->"

# --------------------------------------------------------------------------- #
# Sarcasm pools (edit freely)
# --------------------------------------------------------------------------- #
NOTES = {
    "HIT": [
        "Exact call. Analysts are stunned. HR is still on leave.",
        "Bullseye. Sharma ji ka beta is mildly concerned.",
        "Perfect prediction. Sadly, the recruiter inbox is not as predictable.",
        "Market is bullish. Recruiters remain bearish on reading READMEs.",
        "Called it. Now if only the offer letter would call back.",
    ],
    "NEAR": [
        "Off by one, the most relatable bug in history.",
        "Close enough. Like my code, technically within tolerance.",
        "Within margin. Probability up, LinkedIn still silent.",
        "Almost exact. Almost hired. Almost is the theme.",
    ],
    "MISS_LOW": [
        "Fewer commits than forecast. Blame chai, Wi-Fi and Mercury retrograde.",
        "Underdelivered. The market has feelings and they are hurt.",
        "Bearish day. Stack Overflow was consulted, no commits were made.",
        "Forecast missed. Portfolio blames the power cut.",
    ],
    "MISS_HIGH": [
        "Overachieved, which is also a miss. Analysts hate surprises.",
        "Too many commits. Productivity or panic? Unclear.",
        "Market beat expectations. Expectations were low, to be fair.",
    ],
    "CRASH": [
        "Zero commits. Market crash. Founder is on a Netflix break.",
        "Flatline. Investors are checking if the developer is alive.",
        "Nothing shipped. Volume: 0. Vibes: also 0.",
    ],
    "MANIP": [
        "Market manipulation detected. SEBI has entered the chat.",
        "Suspicious volume spike. Empty commits are not a personality.",
        "Pump and dump alert. Regulators have been notified. By me. Sarcastically.",
    ],
    "INIT": [
        "Exchange opens today. Listing price: optimistic. Fundamentals: pending.",
        "IPO day. Analysts are being polite about the valuation.",
    ],
}

RESULT_LABEL = {
    "HIT": "✅ Exact hit",
    "NEAR": "🟢 Near hit",
    "MISS": "❌ Miss",
    "CRASH": "📉 Crash",
    "MANIP": "🚨 Manipulation",
}


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def default_state() -> dict:
    return {
        "probability": START_PROB,
        "streak": 0,
        "best_streak": 0,
        "opened": None,
        "updated": None,
        "pending": None,        # {"for_date", "predicted", "avg7"}
        "last_result": None,
        "last_delta": 0.0,
        "last_note": None,
        "history": [],          # settled sessions, oldest first
    }


def load_state() -> dict:
    state = default_state()
    if DATA_FILE.exists():
        state.update(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    return state


def save_state(state: dict) -> None:
    DATA_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Commit counts
# --------------------------------------------------------------------------- #
def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_bounds_utc(d: date) -> tuple[str, str]:
    """Start/end of an IST calendar day, expressed in UTC for the GitHub API."""
    start = datetime(d.year, d.month, d.day, tzinfo=IST)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return _utc(start), _utc(end)


def fetch_commit_counts(login: str, days: list[date], token: str) -> dict[date, int]:
    """One GraphQL request, one aliased contributionsCollection per IST day."""
    fields = []
    for d in days:
        s, e = day_bounds_utc(d)
        fields.append(
            f'd{d:%Y%m%d}: contributionsCollection(from: "{s}", to: "{e}") '
            f"{{ totalCommitContributions }}"
        )
    query = "query($login: String!) { user(login: $login) { " + " ".join(fields) + " } }"
    body = json.dumps({"query": query, "variables": {"login": login}}).encode()
    req = request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "hire-exchange",
        },
    )
    with request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors") or not payload.get("data", {}).get("user"):
        raise RuntimeError(f"GitHub GraphQL error: {payload.get('errors') or 'user not found'}")
    user = payload["data"]["user"]
    return {d: int(user[f"d{d:%Y%m%d}"]["totalCommitContributions"]) for d in days}


def mock_commit_counts(days: list[date]) -> dict[date, int]:
    pool = [0, 1, 2, 2, 3, 3, 3, 4, 5, 6, 14]
    return {d: random.Random(f"mock-{d.isoformat()}").choice(pool) for d in days}


# --------------------------------------------------------------------------- #
# Game logic
# --------------------------------------------------------------------------- #
def predict(counts: dict[date, int], today: date) -> tuple[int, float]:
    vals = [counts[today - timedelta(days=i)] for i in range(7, 0, -1)]
    avg = sum(vals) / len(vals)
    return int(avg + 0.5), round(avg, 2)


def classify(predicted: int, actual: int) -> str:
    if predicted >= 1 and actual >= MANIP_MIN_COMMITS and actual >= MANIP_MULTIPLIER * predicted:
        return "MANIP"
    if actual == 0 and predicted >= 1:
        return "CRASH"
    diff = abs(actual - predicted)
    if diff == 0:
        return "HIT"
    if diff <= TOLERANCE:
        return "NEAR"
    return "MISS"


def settle(state: dict, pending: dict, actual: int) -> None:
    predicted = pending["predicted"]
    result = classify(predicted, actual)
    before = state["probability"]

    if result in ("HIT", "NEAR"):
        state["streak"] += 1
        bonus = STREAK_BONUS * min(state["streak"] - 1, STREAK_BONUS_CAP)
        delta = (REWARD_EXACT if result == "HIT" else REWARD_NEAR) + bonus
    else:
        state["streak"] = 0
        delta = {"MISS": PENALTY_MISS, "CRASH": PENALTY_CRASH, "MANIP": PENALTY_MANIP}[result]

    after = round(min(PROB_MAX, max(PROB_MIN, before + delta)), 2)
    state["best_streak"] = max(state["best_streak"], state["streak"])

    pool_key = result
    if result == "MISS":
        pool_key = "MISS_LOW" if actual < predicted else "MISS_HIGH"
    note = random.Random(pending["for_date"]).choice(NOTES[pool_key])

    state["history"].append(
        {
            "date": pending["for_date"],
            "predicted": predicted,
            "actual": actual,
            "result": result,
            "delta": round(after - before, 2),
            "prob_before": before,
            "probability": after,
            "note": note,
        }
    )
    state["history"] = state["history"][-HISTORY_KEEP:]
    state["probability"] = after
    state["last_result"] = result
    state["last_delta"] = round(after - before, 2)
    state["last_note"] = note


def rating(p: float) -> tuple[str, str]:
    if p < 1:
        return "STRONG SELL", "#f85149"
    if p < 5:
        return "SELL", "#f85149"
    if p < 20:
        return "HOLD", "#d29922"
    if p < 50:
        return "BUY", "#3fb950"
    return "STRONG BUY", "#3fb950"


# --------------------------------------------------------------------------- #
# SVG rendering
# --------------------------------------------------------------------------- #
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
BG, BORDER, TEXT, MUTED = "#0d1117", "#30363d", "#f0f6fc", "#8b949e"
GREEN, RED, AMBER, GRID, BAR_PRED = "#3fb950", "#f85149", "#d29922", "#21262d", "#484f58"
RESULT_COLOR = {"HIT": GREEN, "NEAR": GREEN, "MISS": RED, "CRASH": RED, "MANIP": AMBER}


def _t(x, y, s, size=13, fill=MUTED, weight="normal", anchor="start", style="") -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
        f'text-anchor="{anchor}" {style}>{escape(str(s))}</text>'
    )


def _sparkline(series, x0, y0, w, h, color) -> str:
    out = []
    for frac in (0, 0.5, 1):
        gy = y0 + h * frac
        out.append(f'<line x1="{x0}" y1="{gy:.1f}" x2="{x0 + w}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')
    if len(series) < 2:
        out.append(_t(x0 + w / 2, y0 + h / 2 + 4, "Not enough data yet. Market just opened.", 12, MUTED, anchor="middle"))
        return "".join(out)

    lo, hi = min(series), max(series)
    if hi - lo < 0.5:
        mid = (hi + lo) / 2
        lo, hi = mid - 0.25, mid + 0.25
    pad = (hi - lo) * 0.12
    lo, hi = lo - pad, hi + pad

    pts = []
    for i, v in enumerate(series):
        x = x0 + w * i / (len(series) - 1)
        y = y0 + h - (v - lo) / (hi - lo) * h
        pts.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{x0},{y0 + h} {line} {x0 + w},{y0 + h}"
    out.append(f'<polygon points="{area}" fill="{color}" opacity="0.12"/>')
    out.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
    lx, ly = pts[-1]
    out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{color}"/>')
    out.append(_t(x0 + w, y0 - 4, f"hi {max(series):.2f}%", 10, MUTED, anchor="end"))
    out.append(_t(x0 + w, y0 + h + 12, f"lo {min(series):.2f}%", 10, MUTED, anchor="end"))
    return "".join(out)


def _bars(entries, x0, base_y, w, max_h) -> str:
    if not entries:
        return _t(x0 + w / 2, base_y - max_h / 2, "Awaiting first settlement (tomorrow 00:05 IST).", 12, MUTED, anchor="middle")
    slots = 7
    slot_w = w / slots
    maxv = max(1, max(max(e["predicted"], e["actual"]) for e in entries))
    out = [f'<line x1="{x0}" y1="{base_y}" x2="{x0 + w}" y2="{base_y}" stroke="{GRID}" stroke-width="1"/>']
    offset = slots - len(entries)  # right-align so the newest day is always last
    for i, e in enumerate(entries):
        sx = x0 + (offset + i) * slot_w
        for j, (val, colr) in enumerate(((e["predicted"], BAR_PRED), (e["actual"], RESULT_COLOR[e["result"]]))):
            bh = max(2, val / maxv * max_h)
            bx = sx + 8 + j * 18
            out.append(f'<rect x="{bx:.1f}" y="{base_y - bh:.1f}" width="14" height="{bh:.1f}" rx="2" fill="{colr}"/>')
            out.append(_t(f"{bx + 7:.1f}", f"{base_y - bh - 3:.1f}", val, 10, MUTED, anchor="middle"))
        wd = date.fromisoformat(e["date"]).strftime("%a")
        out.append(_t(f"{sx + slot_w / 2:.1f}", base_y + 13, wd, 10, MUTED, anchor="middle"))
    return "".join(out)


def render_svg(state: dict) -> str:
    W, H = 820, 392
    p = state["probability"]
    hist = state["history"]
    label, label_col = rating(p)
    last_res = state.get("last_result")
    delta = state.get("last_delta", 0.0)

    up = delta >= 0
    trend_col = GREEN if (up and last_res not in ("MISS", "CRASH", "MANIP")) else RED
    if not hist:
        trend_col = GREEN

    # Series for sparkline
    recent = hist[-30:]
    series = ([recent[0]["prob_before"]] + [e["probability"] for e in recent]) if recent else []

    # Status line
    if p >= 50:
        note = "Recruiters, please stop. I'm overwhelmed. (Obviously fake.)"
    elif state.get("last_note"):
        note = state["last_note"]
    else:
        note = random.Random("init").choice(NOTES["INIT"])
    note_lines = textwrap.wrap(note, 84)[:2]

    updated = state.get("updated")
    pend = state.get("pending")

    o = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
             f'role="img" aria-labelledby="t d" font-family="{FONT}">')
    o.append(f'<title id="t">Hire probability: {p:.2f}%</title>')
    o.append(f'<desc id="d">Live "hire probability" exchange. Analyst rating {label}. '
             f'Current streak {state["streak"]} correct predictions. Not financial advice.</desc>')
    o.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="{BG}" stroke="{BORDER}"/>')

    # Header
    o.append(_t(32, 40, "$HIRED", 20, GREEN, "bold"))
    o.append(_t(132, 40, "HIRE PROBABILITY EXCHANGE", 13, MUTED))
    o.append(f'<circle cx="622" cy="35" r="4" fill="{GREEN}"><animate attributeName="opacity" values="1;0.25;1" dur="2s" repeatCount="indefinite"/></circle>')
    o.append(_t(632, 40, "LIVE", 12, GREEN, "bold"))
    o.append(_t(788, 40, f"{updated} IST" if updated else "PRE-MARKET", 13, MUTED, anchor="end"))
    o.append(f'<line x1="32" y1="56" x2="788" y2="56" stroke="{GRID}" stroke-width="1"/>')

    # Left column
    o.append(_t(32, 90, "HIRE PROBABILITY", 12, MUTED, style='letter-spacing="1"'))
    o.append(_t(32, 152, f"{p:.2f}%", 64, TEXT, "bold"))
    if hist:
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "■")
        o.append(
            f'<text x="32" y="184" font-size="18" font-weight="bold" fill="{trend_col}">'
            f'{arrow} {delta:+.2f}<tspan fill="{MUTED}" font-weight="normal" font-size="14"> pts  ·  {RESULT_LABEL[last_res].split(" ", 1)[1].upper()}</tspan></text>'
        )
    else:
        o.append(_t(32, 184, "■ 0.00 pts  ·  IPO DAY", 16, MUTED))

    badge = f"ANALYST RATING: {label}"
    bw = len(badge) * 7.9 + 24
    o.append(f'<rect x="32" y="202" width="{bw:.0f}" height="28" rx="6" fill="{label_col}" fill-opacity="0.14" stroke="{label_col}"/>')
    o.append(_t(44, 221, badge, 13, label_col, "bold"))

    if pend:
        o.append(_t(32, 260, f"Today's call: {pend['predicted']} commit{'s' if pend['predicted'] != 1 else ''}", 14, TEXT))
        o.append(_t(32, 279, f"(7-day avg {pend['avg7']}, settles 00:00 IST)", 12, MUTED))
    else:
        o.append(_t(32, 260, "Today's call: pending", 14, TEXT))
    o.append(_t(32, 298, f"Streak: {state['streak']} correct  ·  best {state['best_streak']}", 12, MUTED))

    # Right column: sparkline + bars
    o.append(_t(430, 90, "PROBABILITY · LAST 30 SESSIONS", 12, MUTED, style='letter-spacing="1"'))
    o.append(_sparkline(series, 430, 106, 358, 84, trend_col))
    o.append(_t(430, 226, "PREDICTED (GREY) VS ACTUAL · LAST 7", 12, MUTED, style='letter-spacing="1"'))
    o.append(_bars(hist[-7:], 430, 292, 358, 46))

    # Footer
    o.append(f'<line x1="32" y1="318" x2="788" y2="318" stroke="{GRID}" stroke-width="1"/>')
    for i, ln in enumerate(note_lines):
        o.append(_t(32, 342 + i * 18, ("“" if i == 0 else "") + ln + ("”" if i == len(note_lines) - 1 else ""),
                    14, AMBER, style='font-style="italic"'))
    o.append(_t(32, 380, "Not financial advice. Also not a job guarantee.", 11, MUTED))
    o.append(_t(788, 380, "updated daily by a GitHub Action", 11, MUTED, anchor="end"))
    o.append("</svg>")
    return "\n".join(o)


# --------------------------------------------------------------------------- #
# README block
# --------------------------------------------------------------------------- #
def render_block(state: dict) -> str:
    stamp = (state.get("updated") or "0").replace("-", "")
    p = state["probability"]
    label, _ = rating(p)
    alt = f"Hire probability {p:.2f}% (analyst rating: {label}). Streak: {state['streak']}."

    lines = [
        '<div align="center">',
        "",
        f'<img src="assets/ticker.svg?v={stamp}" alt="{alt}" width="820">',
        "",
        "</div>",
        "",
    ]

    rows = []
    pend = state.get("pending")
    if pend:
        rows.append(f"| **{pend['for_date']}** (today) | {pend['predicted']} | ⏳ | Market open | | |")
    for e in reversed(state["history"][-5:]):
        rows.append(
            f"| {e['date']} | {e['predicted']} | {e['actual']} | {RESULT_LABEL[e['result']]} "
            f"| {e['delta']:+.2f} | {e['probability']:.2f}% |"
        )
    if rows:
        lines += [
            "| Date (IST) | Predicted | Actual | Result | Δ pts | Hire probability |",
            "|---|:-:|:-:|---|:-:|:-:|",
            *rows,
            "",
        ]

    lines += [
        "<details>",
        "<summary>How does this work? (a.k.a. why is this in my README)</summary>",
        "",
        "- Every day at 00:05 IST a GitHub Action **predicts** how many commits I'll make that day (rounded 7-day average).",
        "- The next midnight it fetches my **real** commit count and settles the trade.",
        f"- Exact hit: **+{REWARD_EXACT:g}** pts. Off by one: **+{REWARD_NEAR:g}** pts. Streaks add a small bonus.",
        f"- Miss: **{PENALTY_MISS:g}** pts. Zero commits after predicting some: **{PENALTY_CRASH:g}** pts.",
        f"- {MANIP_MIN_COMMITS}+ commits and {MANIP_MULTIPLIER}x the forecast counts as market manipulation: **{PENALTY_MANIP:g}** pts.",
        "- Probability is 100% fiction. The 100% real part: I actually ship code, and I'm actually looking for a job.",
        "",
        "</details>",
    ]
    return "\n".join(lines)


def update_readme(block: str) -> None:
    if not README_FILE.exists():
        sys.exit("README.md not found.")
    text = README_FILE.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START_MARK) + r".*?" + re.escape(END_MARK), re.S)
    if not pattern.search(text):
        sys.exit(f"README.md is missing the markers {START_MARK} ... {END_MARK}")
    new = pattern.sub(lambda _m: f"{START_MARK}\n{block}\n{END_MARK}", text)
    if new != text:
        README_FILE.write_text(new, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mock", action="store_true", help="use fake commit counts (no network)")
    ap.add_argument("--render-only", action="store_true", help="only re-render files from data.json")
    ap.add_argument("--today", help="override today's IST date, YYYY-MM-DD (for testing)")
    ap.add_argument("--login", default=os.environ.get("GH_LOGIN"), help="GitHub username")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else datetime.now(IST).date()
    state = load_state()

    if not args.render_only:
        pending = state.get("pending")
        needs_settle = bool(pending) and pending["for_date"] < today.isoformat()

        wanted = {today - timedelta(days=i) for i in range(1, 8)}
        if needs_settle:
            wanted.add(date.fromisoformat(pending["for_date"]))
        wanted_sorted = sorted(wanted)

        if args.mock:
            counts = mock_commit_counts(wanted_sorted)
        else:
            token = os.environ.get("GH_TOKEN")
            if not token or not args.login:
                sys.exit("Set GH_TOKEN and GH_LOGIN (or pass --login), or use --mock.")
            counts = fetch_commit_counts(args.login, wanted_sorted, token)

        if needs_settle:
            settle(state, pending, counts[date.fromisoformat(pending["for_date"])])
            state["pending"] = None

        if not state.get("pending"):
            predicted, avg = predict(counts, today)
            state["pending"] = {"for_date": today.isoformat(), "predicted": predicted, "avg7": avg}

        state["opened"] = state["opened"] or today.isoformat()
        state["updated"] = today.isoformat()
        save_state(state)

    SVG_FILE.parent.mkdir(parents=True, exist_ok=True)
    SVG_FILE.write_text(render_svg(state), encoding="utf-8")
    update_readme(render_block(state))

    p = state["probability"]
    print(f"[{state.get('updated')}] hire probability {p:.2f}% | streak {state['streak']} | pending {state.get('pending')}")


if __name__ == "__main__":
    main()
