"""Download game logs and save to data/. Run daily by GitHub Actions."""
import sys, time
from datetime import datetime, timedelta, timezone
import pandas as pd
from nba_api.stats.endpoints import leaguegamelog

SEASONS = sys.argv[1:] or ["2026-27", "2025-26"]
IST = timezone(timedelta(hours=5, minutes=30))

for season in SEASONS:
    for attempt in range(3):
        try:
            df = leaguegamelog.LeagueGameLog(
                season=season, player_or_team_abbreviation="T", timeout=60
            ).get_data_frames()[0]
            break
        except Exception as e:
            print(f"{season} attempt {attempt+1} failed: {e}")
            time.sleep(10)
    else:
        print(f"Skipping {season}")
        continue
    if df.empty:
        print(f"{season}: no games yet")
        continue
    df.to_csv(f"data/games_{season}.csv", index=False)
    print(f"{season}: saved {len(df)} rows")

with open("data/last_updated.txt", "w") as f:
    f.write(datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"))
