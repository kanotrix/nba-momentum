
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="NBA Offensive Stats", layout="wide")
st.title("🏀 NBA Offensive Stats")
st.caption("Cumulative scoring and shooting totals for every team.")

EAST = {"ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND", "MIA", "MIL", "NYK", "ORL", "PHI", "TOR", "WAS"}
WEST = {"DAL", "DEN", "GSW", "HOU", "LAC", "LAL", "MEM", "MIN", "NOP", "OKC", "PHX", "POR", "SAC", "SAS", "UTA"}

# ---------- Sidebar ----------
season = st.sidebar.selectbox("Season", ["2026-27", "2025-26", "2024-25", "2023-24"], index=1)


@st.cache_data(ttl=600)
def load(season):
    path = Path(f"data/games_{season}.csv")
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
    return df.sort_values(["TEAM_ABBREVIATION", "GAME_DATE"])


raw = load(season)
if raw.empty:
    st.warning(f"No data file found for {season}. Try another season.")
    st.stop()

STATS = ["PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA"]
for c in STATS:
    if c not in raw.columns:
        raw[c] = pd.NA
    raw[c] = pd.to_numeric(raw[c], errors="coerce")

dmin, dmax = raw["GAME_DATE"].min().date(), raw["GAME_DATE"].max().date()
span = st.sidebar.date_input("Games between", (dmin, dmax), min_value=dmin, max_value=dmax)
last_n = st.sidebar.selectbox("Games per team", ["All", "Last 5", "Last 10", "Last 20"])
conf = st.sidebar.radio("Conference", ["All teams", "Eastern", "Western"])

# Current NBA rank: win % across the whole season, ties broken by point differential
if "PLUS_MINUS" not in raw.columns:
    raw["PLUS_MINUS"] = 0
raw["PLUS_MINUS"] = pd.to_numeric(raw["PLUS_MINUS"], errors="coerce").fillna(0)
stand = raw.groupby("TEAM_ABBREVIATION").agg(
    W=("WL", lambda x: (x == "W").sum()), G=("WL", "size"), Diff=("PLUS_MINUS", "sum")).reset_index()
stand["L"] = stand["G"] - stand["W"]
stand["WinPct"] = stand["W"] / stand["G"]
stand = stand.sort_values(["WinPct", "Diff"], ascending=False).reset_index(drop=True)
stand["NBA Rank"] = stand.index + 1
stand["W-L"] = stand["W"].astype(str) + "-" + stand["L"].astype(str)
stand = stand.rename(columns={"TEAM_ABBREVIATION": "Team"})[["Team", "NBA Rank", "W-L"]]

df = raw.copy()
if conf == "Eastern":
    df = df[df["TEAM_ABBREVIATION"].isin(EAST)]
elif conf == "Western":
    df = df[df["TEAM_ABBREVIATION"].isin(WEST)]
if isinstance(span, tuple) and len(span) == 2:
    df = df[(df["GAME_DATE"].dt.date >= span[0]) & (df["GAME_DATE"].dt.date <= span[1])]
if last_n != "All":
    n = int(last_n.split()[1])
    df = df.groupby("TEAM_ABBREVIATION", group_keys=False).tail(n)

if df.empty:
    st.warning("No games in that range.")
    st.stop()


def pct(a, b):
    return (a / b * 100).where(b > 0)


tot = df.groupby("TEAM_ABBREVIATION").agg(
    GP=("PTS", "size"), PTS=("PTS", "sum"),
    FGM=("FGM", "sum"), FGA=("FGA", "sum"),
    FG3M=("FG3M", "sum"), FG3A=("FG3A", "sum"),
    FTM=("FTM", "sum"), FTA=("FTA", "sum"),
).reset_index()
tot["PPG"] = tot["PTS"] / tot["GP"]
tot["FG%"] = pct(tot["FGM"], tot["FGA"])
tot["3P%"] = pct(tot["FG3M"], tot["FG3A"])
tot["FT%"] = pct(tot["FTM"], tot["FTA"])
tot = tot.rename(columns={"TEAM_ABBREVIATION": "Team", "FG3M": "3PM", "FG3A": "3PA"})
tot = tot.merge(stand, on="Team", how="left")

has_shooting = df["FGA"].notna().any()
if not has_shooting:
    st.info("Shooting numbers aren't available for this season yet, so only scoring is shown.")

tab1, tab2, tab3 = st.tabs(["Team table", "Leaders", "Cumulative trend"])

with tab1:
    cols = ["NBA Rank", "Team", "W-L", "GP", "PTS", "PPG"]
    if has_shooting:
        cols += ["FGM", "FGA", "FG%", "3PM", "3PA", "3P%", "FTM", "FTA", "FT%"]
    show = tot[cols].sort_values("PTS", ascending=False).reset_index(drop=True)
    show.insert(0, "Sr. no.", show.index + 1)
    st.dataframe(show.round(1), hide_index=True, width="stretch")

with tab2:
    options = ["PTS", "PPG"] + (["FG%", "3P%", "FT%", "3PM", "FTM"] if has_shooting else [])
    metric = st.selectbox("Stat", options)
    d = tot.sort_values(metric, ascending=False)
    fig = px.bar(d, x="Team", y=metric, hover_data=["GP"])
    fig.update_layout(xaxis_title=None)
    st.plotly_chart(fig, width="stretch")
    c1, c2 = st.columns(2)
    c1.metric(f"Highest {metric}", d.iloc[0]["Team"], f"{d.iloc[0][metric]:,.1f}")
    c2.metric(f"Lowest {metric}", d.iloc[-1]["Team"], f"{d.iloc[-1][metric]:,.1f}")

with tab3:
    teams = sorted(df["TEAM_ABBREVIATION"].unique())
    pick = st.multiselect("Teams", teams, default=teams[:3])
    stat = st.selectbox("Running total of", ["PTS"] + (["FGM", "FG3M", "FTM"] if has_shooting else []))
    if pick:
        t = df[df["TEAM_ABBREVIATION"].isin(pick)].copy()
        t["Game #"] = t.groupby("TEAM_ABBREVIATION").cumcount() + 1
        t["Running total"] = t.groupby("TEAM_ABBREVIATION")[stat].cumsum()
        fig = px.line(t, x="Game #", y="Running total", color="TEAM_ABBREVIATION",
                      markers=True, hover_data=["GAME_DATE"])
        st.plotly_chart(fig, width="stretch")
