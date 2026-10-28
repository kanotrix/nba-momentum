"""Daily NBA update from ESPN's public feed (works from GitHub's servers).
Adds finished regular-season games (points + shooting) to data/games_<season>.csv.
Usage: python fetch_espn.py                      (updates 2026-27)
       python fetch_espn.py 2026-27 2026-10-20   (season, first date to scan)
"""
import os, sys, time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import requests

SEASON = sys.argv[1] if len(sys.argv) > 1 else "2026-27"
START = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 10, 20)
BOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
SUMMARY = "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
ET, IST = ZoneInfo("America/New_York"), timezone(timedelta(hours=5, minutes=30))
FIX = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}
SHOOT = ["FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA"]

os.makedirs("data", exist_ok=True)
path = f"data/games_{SEASON}.csv"
old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()

# Where to start scanning: last 3 days, or the first row missing shooting data
start = START
if not old.empty:
    last = pd.to_datetime(old["GAME_DATE"]).max().date()
    start = max(START, last - timedelta(days=3))
    if "FGA" in old.columns:
        missing = old[old["FGA"].isna()]
        if not missing.empty:
            start = min(start, pd.to_datetime(missing["GAME_DATE"]).min().date())
    else:
        start = START
end = datetime.now(ET).date()


def get(url, params):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"{params} attempt {attempt+1} failed: {e}")
            time.sleep(5)
    return None


def split(v):
    """'41-88' -> (41, 88)"""
    try:
        a, b = str(v).split("-")
        return float(a), float(b)
    except Exception:
        return None, None


def boxscore(event_id):
    """Return {ESPN abbreviation: {FGM, FGA, FG3M, FG3A, FTM, FTA}} for one game."""
    data = get(SUMMARY, {"event": event_id})
    out = {}
    for t in ((data or {}).get("boxscore") or {}).get("teams", []):
        vals = {}
        for s in t.get("statistics", []):
            name, label = str(s.get("name", "")), str(s.get("label", "")).upper()
            if name.startswith("fieldGoalsMade") or label == "FG":
                vals["FGM"], vals["FGA"] = split(s.get("displayValue"))
            elif name.startswith("threePointFieldGoalsMade") or label in ("3PT", "3P"):
                vals["FG3M"], vals["FG3A"] = split(s.get("displayValue"))
            elif name.startswith("freeThrowsMade") or label == "FT":
                vals["FTM"], vals["FTA"] = split(s.get("displayValue"))
        out[t["team"]["abbreviation"]] = vals
    return out


def parse(data):
    rows = []
    for ev in (data or {}).get("events", []):
        if ev.get("season", {}).get("type") != 2:   # regular season only
            continue
        comp = ev["competitions"][0]
        if not comp.get("status", {}).get("type", {}).get("completed"):
            continue
        gdate = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET).date()
        teams = comp["competitors"]
        scores = {t["team"]["abbreviation"]: float(t["score"]) for t in teams}
        box = boxscore(ev["id"])
        for t in teams:
            ab = t["team"]["abbreviation"]
            opp = [k for k in scores if k != ab][0]
            margin = scores[ab] - scores[opp]
            row = {"TEAM_ABBREVIATION": FIX.get(ab, ab), "GAME_DATE": gdate.isoformat(),
                   "PLUS_MINUS": margin, "WL": "W" if margin > 0 else "L",
                   "PTS": scores[ab], "OPP_PTS": scores[opp], "GAME_ID": ev["id"]}
            row.update({k: box.get(ab, {}).get(k) for k in SHOOT})
            rows.append(row)
    return rows


new, failed = [], 0
day = start
while day <= end:
    data = get(BOARD, {"dates": day.strftime("%Y%m%d"), "limit": 100})
    if data is None:
        failed += 1
    else:
        new += parse(data)
    day += timedelta(days=1)
print(f"Scanned {start} to {end}: {len(new)} team-games found, {failed} days failed")

if new:
    fresh = pd.DataFrame(new)
    got = fresh["FGA"].notna().sum()
    print(f"Shooting stats found for {got} of {len(fresh)} team-games")
    df = pd.concat([old, fresh], ignore_index=True)
    df = df.drop_duplicates(subset=["TEAM_ABBREVIATION", "GAME_DATE"], keep="last")
    df = df.sort_values(["TEAM_ABBREVIATION", "GAME_DATE"])
    df.to_csv(path, index=False)
    print(f"{SEASON}: {len(df)} rows saved")
else:
    print("Nothing new to save")

with open("data/last_updated.txt", "w") as f:
    f.write(datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"))
if failed and not new:
    sys.exit(1)
