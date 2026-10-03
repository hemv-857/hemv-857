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

print("ok")
