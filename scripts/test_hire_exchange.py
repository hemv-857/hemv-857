import hire_exchange as h

# 2026-10-02 regression: predicted 11, actual 40 -> manipulation, and the
# penalty must survive the PROB_MIN floor instead of rendering as +0.00.
assert h.classify(11, 40) == "MANIP"
assert h.classify(0, 40) == "MANIP"      # predicting 0 is not an immunity
assert h.classify(22, 9) == "MISS"
assert h.classify(22, 0) == "CRASH"

state = {"probability": h.PROB_MIN, "streak": 0, "best_streak": 0, "history": []}
h.settle(state, {"for_date": "2026-10-02", "predicted": 11}, 40)
e = state["history"][-1]
assert e["score"] == h.PENALTY_MANIP, e["score"]
assert e["delta"] == 0.0, e["delta"]      # floored, as designed
assert e["probability"] == h.PROB_MIN

print("ok")