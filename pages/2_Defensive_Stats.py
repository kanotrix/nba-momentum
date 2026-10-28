from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="NBA Defensive Stats", layout="wide")
st.title("🛡️ NBA Defensive Stats")
st.caption("Cumulative defensive totals for every team. For points allowed and opponent shooting, lower is better.")

EAST = {"ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND", "MIA", "MIL", "NYK", "ORL", "PHI", "TOR", "WAS"}
WEST = {"DAL", "DEN", "GSW", "HOU", "LAC", "LAL", "MEM", "MIN", "NOP", "OKC", "PHX", "POR", "SAC", "SAS", "UTA"}

# ---------- Sidebar ----------
season = st.sidebar.selectbox("Season", ["2026-27", "2025-26", "2024-25", "2023-24"], index=1)


@st.cache_data(ttl=600)
def load(season):
    path = Path(f"data/games_{season}.csv")
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"GAME_ID": str})
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
    return df.sort_values(["TEAM_ABBREVIATION", "GAME_DATE"]).reset_index(drop=True)


raw = load(season)
if raw.empty:
    st.warning(f"No data file found for {season}. Try another season.")
    st.stop()

NUM = ["PTS", "PLUS_MINUS", "OPP_PTS", "FGM", "FGA", "FG3M", "FG3A", "STL", "BLK", "DREB", "TOV"]
for c in NUM:
    if c not in raw.columns:
        raw[c] = pd.NA
    raw[c] = pd.to_numeric(raw[c], errors="coerce")

# Points allowed = opponent's points
raw["OPP_PTS"] = raw["OPP_PTS"].fillna(raw["PTS"] - raw["PLUS_MINUS"])

# Opponent's numbers in the same game = (both teams' total) - (this team)
if "GAME_ID" in raw.columns and raw["GAME_ID"].notna().any():
    for c, o in [("FGM", "OPP_FGM"), ("FGA", "OPP_FGA"), ("FG3M", "OPP_FG3M"),
                 ("FG3A", "OPP_FG3A"), ("TOV", "OPP_TOV")]:
        g = raw.groupby("GAME_ID")[c]
        raw[o] = (g.transform("sum") - raw[c]).where(g.transform("count") == 2)
else:
    for o in ["OPP_FGM", "OPP_FGA", "OPP_FG3M", "OPP_FG3A", "OPP_TOV"]:
        raw[o] = pd.NA
for o in ["OPP_FGM", "OPP_FGA", "OPP_FG3M", "OPP_FG3A", "OPP_TOV"]:
    raw[o] = pd.to_numeric(raw[o], errors="coerce")

dmin, dmax = raw["GAME_DATE"].min().date(), raw["GAME_DATE"].max().date()
span = st.sidebar.date_input("Games between", (dmin, dmax), min_value=dmin, max_value=dmax)
last_n = st.sidebar.selectbox("Games per team", ["All", "Last 5", "Last 10", "Last 20"])
conf = st.sidebar.radio("Conference", ["All teams", "Eastern", "Western"])

# Current NBA rank: win % across the whole season, ties broken by point differential
raw["PLUS_MINUS"] = raw["PLUS_MINUS"].fillna(0)
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
    GP=("OPP_PTS", "size"), OPP_PTS=("OPP_PTS", "sum"),
    OFGM=("OPP_FGM", "sum"), OFGA=("OPP_FGA", "sum"),
    O3M=("OPP_FG3M", "sum"), O3A=("OPP_FG3A", "sum"),
    STL=("STL", "sum"), BLK=("BLK", "sum"), DREB=("DREB", "sum"), OPP_TOV=("OPP_TOV", "sum"),
).reset_index()
tot["Opp PPG"] = tot["OPP_PTS"] / tot["GP"]
tot["Opp FG%"] = pct(tot["OFGM"], tot["OFGA"])
tot["Opp 3P%"] = pct(tot["O3M"], tot["O3A"])
tot = tot.rename(columns={"TEAM_ABBREVIATION": "Team", "OPP_PTS": "Opp PTS", "OPP_TOV": "Opp TOV"})
tot = tot.merge(stand, on="Team", how="left")

has_opp_shooting = df["OPP_FGA"].notna().any()
has_hustle = df["STL"].notna().any()
if not has_opp_shooting or not has_hustle:
    st.info("Some defensive numbers (opponent shooting, steals, blocks, rebounds, turnovers) "
            "aren't available for this season yet, so only what exists is shown.")

tab1, tab2, tab3 = st.tabs(["Team table", "Leaders", "Cumulative trend"])

with tab1:
    cols = ["NBA Rank", "Team", "W-L", "GP", "Opp PTS", "Opp PPG"]
    if has_opp_shooting:
        cols += ["Opp FG%", "Opp 3P%"]
    if has_hustle:
        cols += ["STL", "BLK", "DREB", "Opp TOV"]
    show = tot[cols].sort_values("Opp PPG").reset_index(drop=True)   # best defense first
    show.insert(0, "Sr. no.", show.index + 1)
    st.dataframe(show.round(1), hide_index=True, width="stretch")
    st.caption("Sorted by points allowed per game, fewest first. Opp TOV = turnovers the team forced.")

LOWER_BETTER = {"Opp PTS", "Opp PPG", "Opp FG%", "Opp 3P%"}

with tab2:
    options = ["Opp PPG", "Opp PTS"]
    if has_opp_shooting:
        options += ["Opp FG%", "Opp 3P%"]
    if has_hustle:
        options += ["STL", "BLK", "DREB", "Opp TOV"]
    metric = st.selectbox("Stat", options)
    asc = metric in LOWER_BETTER
    d = tot.sort_values(metric, ascending=asc)   # best first
    fig = px.bar(d, x="Team", y=metric, hover_data=["GP"])
    fig.update_layout(xaxis_title=None)
    st.plotly_chart(fig, width="stretch")
    c1, c2 = st.columns(2)
    c1.metric(f"Best {metric}", d.iloc[0]["Team"], f"{d.iloc[0][metric]:,.1f}")
    c2.metric(f"Worst {metric}", d.iloc[-1]["Team"], f"{d.iloc[-1][metric]:,.1f}")

with tab3:
    teams = sorted(df["TEAM_ABBREVIATION"].unique())
    pick = st.multiselect("Teams", teams, default=teams[:3])
    stat_map = {"Points allowed": "OPP_PTS"}
    if has_hustle:
        stat_map.update({"Steals": "STL", "Blocks": "BLK", "Defensive rebounds": "DREB",
                         "Turnovers forced": "OPP_TOV"})
    label = st.selectbox("Running total of", list(stat_map))
    if pick:
        t = df[df["TEAM_ABBREVIATION"].isin(pick)].copy()
        t["Game #"] = t.groupby("TEAM_ABBREVIATION").cumcount() + 1
        t["Running total"] = t.groupby("TEAM_ABBREVIATION")[stat_map[label]].cumsum()
        fig = px.line(t, x="Game #", y="Running total", color="TEAM_ABBREVIATION",
                      markers=True, hover_data=["GAME_DATE"])
        st.plotly_chart(fig, width="stretch")
