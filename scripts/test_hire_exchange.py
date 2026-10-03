import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import hire_exchange as h

# 2026-10-02 regression: predicted 11, actual 40 across 7 real repos scored
# "manipulation". Beating a low forecast is the good outcome, not fraud.
assert h.classify(11, 40) == "BEAT"
assert h.classify(0, 40) == "BEAT"
assert h.classify(39, 12) == "MISS"
assert h.classify(22, 9) == "MISS"
assert h.classify(22, 0) == "CRASH"
assert h.classify(20, 20) == "HIT"
assert h.classify(20, 21) == "NEAR"

# Streaks are derived from history, so a re-settled entry cannot leave the
# stored counters lying about the record.
hist = [{"result": r} for r in ("MISS", "MISS", "BEAT")]
assert h.streak_from(hist) == 1, h.streak_from(hist)
assert h.best_streak_from(hist) == 1
assert h.streak_from([{"result": "BEAT"}] * 7) == 7
assert h.best_streak_from([{"result": "BEAT"}] * 3 + [{"result": "MISS"}] + [{"result": "NEAR"}] * 2) == 3
assert h.streak_from([]) == 0 and h.best_streak_from([]) == 0

# The bonus still escalates with the streak, and only for good sessions.
def score(results, pred, actual):
    st = {"probability": 50.0, "history": []}
    for i, r in enumerate(results):
        h.settle(st, {"for_date": f"2026-10-{i + 1:02d}", "predicted": pred}, actual,
                 hourly_manip=(r == "MANIP"))
    return st["history"]

assert [e["score"] for e in score(["HIT", "HIT"], 20, 20)] == [1.0, 1.1]
assert score(["BEAT"], 11, 40)[0]["score"] == 0.5

# The probability floor must not swallow the score shown in the table.
st = {"probability": h.PROB_MIN, "history": []}
h.settle(st, {"for_date": "2026-10-02", "predicted": 11}, 40)
e = st["history"][-1]
assert (e["result"], e["score"], e["delta"]) == ("BEAT", h.REWARD_NEAR, h.REWARD_NEAR), e

# Only a profile-repo burst is manipulation, and it costs the full penalty.
st = {"probability": 50.0, "history": []}
h.settle(st, {"for_date": "2026-10-02", "predicted": 11}, 40, hourly_manip=True)
e = st["history"][-1]
assert (e["result"], e["score"]) == ("MANIP", h.PENALTY_MANIP), e
assert h.streak_from(st["history"]) == 0, "a burst must not extend the streak"

# 10 commits inside a 60-minute window is a burst; spread over a day it is not.
base = datetime(2026, 10, 2, tzinfo=timezone.utc)
assert h.is_hourly_manipulation([base + timedelta(minutes=i) for i in range(10)])
assert not h.is_hourly_manipulation([base + timedelta(hours=i) for i in range(10)])

# Every consumer must agree on what a good session is.
for r in ("HIT", "NEAR", "BEAT"):
    assert r in h.GOOD_RESULTS
    assert h.stats([{"result": r}], 0)["hit_rate"] == 1.0
for r in ("MISS", "CRASH", "MANIP"):
    assert r not in h.GOOD_RESULTS
    assert h.stats([{"result": r}], 0)["hit_rate"] == 0.0
assert h.stats([{"result": "BEAT"}, {"result": "MISS"}], 1)["beat"] == 1
assert "beat" in h.stats_line([{"result": "BEAT"}], 0)

# A clamped score must say so, otherwise the pts column looks like a lie.
st = {"probability": 0.06, "history": []}
h.settle(st, {"for_date": "2026-10-04", "predicted": 22}, 9)
e = st["history"][-1]
assert (e["score"], e["delta"], e["clamped"]) == (h.PENALTY_MISS, -0.01, "floor"), e
st = {"probability": 99.5, "history": []}
h.settle(st, {"for_date": "2026-10-05", "predicted": 20}, 20)
assert st["history"][-1]["clamped"] == "ceiling", "a gain past PROB_MAX must flag the ceiling"
st = {"probability": 50.0, "history": []}
h.settle(st, {"for_date": "2026-10-06", "predicted": 20}, 20)
assert st["history"][-1]["clamped"] is None, "an unclamped score must not claim a clamp"

# The headline answers "how much shipped", not "how good is the predictor".
assert h.volume_line([]).startswith("No sessions")
v = h.volume_line([{"actual": 40, "predicted": 11}, {"actual": 9, "predicted": 22},
                   {"actual": 12, "predicted": 39}])
assert v == "61 commits in 3 sessions \u00b7 20/day \u00b7 never missed a day", v
z = h.volume_line([{"actual": 0, "predicted": 5}])
assert "1 day at zero" in z, z

# The SVG must stay parseable XML and fit its canvas.
import re, xml.etree.ElementTree as ET
for st in ({"probability": 50.0, "streak": 0, "best_streak": 0, "history": [], "pending": None},
           {"probability": h.PROB_MIN, "streak": 2, "best_streak": 5,
            "history": [{"date": "2026-10-0%d" % i, "predicted": 10 * i, "actual": i,
                         "result": "BEAT", "prob_before": 1.0, "probability": 1.0 + i}
                        for i in range(1, 8)],
            "pending": {"for_date": "2026-10-08", "predicted": 3, "avg7": 2.5},
            "last_result": "BEAT", "last_delta": 0.5, "last_note": "note",
            "last_clamped": "floor", "updated": "2026-10-08"}):
    svg = h.render_svg(st)
    ET.fromstring(svg)
    W, H = map(float, re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
    for m in re.finditer(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*font-size="(\d+)"[^>]*>([^<]*)', svg):
        x, y, size, txt = float(m[1]), float(m[2]), int(m[3]), m[4]
        w = len(txt) * size * 0.62
        a = "end" if 'text-anchor="end"' in m[0] else ("middle" if 'text-anchor="middle"' in m[0] else "start")
        x0 = x if a == "start" else (x - w / 2 if a == "middle" else x - w)
        assert 8 <= x0 and x0 + w <= W - 8 and 10 <= y <= H - 4, (txt[:40], x0, x0 + w, y, W, H)
    assert min(int(f) for f in re.findall(r'font-size=.(\d+)', svg)) >= 11

print("ok")
