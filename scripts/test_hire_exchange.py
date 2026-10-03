import hire_exchange as h

# 2026-10-02 regression: predicted 11, actual 40 across 7 real repos was scored
# "🚨 Manipulation" by a since-deleted 3x-the-forecast rule. Beating a low
# forecast is a MISS, not fraud.
assert h.classify(11, 40) == "MISS"
assert h.classify(0, 40) == "MISS"
assert h.classify(22, 9) == "MISS"
assert h.classify(22, 0) == "CRASH"
assert h.classify(20, 20) == "HIT"
assert h.classify(20, 21) == "NEAR"

# Only a profile-repo burst is manipulation, and it costs the full penalty.
state = {"probability": 50.0, "streak": 0, "best_streak": 0, "history": []}
h.settle(state, {"for_date": "2026-10-02", "predicted": 11}, 40, hourly_manip=True)
e = state["history"][-1]
assert e["result"] == "MANIP", e["result"]
assert e["score"] == h.PENALTY_MANIP, e["score"]
assert e["probability"] == 50.0 - 1.5

# The probability floor must not swallow the score shown in the table.
state["probability"] = h.PROB_MIN
h.settle(state, {"for_date": "2026-10-02", "predicted": 11}, 40)
e = state["history"][-1]
assert (e["result"], e["score"], e["delta"]) == ("MISS", h.PENALTY_MISS, 0.0), e

# 10 commits inside a 60-minute window is a burst; spread over a day it is not.
from datetime import datetime, timedelta, timezone
base = datetime(2026, 10, 2, tzinfo=timezone.utc)
assert h.is_hourly_manipulation([base + timedelta(minutes=i) for i in range(10)])
assert not h.is_hourly_manipulation([base + timedelta(hours=i) for i in range(10)])

print("ok")