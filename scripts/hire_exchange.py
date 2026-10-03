#!/usr/bin/env python3
"""
$HIRED - the Hire Probability Exchange.

Every run (00:05 IST via GitHub Actions):
  1. SETTLE  - if a prediction is pending for a day that has ended, fetch the real
               commit count for that IST day and score it. Also checks hourly
               manipulation (10+ commits within any 60-minute window) and settles
               visitor votes from the day's issue reactions.
  2. PREDICT - forecast today's commit count (rounded mean of the last 7 IST days).
  3. VOTE    - open (or update) an issue for visitors to vote HIT or MISS.
  4. WRAP    - on the 1st of each month, publish an "earnings report".
  5. RENDER  - rewrite data.json, assets/ticker.svg and the block inside README.md
               between the HIRE_EXCHANGE markers.

Standard library only. No pip install needed.

Usage:
  python scripts/hire_exchange.py                 # real run (needs GH_TOKEN, GH_LOGIN)
  python scripts/hire_exchange.py --mock          # fake commit counts, no network
  python scripts/hire_exchange.py --render-only   # just re-render from data.json
  python scripts/hire_exchange.py --today 2026-10-01 --mock   # simulate a date (writes nothing)
  python scripts/hire_exchange.py --today 2026-10-01 --mock --write   # ...and overwrite the files
"""
from __future__ import annotations

import argparse
import json
import os
import random
import hashlib
import re
import sys
import textwrap
import time
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
REWARD_NEAR = 0.5          # points gained on near hit or beat
PENALTY_MISS = -0.25
PENALTY_CRASH = -0.5       # zero commits when at least one was predicted
PENALTY_MANIP = -1.5       # suspicious spike
STREAK_BONUS = 0.1         # extra per consecutive good session (after the first)...
STREAK_BONUS_CAP = 5       # ...up to this many steps

# The single definition of a "good" session. Every consumer must use this:
# the hit rate, the streak, and the visitor-vote settlement all read it, so a
# result can never be a hit in one place and a miss in another.
GOOD_RESULTS = ("HIT", "NEAR", "BEAT")

# Market manipulation: a burst of commits inside the profile repo. Overachieving a
# low forecast is not fraud, so there is no ratio rule.
HOURLY_MANIP_MIN = 10
HOURLY_WINDOW_MIN = 60

HISTORY_KEEP = 120         # settled sessions kept in data.json
README_ROWS = 14           # history rows shown in the README table

# GraphQL retry
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0     # seconds; doubles each attempt

# Visitor voting issue
VOTE_ISSUE_TITLE = "$HIRED Daily Forecast — Vote: will the bot hit today's number?"
VOTE_REACT_HIT = "+1"      # 👍 = visitor says HIT
VOTE_REACT_MISS = "-1"     # 👎 = visitor says MISS

# Monthly wrap-up
WRAP_NOTES = [
    "Recruiter sentiment: unchanged. Model sentiment: smug.",
    "The alpha is imaginary but the vibes are quarterly-confirmed.",
    "Earnings beat expectations. Expectations were fictional.",
    "Another month, another set of predictions nobody asked for.",
]

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
    "BEAT": [
        "Beat the forecast by a mile. The model is now upgrading its assumptions.",
        "Volume above forecast. Recruiters noticed, recruiters are confused.",
        "Overdelivered. The forecast was simply wrong, and happily so.",
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
        "🚨 Manipulation: 10+ commits inside an hour. The SEC (Stack Enforcement Committee) is watching.",
        "Market manipulation detected. SEBI has entered the chat.",
        "Suspicious volume spike. Empty commits are not a personality.",
        "Volume spike within 60 minutes. Either a deadline or a breakdown. Probably both.",
        "Pump and dump alert. Regulators have been notified. By me. Sarcastically.",
        "Commits-per-hour exceeds regulatory limits. Please gamble responsibly.",
    ],
    "INIT": [
        "Exchange opens today. Listing price: optimistic. Fundamentals: pending.",
        "IPO day. Analysts are being polite about the valuation.",
    ],
}

RESULT_LABEL = {
    "HIT": "✅ Exact hit",
    "BEAT": "🚀 Beat",
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
        "visitors": {"hit": 0, "miss": 0, "correct": 0},  # visitor vote tallies
        "vote_issue": None,     # issue number for today's voting issue
        "monthly_wrap": None,   # last month a wrap-up was published (YYYY-MM)
    }


def load_state() -> dict:
    state = default_state()
    if DATA_FILE.exists():
        state.update(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    return state


def save_state(state: dict) -> None:
    DATA_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Stats (used in SVG + README)
# --------------------------------------------------------------------------- #
def stats(history: list[dict], best_streak: int) -> dict:
    n = len(history)
    if n == 0:
        return {"n": 0, "hit_rate": 0.0, "exact": 0, "near": 0, "beat": 0, "miss": 0, "best_streak": best_streak}
    exact = sum(e["result"] == "HIT" for e in history)
    near = sum(e["result"] == "NEAR" for e in history)
    beat = sum(e["result"] == "BEAT" for e in history)  # all three are GOOD_RESULTS
    miss = sum(e["result"] in ("MISS", "CRASH", "MANIP") for e in history)
    return {
        "n": n,
        "hit_rate": sum(e["result"] in GOOD_RESULTS for e in history) / n,
        "exact": exact,
        "near": near,
        "beat": beat,
        "miss": miss,
        "best_streak": best_streak,
    }


def volume_line(history: list[dict], window: int = 30) -> str:
    """How much actually got shipped. This is the only number on the card that is
    about the developer rather than about a 7-day-mean predictor's accuracy."""
    recent = history[-window:]
    if not recent:
        return "No sessions yet \u2014 market opens tomorrow."
    shipped = sum(e["actual"] for e in recent)
    days = len(recent)
    off = sum(e["actual"] == 0 for e in recent)
    line = f"{shipped} commits in {days} session{'s' if days != 1 else ''} \u00b7 {shipped / days:.0f}/day"
    if off == 0:
        return line + " \u00b7 never missed a day"
    return line + f" \u00b7 {off} day{'s' if off != 1 else ''} at zero"


def stats_line(history: list[dict], best_streak: int) -> str:
    s = stats(history, best_streak)
    if s["n"] == 0:
        return "No sessions yet — market opens tomorrow."
    return (f"{s['n']} sessions · {s['hit_rate']:.0%} hit rate · "
            f"best streak {s['best_streak']} · {s['exact']} exact / {s['near']} near / "
            f"{s['beat']} beat / {s['miss']} miss")


# --------------------------------------------------------------------------- #
# Commit counts - GraphQL with retry
# --------------------------------------------------------------------------- #
def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_bounds_utc(d: date) -> tuple[str, str]:
    """Start/end of an IST calendar day, expressed in UTC for the GitHub API."""
    start = datetime(d.year, d.month, d.day, tzinfo=IST)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return _utc(start), _utc(end)


def _request_json(req: request.Request, attempts: int = RETRY_ATTEMPTS) -> dict:
    """POST/GET with exponential backoff. Retries on network errors and 5xx."""
    delay = RETRY_BASE_DELAY
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            with request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except Exception as e:  # URLError, HTTPError, timeout, JSONDecodeError
            last_err = e
            code = getattr(e, "code", None)
            # Don't retry 4xx (auth, bad request) — only network/5xx
            if code is not None and 400 <= code < 500:
                raise
            if i < attempts - 1:
                print(f"  retry {i+1}/{attempts-1} after error: {e} (sleeping {delay:.0f}s)", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
    raise RuntimeError(f"GitHub API failed after {attempts} attempts: {last_err}")


def fetch_commit_counts(login: str, days: list[date], token: str) -> dict[date, int]:
    """One GraphQL request, one aliased contributionsCollection per IST day.

    ponytail: totalCommitContributions is the contribution-graph number, not a
    commit count - it excludes forks and repos without push access, and it lags.
    Swap in the REST /repos/*/commits listing if that ever matters.
    """
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
    payload = _request_json(req)
    if payload.get("errors") or not payload.get("data", {}).get("user"):
        raise RuntimeError(f"GitHub GraphQL error: {payload.get('errors') or 'user not found'}")
    user = payload["data"]["user"]
    return {d: int(user[f"d{d:%Y%m%d}"]["totalCommitContributions"]) for d in days}


def mock_commit_counts(days: list[date]) -> dict[date, int]:
    pool = [0, 1, 2, 2, 3, 3, 3, 4, 5, 6, 14]
    return {d: random.Random(f"mock-{d.isoformat()}").choice(pool) for d in days}


# --------------------------------------------------------------------------- #
# Hourly manipulation detection (REST API)
# --------------------------------------------------------------------------- #
def fetch_commit_timestamps(login: str, target: date, token: str) -> list[datetime]:
    """Commit timestamps inside the profile repo for one IST day, sorted UTC.
    Empty if the API fails (graceful). Scoped to the profile repo on purpose:
    a burst of commits there games the contribution graph, whereas the same
    burst spread over real repos is just a work session."""
    s, e = day_bounds_utc(target)
    ts: list[datetime] = []
    page = 1
    while page <= 5:  # max 5 pages = 500 commits, plenty
        url = (f"https://api.github.com/repos/{login}/{login}/commits"
               f"?since={s}&until={e}&per_page=100&page={page}")
        req = request.Request(url, headers={
            "Authorization": f"bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "hire-exchange",
        })
        try:
            payload = _request_json(req, attempts=2)
        except Exception:
            break  # graceful: hourly check is best-effort
        if not payload:
            break
        for c in payload:
            try:
                ts.append(datetime.fromisoformat(c["commit"]["committer"]["date"].replace("Z", "+00:00")))
            except (KeyError, ValueError):
                continue
        if len(payload) < 100:
            break
        page += 1
    return sorted(ts)


def is_hourly_manipulation(timestamps: list[datetime]) -> bool:
    """True if HOURLY_MANIP_MIN commits fall within any HOURLY_WINDOW_MIN window."""
    if len(timestamps) < HOURLY_MANIP_MIN:
        return False
    n = len(timestamps)
    j = 0
    for i in range(n):
        while j < n and (timestamps[j] - timestamps[i]).total_seconds() <= HOURLY_WINDOW_MIN * 60:
            j += 1
        if j - i >= HOURLY_MANIP_MIN:
            return True
    return False


def mock_hourly_manipulation(actual: int, seed: str) -> bool:
    """Deterministic mock: ~15% chance of hourly manipulation on days with enough commits."""
    if actual < HOURLY_MANIP_MIN:
        return False
    return random.Random(f"hourly-{seed}").random() < 0.15


# --------------------------------------------------------------------------- #
# Visitor voting via issue reactions
# --------------------------------------------------------------------------- #
def _gh_api(method: str, path: str, token: str, body: dict | None = None):
    """Minimal GitHub REST API helper. Returns parsed JSON or None on failure."""
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(url, data=data, method=method, headers={
        "Authorization": f"bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "hire-exchange",
    })
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except Exception as e:
        print(f"  gh_api {method} {path} failed: {e}", file=sys.stderr)
        return None


def _count_vote_reactions(repo: str, issue_no: int, token: str) -> tuple[int, int] | None:
    """(hit, miss) reaction totals. None if the first page failed."""
    hit = miss = 0
    for page in range(1, 11):  # reactions are paginated; page 1 alone is not enough
        chunk = _gh_api("GET", f"/repos/{repo}/issues/{issue_no}/reactions?per_page=100&page={page}", token)
        if chunk is None:
            return None if page == 1 else (hit, miss)
        for r in chunk:
            if r.get("content") == VOTE_REACT_HIT:
                hit += 1
            elif r.get("content") == VOTE_REACT_MISS:
                miss += 1
        if len(chunk) < 100:
            break
    return hit, miss


def settle_visitor_votes(state: dict, actual: int, token: str) -> None:
    """Count 👍/👎 reactions on yesterday's voting issue and update visitor tallies."""
    issue_no = state.get("vote_issue")
    if not issue_no:
        return

    repo = state.get("_repo", "")
    votes = _count_vote_reactions(repo, issue_no, token)
    if votes is None:
        return
    hit_votes, miss_votes = votes
    # Did the visitors win? (They vote HIT if they think the bot's prediction lands)
    pred = state.get("_last_vote_predicted")
    # settle() already scored this session. Re-deriving it here would disagree on
    # BEAT (good) and MANIP (decided by the burst check, not by classify).
    result = state.get("last_result") or classify(pred, actual)
    visitors = state.setdefault("visitors", {"hit": 0, "miss": 0, "correct": 0})
    visitors["hit"] += hit_votes
    visitors["miss"] += miss_votes
    if pred is not None:
        visitor_said_hit = hit_votes > miss_votes
        visitor_was_right = (result in GOOD_RESULTS) == visitor_said_hit
        if visitor_was_right:
            visitors["correct"] += hit_votes + miss_votes
    # Close the issue by commenting the result
    comment = (f"**Settled:** forecast was {pred}, actual was {actual} → "
               f"{RESULT_LABEL.get(result, 'n/a')}. "
               f"Visitors: {hit_votes} 👍 / {miss_votes} 👎.")
    _gh_api("POST", f"/repos/{repo}/issues/{issue_no}/comments", token, {"body": comment})
    state["vote_issue"] = None


def create_vote_issue(state: dict, token: str, login: str, mock: bool = False) -> None:
    """Open today's voting issue so visitors can vote on the forecast."""
    if mock:
        return  # don't create issues in mock mode
    if state.get("vote_issue"):
        return  # already open for today
    pred = state["pending"]["predicted"]
    body = (
        f"## Today's forecast: **{pred} commit{'s' if pred != 1 else ''}**\n\n"
        f"Will the bot's prediction be correct (or within ±1)?\n\n"
        f"- 👍 **+1** reaction = I think it'll **HIT**\n"
        f"- 👎 **-1** reaction = I think it'll **MISS**\n\n"
        f"Settles tomorrow at 00:05 IST. No prize. Just bragging rights.\n\n"
        f"*Not financial advice. Also not a job guarantee.*"
    )
    repo = f"{login}/{login}"
    result = _gh_api("POST", f"/repos/{repo}/issues", token,
                     {"title": VOTE_ISSUE_TITLE, "body": body, "labels": ["hire-exchange"]})
    if result and "number" in result:
        state["vote_issue"] = result["number"]
        state["_repo"] = repo


# --------------------------------------------------------------------------- #
# Monthly wrap-up
# --------------------------------------------------------------------------- #
def monthly_wrap(state: dict, today: date) -> str | None:
    """Generate an earnings-report note on the 1st of each month. Returns None if not due."""
    if today.day != 1:
        return None
    month_key = f"{today.year:04d}-{today.month:02d}"
    if state.get("monthly_wrap") == month_key:
        return None  # already published this month
    state["monthly_wrap"] = month_key
    # Find previous month's sessions
    prev_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    month_sessions = [e for e in state["history"] if e["date"].startswith(prev_month)]
    if not month_sessions:
        return None
    s = stats(month_sessions, state["best_streak"])
    prob_change = state["probability"] - month_sessions[0]["prob_before"]
    return (
        f"{prev_month} earnings report: {s['n']} sessions, "
        f"{s['hit_rate']:.0%} hit rate, probability {'+' if prob_change >= 0 else ''}{prob_change:.1f}pts. "
        f"{random.Random(month_key).choice(WRAP_NOTES)}"
    )


# --------------------------------------------------------------------------- #
# Game logic
# --------------------------------------------------------------------------- #
def predict(counts: dict[date, int], today: date) -> tuple[int, float]:
    vals = [counts[today - timedelta(days=i)] for i in range(7, 0, -1)]
    avg = sum(vals) / len(vals)
    return int(avg + 0.5), round(avg, 2)


def classify(predicted: int, actual: int) -> str:
    """Score the trade. Manipulation is decided by the burst check, not here.

    Overshooting the forecast is not a miss — on a profile whose entire pitch
    is volume, shipping more than predicted is the good outcome.
    """
    if actual == 0 and predicted >= 1:
        return "CRASH"
    diff = actual - predicted
    if diff == 0:
        return "HIT"
    if abs(diff) <= TOLERANCE:
        return "NEAR"
    if diff > 0:
        return "BEAT"
    return "MISS"


def streak_from(history: list[dict]) -> int:
    """Consecutive good sessions ending at the most recent one."""
    n = 0
    for e in reversed(history):
        if e["result"] in GOOD_RESULTS:
            n += 1
        else:
            break
    return n


def best_streak_from(history: list[dict]) -> int:
    """Longest run of consecutive good sessions ever recorded."""
    best = run = 0
    for e in history:
        run = run + 1 if e["result"] in GOOD_RESULTS else 0
        best = max(best, run)
    return best


def settle(state: dict, pending: dict, actual: int, hourly_manip: bool = False) -> None:
    predicted = pending["predicted"]
    result = "MANIP" if hourly_manip else classify(predicted, actual)
    before = state["probability"]
    streak = streak_from(state["history"])  # read before this session is appended

    if result in GOOD_RESULTS:
        bonus = STREAK_BONUS * min(streak, STREAK_BONUS_CAP)
        base = {"HIT": REWARD_EXACT, "NEAR": REWARD_NEAR, "BEAT": REWARD_NEAR}[result]
        delta = base + bonus
    else:
        delta = {"MISS": PENALTY_MISS, "CRASH": PENALTY_CRASH, "MANIP": PENALTY_MANIP}[result]

    raw = before + delta
    after = round(min(PROB_MAX, max(PROB_MIN, raw)), 2)
    # A clamped score is why the displayed delta can disagree with the price move.
    clamped = "ceiling" if raw > PROB_MAX else "floor" if raw < PROB_MIN else None

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
            "hourly_manip": hourly_manip,
            "score": round(delta, 2),
            "delta": round(after - before, 2),
            "clamped": clamped,
            "prob_before": before,
            "probability": after,
            "note": note,
        }
    )
    state["history"] = state["history"][-HISTORY_KEEP:]
    state["probability"] = after
    state["last_result"] = result
    state["last_delta"] = round(delta, 2)
    state["last_clamped"] = clamped
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
RESULT_COLOR = {"HIT": GREEN, "NEAR": GREEN, "BEAT": GREEN, "MISS": RED, "CRASH": RED, "MANIP": AMBER}


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
    out.append(_t(x0 + w, y0 - 4, f"hi {max(series):.2f}%", 11, MUTED, anchor="end"))
    out.append(_t(x0 + w, y0 + h + 12, f"lo {min(series):.2f}%", 11, MUTED, anchor="end"))
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
            out.append(_t(f"{bx + 7:.1f}", f"{base_y - bh - 3:.1f}", val, 11, MUTED, anchor="middle"))
        wd = date.fromisoformat(e["date"]).strftime("%a")
        out.append(_t(f"{sx + slot_w / 2:.1f}", base_y + 13, wd, 11, MUTED, anchor="middle"))
    return "".join(out)


def render_svg(state: dict) -> str:
    # Single column at 640px. GitHub scales an <img> to the viewport, so a wide
    # two-column layout rendered 10px labels at ~4px on a phone. Narrower +
    # stacked means less downscaling and nothing is ever pushed off-canvas.
    W, H = 640, 584
    M, R = 32, W - 32
    p = state["probability"]
    hist = state["history"]
    label, label_col = rating(p)
    last_res = state.get("last_result")
    delta = state.get("last_delta", 0.0)
    clamped = state.get("last_clamped")

    up = delta >= 0
    trend_col = GREEN if (up and last_res not in ("MISS", "CRASH", "MANIP")) else RED
    if not hist:
        trend_col = GREEN

    recent = hist[-30:]
    series = ([recent[0]["prob_before"]] + [e["probability"] for e in recent]) if recent else []

    # Status line
    if p >= 50:
        note = "Recruiters, please stop. I'm overwhelmed. (Obviously fake.)"
    elif state.get("last_note"):
        note = state["last_note"]
    else:
        note = random.Random("init").choice(NOTES["INIT"])
    note_lines = textwrap.wrap(note, 88)[:2]

    updated = state.get("updated")
    pend = state.get("pending")

    o = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
             f'role="img" aria-labelledby="t d" font-family="{FONT}">')
    o.append('<style>@media (prefers-reduced-motion: reduce){ .pulse animate { display: none } }</style>')
    o.append(f'<title id="t">Hire probability: {p:.2f}%</title>')
    o.append(f'<desc id="d">Live "hire probability" exchange. Analyst rating {label}. '
             f'Current streak {state["streak"]} good sessions. {escape(volume_line(hist))} '
             f'Not financial advice.</desc>')
    o.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="{BG}" stroke="{BORDER}"/>')

    # Header
    o.append(_t(M, 36, "$HIRED", 20, GREEN, "bold"))
    o.append(_t(132, 36, "HIRE PROBABILITY EXCHANGE", 13, MUTED))
    o.append(f'<circle class="pulse" cx="{R - 96}" cy="31" r="4" fill="{GREEN}">'
             f'<animate attributeName="opacity" values="1;0.25;1" dur="2s" repeatCount="indefinite"/></circle>')
    o.append(_t(R - 86, 36, "LIVE", 12, GREEN, "bold"))
    o.append(_t(R, 36, f"{updated} IST" if updated else "PRE-MARKET", 13, MUTED, anchor="end"))
    o.append(f'<line x1="{M}" y1="52" x2="{R}" y2="52" stroke="{GRID}" stroke-width="1"/>')

    # Headline
    o.append(_t(M, 78, "HIRE PROBABILITY", 12, MUTED, style='letter-spacing="1"'))
    o.append(_t(M, 134, f"{p:.2f}%", 56, TEXT, "bold"))
    if hist:
        arrow = "\u25b2" if delta > 0 else ("\u25bc" if delta < 0 else "\u25a0")
        tail = f'  \u00b7  {escape(RESULT_LABEL[last_res].split(" ", 1)[1].upper())}'
        if clamped:
            tail += f'  \u00b7  AT {clamped.upper()}'
        o.append(
            f'<text x="{M}" y="164" font-size="18" font-weight="bold" fill="{trend_col}">'
            f'{arrow} {delta:+.2f}<tspan fill="{MUTED}" font-weight="normal" '
            f'font-size="13">{escape(tail)}</tspan></text>'
        )
    else:
        o.append(_t(M, 164, "\u25a0 0.00 pts  \u00b7  IPO DAY", 16, MUTED))

    badge = f"ANALYST RATING: {label}"
    bw = len(badge) * 7.9 + 24
    o.append(f'<rect x="{M}" y="182" width="{bw:.0f}" height="28" rx="6" fill="{label_col}" '
             f'fill-opacity="0.14" stroke="{label_col}"/>')
    o.append(_t(M + 12, 201, badge, 13, label_col, "bold"))

    # Volume first, accuracy second. The predictor is a 7-day mean and will always
    # look bad; the commit count is the part that is actually about me.
    o.append(_t(M, 242, volume_line(hist), 14, TEXT))
    o.append(_t(M, 262, stats_line(hist, state["best_streak"]), 11, MUTED))

    if pend:
        o.append(_t(M, 288, f"Today's call: {pend['predicted']} commit{'s' if pend['predicted'] != 1 else ''}", 14, TEXT))
        o.append(_t(M, 306, f"(7-day avg {pend['avg7']}, settles 00:00 IST)", 12, MUTED))
    else:
        o.append(_t(M, 288, "Today's call: pending", 14, TEXT))
    o.append(_t(M, 326, f"Streak: {state['streak']} good  \u00b7  best {state['best_streak']}", 12, MUTED))

    o.append(f'<line x1="{M}" y1="344" x2="{R}" y2="344" stroke="{GRID}" stroke-width="1"/>')

    # Charts
    o.append(_t(M, 366, "PROBABILITY \u00b7 LAST 30 SESSIONS", 12, MUTED, style='letter-spacing="1"'))
    o.append(_sparkline(series, M, 380, R - M, 54, trend_col))

    o.append(_t(M, 464, "SHIPPED vs FORECAST \u00b7 LAST 7", 12, MUTED, style='letter-spacing="1"'))
    o.append(f'<rect x="{M + 214}" y="456" width="9" height="9" rx="2" fill="{BAR_PRED}"/>')
    o.append(_t(M + 228, 464, "forecast", 11, MUTED))
    o.append(f'<rect x="{M + 290}" y="456" width="9" height="9" rx="2" fill="{GREEN}"/>')
    o.append(_t(M + 304, 464, "shipped", 11, MUTED))
    o.append(_bars(hist[-7:], M, 528, R - M, 34))

    # Footer
    o.append(f'<line x1="{M}" y1="542" x2="{R}" y2="542" stroke="{GRID}" stroke-width="1"/>')
    for i, ln in enumerate(note_lines):
        o.append(_t(M, 560 + i * 15, ("\u201c" if i == 0 else "") + ln + ("\u201d" if i == len(note_lines) - 1 else ""),
                    12, AMBER, style='font-style="italic"'))
    o.append(_t(M, 578, "Not financial advice. Also not a job guarantee.", 11, MUTED))
    o.append("</svg>")
    return "\n".join(o)


# --------------------------------------------------------------------------- #
# README block
# --------------------------------------------------------------------------- #
def render_block(state: dict) -> str:
    # Content hash, not the date: camo caches images by URL, so a same-day fix
    # would otherwise keep serving the stale ticker.
    stamp = hashlib.sha1(render_svg(state).encode()).hexdigest()[:8]
    p = state["probability"]
    label, _ = rating(p)
    alt = (f"Hire probability {p:.2f}% (analyst rating: {label}). "
           f"{volume_line(state['history'])}. Streak: {state['streak']}.")

    lines = [
        '<div align="center">',
        "",
        f'<img src="assets/ticker.svg?v={stamp}" alt="{escape(alt)}" width="640">',
        "",
        "</div>",
        "",
        "<br>",
        "",
    ]

    # Stats line (NEW)
    s = stats(state["history"], state["best_streak"])
    if s["n"] > 0:
        lines += [f"*{stats_line(state['history'], state['best_streak'])}*", ""]

    # Monthly wrap (NEW)
    if state.get("monthly_wrap_note"):
        lines += [f"> 📊 {state['monthly_wrap_note']}", ""]
        state.pop("monthly_wrap_note", None)

    # Visitor votes summary (NEW)
    vis = state.get("visitors", {"hit": 0, "miss": 0})
    if vis.get("hit", 0) or vis.get("miss", 0):
        lines += [f"*Visitors: {vis.get('hit', 0)} 👍 / {vis.get('miss', 0)} 👎 votes — [vote on today's forecast](https://github.com/hemv-857/hemv-857/issues)*", ""]

    rows = []
    pend = state.get("pending")
    if pend:
        rows.append(f"| **{pend['for_date']}** (today) | {pend['predicted']} | ⏳ | Market open | | |")
    for e in reversed(state["history"][-README_ROWS:]):
        manip_flag = " 🚨" if e.get("hourly_manip") else ""
        if e.get("clamped"):
            # A clamped score is why the pts column can disagree with the price move.
            manip_flag += f" {'⌄' if e['clamped'] == 'floor' else '⌃'}{e['clamped']}"
        rows.append(
            f"| {e['date']} | {e['predicted']} | {e['actual']} | {RESULT_LABEL[e['result']]}{manip_flag} "
            f"| {e.get('score', e['delta']):+.2f} | {e['probability']:.2f}% |"
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
        f"- Beat the forecast by more than {TOLERANCE} commit and the probability **rises**: **+{REWARD_NEAR:g}** pts. Shipping more than predicted is the whole pitch, so overachieving is never a miss.",
        f"- Market manipulation means one thing only: {HOURLY_MANIP_MIN}+ commits within {HOURLY_WINDOW_MIN} minutes **in this profile repo** — the only way to game the contribution graph. Overachieving a low forecast across real repos is not a crime. Penalty: **{PENALTY_MANIP:g}** pts.",
        "- **Visitors:** 👍/👎 on today's [voting issue](https://github.com/hemv-857/hemv-857/issues) to predict whether the bot hits. No prize, just bragging rights.",
        "- **Monthly:** on the 1st, an earnings report summarises the previous month.",
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
    ap.add_argument("--write", action="store_true",
                    help="let --mock overwrite data.json / README.md / ticker.svg")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else datetime.now(IST).date()
    state = load_state()
    # --mock runs on dice rolls. Writing them into the tracked files would
    # corrupt the real ticker, so that needs an explicit opt-in.
    may_write = not args.mock or args.write
    if not may_write:
        print("  mock run: not writing data.json / README.md / ticker.svg (pass --write to override)")

    if not args.render_only:
        pending = state.get("pending")
        needs_settle = bool(pending) and pending["for_date"] < today.isoformat()

        if needs_settle:
            # Days that ended with no prediction cannot be scored - there is no
            # forecast to settle them against, and inventing one would be a lie.
            # Surface the gap instead of letting history look complete.
            gap = (today - date.fromisoformat(pending["for_date"])).days - 1
            if gap > 0:
                print(f"  WARNING: {gap} day(s) were never predicted and are absent from "
                      f"history: {pending['for_date']} -> {(today - timedelta(days=1))}",
                      file=sys.stderr)

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
            settle_date = date.fromisoformat(pending["for_date"])
            actual = counts[settle_date]

            # Hourly manipulation check (REST API, best-effort)
            hourly_manip = False
            if not args.mock:
                try:
                    ts = fetch_commit_timestamps(args.login, settle_date, token)
                    hourly_manip = is_hourly_manipulation(ts)
                except Exception as e:
                    print(f"  hourly check skipped: {e}", file=sys.stderr)
            else:
                hourly_manip = mock_hourly_manipulation(actual, pending["for_date"])

            settle(state, pending, actual, hourly_manip=hourly_manip)

            # Settle visitor votes
            if not args.mock:
                state["_repo"] = f"{args.login}/{args.login}"
                state["_last_vote_predicted"] = pending["predicted"]
                settle_visitor_votes(state, actual, token)
            else:
                # Simulate deterministic visitor votes in mock mode
                visitors = state.setdefault("visitors", {"hit": 0, "miss": 0, "correct": 0})
                rng = random.Random(f"votes-{pending['for_date']}")
                visitors["hit"] += rng.randint(0, 6)
                visitors["miss"] += rng.randint(0, 6)

            state["pending"] = None

        if not state.get("pending"):
            predicted, avg = predict(counts, today)
            state["pending"] = {"for_date": today.isoformat(), "predicted": predicted, "avg7": avg}

        # Derived, never stored-and-incremented: a re-settled or hand-edited
        # history can no longer leave these lying about the record.
        state["streak"] = streak_from(state["history"])
        state["best_streak"] = best_streak_from(state["history"])

        # Monthly wrap-up (NEW)
        wrap = monthly_wrap(state, today)
        if wrap:
            state["monthly_wrap_note"] = wrap
            print(f"  monthly wrap: {wrap}")

        # Create today's visitor voting issue (NEW)
        if not args.mock:
            token = os.environ.get("GH_TOKEN")
            if token and args.login:
                state["_repo"] = f"{args.login}/{args.login}"
                create_vote_issue(state, token, args.login)

        # Clean up internal keys before saving
        state.pop("_repo", None)
        state.pop("_last_vote_predicted", None)

        state["opened"] = state["opened"] or today.isoformat()
        state["updated"] = today.isoformat()
        if may_write:
            save_state(state)

    if may_write:
        SVG_FILE.parent.mkdir(parents=True, exist_ok=True)
        SVG_FILE.write_text(render_svg(state), encoding="utf-8")
        update_readme(render_block(state))

    p = state["probability"]
    print(f"[{state.get('updated')}] hire probability {p:.2f}% | streak {state['streak']} | pending {state.get('pending')}")


if __name__ == "__main__":
    main()
