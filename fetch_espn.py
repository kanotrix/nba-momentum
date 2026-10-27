"""Daily NBA update from ESPN's public scoreboard (works from GitHub's servers).
Adds new completed regular-season games to data/games_<season>.csv.
Usage: python fetch_espn.py            (updates 2026-27)
       python fetch_espn.py 2026-27 2026-10-20   (season, first date to scan)
"""
import os, sys, time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import requests

SEASON = sys.argv[1] if len(sys.argv) > 1 else "2026-27"
START = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 10, 20)
URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ET, IST = ZoneInfo("America/New_York"), timezone(timedelta(hours=5, minutes=30))
# ESPN abbreviations -> NBA.com abbreviations (keeps teams consistent with old data)
FIX = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}

os.makedirs("data", exist_ok=True)
path = f"data/games_{SEASON}.csv"
old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()

# Re-scan the last 3 days of existing data (catches late score fixes)
start = START
if not old.empty:
    last = pd.to_datetime(old["GAME_DATE"]).max().date()
    start = max(START, last - timedelta(days=3))
end = datetime.now(ET).date()


def get(day):
    for attempt in range(3):
        try:
            r = requests.get(URL, params={"dates": day.strftime("%Y%m%d"), "limit": 100}, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"{day} attempt {attempt+1} failed: {e}")
            time.sleep(5)
    return None


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
        for t in teams:
            ab = t["team"]["abbreviation"]
            opp = [k for k in scores if k != ab][0]
            margin = scores[ab] - scores[opp]
            rows.append({"TEAM_ABBREVIATION": FIX.get(ab, ab), "GAME_DATE": gdate.isoformat(),
                         "PLUS_MINUS": margin, "WL": "W" if margin > 0 else "L",
                         "PTS": scores[ab], "OPP_PTS": scores[opp], "GAME_ID": ev["id"]})
    return rows


new, failed = [], 0
day = start
while day <= end:
    data = get(day)
    if data is None:
        failed += 1
    else:
        new += parse(data)
    day += timedelta(days=1)
print(f"Scanned {start} to {end}: {len(new)} team-games found, {failed} days failed")

if new:
    df = pd.concat([old, pd.DataFrame(new)], ignore_index=True)
    df = df.drop_duplicates(subset=["TEAM_ABBREVIATION", "GAME_DATE"], keep="last")
    df = df.sort_values(["TEAM_ABBREVIATION", "GAME_DATE"])
    df.to_csv(path, index=False)
    print(f"{SEASON}: {len(df)} rows saved")
else:
    print("Nothing new to save")

with open("data/last_updated.txt", "w") as f:
    f.write(datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"))
if failed and not new:
    sys.exit(1)   # make the workflow show a red cross if ESPN was unreachable
