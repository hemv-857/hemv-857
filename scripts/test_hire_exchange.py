import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import hire_exchange as h

# ---------------------------------------------------------------- the forecast
# A point forecast from a 7-day mean hit 10% of days: this account's volume
# swings from 1 to 136 commits, so +-1 is unreachable. The range must be honest.
counts = {date(2026, 10, 3) - timedelta(days=i): v
          for i, v in enumerate([5, 40, 12, 9, 60, 3, 22], start=1)}
lo, hi, avg = h.predict(counts, date(2026, 10, 3))
assert (lo, hi) == (3, 60), (lo, hi)
assert avg == 21.57, avg

# A range of one value is a point forecast, and must behave like one.
flat = {date(2026, 10, 3) - timedelta(days=i): 20 for i in range(1, 8)}
assert h.predict(flat, date(2026, 10, 3))[:2] == (20, 20)

# ------------------------------------------------------------------ the scoring
assert h.classify(3, 60, 12) == "HIT"        # inside the range
assert h.classify(3, 60, 60) == "HIT"        # edges count as inside
assert h.classify(3, 60, 3) == "HIT"
assert h.classify(3, 60, 2) == "NEAR"        # one commit short of the floor
assert h.classify(3, 60, 1) == "MISS"        # further under is a miss
# Everything above the range is a BEAT - there is no "too much" penalty left.
assert all(h.classify(3, 60, a) == "BEAT" for a in (61, 63, 64, 100, 10_000))
assert h.classify(3, 60, 0) == "CRASH"       # zero when the range expected work
assert h.classify(0, 0, 0) == "HIT"          # a zero-range day cannot crash
assert h.classify(20, 40, 5) == "MISS"       # underdelivering costs

# ------------------------------------------------- the reward follows the work
# Regression: shipping one commit PAST the range used to halve the payout, because
# a BEAT paid the same as a NEAR. More work must never be worth less.
LO, HI = 9, 40
pts = [h.score_session(LO, HI, a)[1] for a in range(LO, 200)]
assert pts == sorted(pts), "reward must rise with commits shipped"
assert h.score_session(LO, HI, HI + 1)[1] > h.score_session(LO, HI, LO)[1], \
    "beating the range must beat scraping its floor"
assert h.score_session(LO, HI, LO)[0] == "HIT" and h.score_session(LO, HI, LO)[1] == h.REWARD_FLOOR
assert h.score_session(LO, HI, HI)[1] == h.REWARD_CEIL
assert h.score_session(LO, HI, LO - 1) == ("NEAR", h.REWARD_EDGE)
assert h.score_session(LO, HI, 0) == ("CRASH", h.PENALTY_CRASH)
# One huge day cannot rocket the ticker on its own.
assert h.score_session(LO, HI, 10_000)[1] == h.REWARD_CEIL + h.OVERSHOOT_BONUS
# A flat forecast is a point forecast and must still grade sensibly.
# A flat forecast is a point forecast: an exact hit is the ceiling, not the floor.
assert h.score_session(20, 20, 20) == ("HIT", h.REWARD_CEIL)
assert h.score_session(20, 20, 19) == ("NEAR", h.REWARD_EDGE)
assert h.score_session(0, 0, 0)[0] == "HIT"
flat = [h.score_session(20, 20, a)[1] for a in range(1, 60)]
assert flat == sorted(flat), flat
# Under the floor everything falls away, in order.
below = [h.score_session(LO, HI, a)[1] for a in (0, 1, 2, LO - 2, LO - 1, LO)]
assert below == sorted(below), below
# classify() must be the label from the same function, never a second opinion.
for a in range(0, 200):
    assert h.classify(LO, HI, a) == h.score_session(LO, HI, a)[0]

# ------------------------------------------------------------------- the settle
def run(pending, actual, **kw):
    st = {"probability": 50.0, "history": []}
    h.settle(st, pending, actual, **kw)
    return st["history"][-1]

p = {"for_date": "2026-10-02", "lo": 3, "hi": 60}
e = run(p, 40)
assert (e["result"], (e["lo"], e["hi"])) == ("HIT", (3, 60)), e
assert e["score"] == round(h.score_session(3, 60, 40)[1], 2), e
assert e["probability"] == round(50.0 + e["score"], 2)

# Vacation: voided, worth nothing, breaks nothing.
assert run(p, 40, vacation=True)["score"] == 0.0
assert run(p, 40, vacation=True)["result"] == "SKIP"

# A clamped score must say so, or the pts column looks like a lie.
st = {"probability": h.PROB_MIN, "history": []}
h.settle(st, {"for_date": "2026-10-04", "lo": 20, "hi": 40}, 0)
assert st["history"][-1]["clamped"] == "floor"
st = {"probability": 99.5, "history": []}
h.settle(st, {"for_date": "2026-10-05", "lo": 20, "hi": 40}, 30)
assert st["history"][-1]["clamped"] == "ceiling"
st = {"probability": 50.0, "history": []}
h.settle(st, {"for_date": "2026-10-06", "lo": 20, "hi": 40}, 30)
assert st["history"][-1]["clamped"] is None

# Manipulation is decided by the burst check and costs the full penalty.
e = run(p, 40, hourly_manip=True)
assert (e["result"], e["score"]) == ("MANIP", h.PENALTY_MANIP), e

# --------------------------------------------------------------- derived streaks
hist = [{"result": r} for r in ("MISS", "MISS", "HIT")]
assert h.streak_from(hist) == 1
assert h.best_streak_from(hist) == 1
# Vacation days are transparent: they neither extend nor break a streak.
assert h.streak_from(hist + [{"result": "SKIP"}, {"result": "HIT"}]) == 2, h.streak_from(hist + [{"result": "SKIP"}])
assert h.streak_from([{"result": "SKIP"}]) == 0
# Transparent: the run spans the vacation instead of restarting after it.
assert h.best_streak_from([{"result": "HIT"}] * 3 + [{"result": "SKIP"}] + [{"result": "HIT"}] * 2) == 5
assert h.streak_from([]) == 0 and h.best_streak_from([]) == 0

# Bonuses still escalate, and only for good sessions.
st = {"probability": 50.0, "history": []}
for i in range(2):
    h.settle(st, {"for_date": f"2026-10-0{i+1}", "lo": 10, "hi": 30}, 30)
scored = [e["score"] for e in st["history"]]
assert scored[1] > scored[0], "a streak must be worth more"
assert scored[0] == h.REWARD_CEIL + 0.0, scored

# ------------------------------------------------------- one rule, all consumers
for r in ("HIT", "NEAR", "BEAT"):
    assert r in h.GOOD_RESULTS and h.stats([{"result": r}], 0)["hit_rate"] == 1.0
for r in ("MISS", "CRASH", "MANIP"):
    assert r not in h.GOOD_RESULTS and h.stats([{"result": r}], 0)["hit_rate"] == 0.0
# SKIP is not a session at all: excluded from both the rate and the denominator.
assert h.stats([{"result": "HIT"}, {"result": "SKIP"}], 0) == {
    "n": 1, "hit_rate": 1.0, "exact": 1, "near": 0, "beat": 0, "miss": 0, "best_streak": 0}

# The headline answers "how much shipped", not "how good is the predictor".
assert h.volume_line([]).startswith("No sessions")
v = h.volume_line([{"actual": a, "result": "HIT"} for a in (40, 9, 12)])
assert v == "61 commits in 3 sessions · 20/day · never missed a day", v
# ...and a vacation day must not count as a day with zero commits.
assert "never missed a day" in h.volume_line(
    [{"actual": a, "result": "HIT"} for a in (40, 9)] + [{"actual": 0, "result": "SKIP"}])
assert "1 day at zero" in h.volume_line([{"actual": 0, "result": "CRASH"}])
assert "1 session ·" in h.stats_line([{"result": "HIT"}], 0), "singular, not '1 sessions'"

# ----------------------------------------------------------------- the burst rule
base = datetime(2026, 10, 2, tzinfo=timezone.utc)
assert h.is_hourly_manipulation([base + timedelta(minutes=i) for i in range(10)])
assert not h.is_hourly_manipulation([base + timedelta(hours=i) for i in range(10)])

# ------------------------------------------------- the controls issue is a switch
V = h.VACATION_LABEL
assert re.search(rf"^-\s*\[ \]\s*{re.escape(V)}", h.CONTROLS_BODY, re.M), "must ship unticked"
assert h.vacation_ticked(h.CONTROLS_BODY) is False, "a fresh controls issue is off"
assert h.vacation_ticked(h.CONTROLS_BODY.replace("- [ ] " + V, "- [x] " + V)) is True
assert h.vacation_ticked(h.CONTROLS_BODY.replace("- [ ] " + V, "- [X] " + V)) is True
# Untick and it goes back off - that is the whole switch.
assert h.vacation_ticked(h.CONTROLS_BODY.replace("- [x] " + V, "- [ ] " + V)) is False
# Fail safe: a missing, empty or mangled box is never "on".
for bad in ("", None, "no checkbox here", f"-[ ] {V}", f"- [y] {V}", f"* [x] {V}"):
    assert h.vacation_ticked(bad) is False, bad

# ---------------------------------------------- forecast issues are found by title
NEW = "\U0001f680 $HIRED 2026-10-03 \u2014 9\u201340 commits?"
OLD = "$HIRED Daily Forecast \u2014 Vote: will the bot hit today's number?"
CTRL = "\u2699\ufe0f Exchange controls"
assert h._is_vote_issue(NEW) and h._is_vote_issue(OLD)
assert not h._is_vote_issue(CTRL), "the controls issue is not a forecast issue"
assert not h._is_vote_issue("Bug: ticker shows the wrong delta")
assert not h._is_vote_issue("")
assert h._vote_date(NEW) == "2026-10-03"
assert h._vote_date(OLD) is None, "legacy titles carry no date and must never be adopted as today's"

# list_vote_issues must page, must filter, and must survive a dead API.
def api_with(pages):
    def f(method, path, token, body=None):
        n = int(re.search(r"[?&]page=(\d+)", path).group(1)) if "page=" in path else 1
        return pages.get(n, [])
    return f
h._gh_api = api_with({1: [{"number": 1, "title": OLD}, {"number": 5, "title": CTRL},
                          {"number": 9, "title": NEW}, {"number": 7, "title": "chore: bump"}]})
assert [i["number"] for i in h.list_vote_issues("o/o", "t")] == [1, 9]
h._gh_api = api_with({})
assert h.list_vote_issues("o/o", "t") == [], "a failed lookup must not raise"

# A retry adopts today's issue instead of opening a second one.
posted = []
def api_adopt(method, path, token, body=None):
    if method == "POST":
        posted.append(body); return {"number": 42}
    return [{"number": 9, "title": NEW}]
h._gh_api = api_adopt
st = {"pending": {"for_date": "2026-10-03", "lo": 9, "hi": 40, "avg7": 19.86}, "vote_issue": None}
h.create_vote_issue(st, "t", "o")
assert st["vote_issue"] == 9 and not posted, (st["vote_issue"], posted)
# ...and only creates one when there is genuinely nothing for today.
def api_create(method, path, token, body=None):
    if method == "POST":
        posted.append(body); return {"number": 42}
    return []
h._gh_api = api_create
h.create_vote_issue(st, "t", "o")
assert st["vote_issue"] == 42 and len(posted) == 1 and posted[0]["title"] == NEW

# The SVG must stay parseable XML, fit its canvas, and never overlap itself.
# Two hardcoded offsets did exactly that once: LIVE over the date, and the
# legend swatches over "LAST 7".
def _runs(svg):
    """(x0, x1, y_top, y_bottom, text) for every rendered string.

    Reads the whole open tag, not just the attributes before font-size -
    text-anchor="end" comes last, and missing it silently measures every
    right-aligned label as if it were left-aligned.
    """
    out = []
    for mm in re.finditer(r"<(text|tspan)\b([^>]*)>([^<]*)", svg):
        attrs, txt = mm[2], mm[3]
        if not txt.strip():
            continue
        gx, gy = re.search(r'\bx="([\d.]+)"', attrs), re.search(r'\by="([\d.]+)"', attrs)
        fs = re.search(r'font-size="(\d+)"', attrs)
        if not (gx and gy and fs):
            continue
        x, y, size = float(gx[1]), float(gy[1]), int(fs[1])
        w = len(txt) * size * 0.62
        if 'text-anchor="middle"' in attrs:
            x0 = x - w / 2
        elif 'text-anchor="end"' in attrs:
            x0 = x - w
        else:
            x0 = x
        out.append((x0, x0 + w, y - size * 0.75, y + size * 0.25, txt))
    return out


def svg_ok(state):
    svg = h.render_svg(state)
    ET.fromstring(svg)
    W, H = map(float, re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
    runs = _runs(svg)
    assert runs, "no text rendered at all"
    for x0, x1, top, bot, txt in runs:
        assert 4 <= x0 and x1 <= W - 4, f"outside canvas: {txt!r} {x0:.0f}..{x1:.0f} of {W}"
        assert 8 <= top and bot <= H - 2, f"outside canvas: {txt!r} {top:.0f}..{bot:.0f} of {H}"
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            a, b = runs[i], runs[j]
            assert not (a[2] < b[3] and b[2] < a[3] and a[0] < b[1] and b[0] < a[1]), \
                f"overlap: {a[4]!r} x {b[4]!r}"
    # ...and so must small rects (the legend swatches) - the second collision was
    # a chip sitting on top of the chart title, which text-vs-text cannot see.
    chips = []
    for mm in re.finditer(r'<rect x="([\d.]+)" y="([\d.]+)" width="(\d+)" height="(\d+)"', svg):
        x, y, w, ht = (float(mm[i]) for i in range(1, 5))
        if w <= 14 and ht <= 14:
            chips.append((x, x + w, y, y + ht))
    for cx0, cx1, cy0, cy1 in chips:
        for x0, x1, top, bot, txt in runs:
            assert not (cx0 < x1 and x0 < cx1 and cy0 < bot and top < cy1), \
                f"swatch {cx0:.0f},{cy0:.0f} sits on {txt!r}"
    assert min(int(f) for f in re.findall(r'font-size=.(\d+)', svg)) >= 10


svg_ok({"probability": 50.0, "streak": 0, "best_streak": 0, "history": [], "pending": None})
for res in ("HIT", "BEAT", "MISS", "CRASH", "MANIP", "SKIP"):
    svg_ok({"probability": h.PROB_MIN, "streak": 1, "best_streak": 2, "updated": "2026-10-03",
            "last_result": res, "last_delta": -0.25, "last_clamped": "floor",
            "last_note": "note",
            "pending": {"for_date": "2026-10-03", "lo": 1, "hi": 999, "avg7": 12.5},
            "history": [{"date": f"2026-10-0{i}", "lo": 1, "hi": 999, "actual": i * 7,
                         "result": res, "prob_before": 1.0, "probability": 1.0 + i}
                        for i in range(1, 8)]})
svg_ok({"probability": 99.89, "streak": 9, "best_streak": 9, "updated": "2026-10-03",
        "last_result": "HIT", "last_delta": 1.0, "last_clamped": "ceiling", "last_note": "x",
        "pending": None, "history": []})
# The longest date the ticker will ever print, and the widest headline.
svg_ok({"probability": 99.89, "streak": 99, "best_streak": 99, "updated": "2026-12-31",
        "last_result": "BEAT", "last_delta": 1.5, "last_clamped": None,
        "last_note": "Beat the range by a mile. The model is now upgrading its assumptions.",
        "pending": {"for_date": "2026-12-31", "lo": 136, "hi": 136, "avg7": 136.0},
        "visitors": {"hit": 9999, "miss": 9999},
        "history": [{"date": f"2026-10-{i:02d}", "lo": 136, "hi": 136, "actual": 136,
                     "result": "BEAT", "prob_before": 1.0, "probability": 1.0}
                    for i in range(1, 8)]})

print("ok")