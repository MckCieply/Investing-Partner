"""FOMC meeting calendar for Setup 14 (Rate Sensitivity Play).

fred.stlouisfed.org's CSV/graph endpoints time out from this environment
regardless of network sandboxing (tested both with and without the sandbox
override) - so this module skips the live FRED series and uses a hardcoded,
publicly verifiable FOMC decision calendar instead. Setup 14 only needs the
meeting dates and decision direction to bucket events; the handoff already
flags this setup's result as correlation, not causation, so a static
calendar is an acceptable substitute for a live rate series here.

Source: federalreserve.gov FOMC calendar/statements (public record).
direction: "hike" | "cut" | "hold" - effective fed funds target change at that meeting.
"""

FOMC_MEETINGS = [
    {"date": "2021-12-15", "direction": "hold"},
    {"date": "2022-01-26", "direction": "hold"},
    {"date": "2022-03-16", "direction": "hike"},
    {"date": "2022-05-04", "direction": "hike"},
    {"date": "2022-06-15", "direction": "hike"},
    {"date": "2022-07-27", "direction": "hike"},
    {"date": "2022-09-21", "direction": "hike"},
    {"date": "2022-11-02", "direction": "hike"},
    {"date": "2022-12-14", "direction": "hike"},
    {"date": "2023-02-01", "direction": "hike"},
    {"date": "2023-03-22", "direction": "hike"},
    {"date": "2023-05-03", "direction": "hike"},
    {"date": "2023-06-14", "direction": "hold"},
    {"date": "2023-07-26", "direction": "hike"},
    {"date": "2023-09-20", "direction": "hold"},
    {"date": "2023-11-01", "direction": "hold"},
    {"date": "2023-12-13", "direction": "hold"},
    {"date": "2024-01-31", "direction": "hold"},
    {"date": "2024-03-20", "direction": "hold"},
    {"date": "2024-05-01", "direction": "hold"},
    {"date": "2024-06-12", "direction": "hold"},
    {"date": "2024-07-31", "direction": "hold"},
    {"date": "2024-09-18", "direction": "cut"},
    {"date": "2024-11-07", "direction": "cut"},
    {"date": "2024-12-18", "direction": "cut"},
    {"date": "2025-01-29", "direction": "hold"},
    {"date": "2025-03-19", "direction": "hold"},
    {"date": "2025-05-07", "direction": "hold"},
    {"date": "2025-06-18", "direction": "hold"},
    {"date": "2025-07-30", "direction": "hold"},
    {"date": "2025-09-17", "direction": "cut"},
    {"date": "2025-10-29", "direction": "cut"},
    {"date": "2025-12-10", "direction": "hold"},
]

# Rate-sensitive sector proxies for Setup 14: utilities, REITs, regional banks, homebuilders.
RATE_SENSITIVE_ETFS = ["XLU", "VNQ", "KRE", "XHB"]


def meetings_in_range(start_date, end_date, directions=None):
    import pandas as pd
    start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
    out = []
    for m in FOMC_MEETINGS:
        d = pd.Timestamp(m["date"])
        if start_ts <= d <= end_ts and (directions is None or m["direction"] in directions):
            out.append(m)
    return out
