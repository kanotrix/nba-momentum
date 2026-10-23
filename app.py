from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from nba_api.stats.endpoints import leaguegamelog

st.set_page_config(page_title="NBA Momentum", layout="wide")
st.title("🏀 NBA Weekly Momentum")
_lu = Path("data/last_updated.txt")
if _lu.exists():
    st.info(f"Data last refreshed: {_lu.read_text()} (auto-updates daily at 2:30 PM IST)")
st.caption("Momentum = a team's average margin that week minus its season-to-date average before those games.")

# ---------- Sidebar ----------
season = st.sidebar.selectbox("Season", ["2026-27", "2025-26", "2024-25", "2023-24"], index=1)
cap = st.sidebar.slider("Cap blowout margin at ±", 10, 40, 20)
min_games = st.sidebar.slider("Min games per week", 1, 4, 2)


@st.cache_data(ttl=600, show_spinner="Loading games...")
def load(season):
    path = Path(f"data/games_{season}.csv")
    if path.exists():
        df = pd.read_csv(path)
    else:  # fallback: pull live (may be blocked on cloud hosts)
        df = leaguegamelog.LeagueGameLog(
            season=season, player_or_team_abbreviation="T", timeout=60
        ).get_data_frames()[0]
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
    return df.sort_values(["TEAM_ABBREVIATION", "GAME_DATE"])


def compute(df, cap, min_games):
    d = df.copy()
    d["margin"] = d["PLUS_MINUS"].clip(-cap, cap)
    # Baseline uses only games BEFORE each game (no leakage)
    d["baseline"] = d.groupby("TEAM_ABBREVIATION")["margin"].transform(
        lambda s: s.expanding().mean().shift(1)
    )
    d["week"] = d["GAME_DATE"].dt.to_period("W-SUN").dt.start_time
    w = (
        d.groupby(["TEAM_ABBREVIATION", "week"])
        .agg(week_margin=("margin", "mean"), baseline=("baseline", "mean"),
             games=("margin", "size"), wins=("WL", lambda s: (s == "W").sum()))
        .reset_index()
        .dropna(subset=["baseline"])
    )
    w = w[w["games"] >= min_games].copy()
    w["momentum"] = w["week_margin"] - w["baseline"]
    w["rank"] = w.groupby("week")["momentum"].rank(ascending=False).astype(int)
    w = w.sort_values(["TEAM_ABBREVIATION", "week"])
    w["rank_move"] = w.groupby("TEAM_ABBREVIATION")["rank"].diff().mul(-1)
    # Next week's margin, for validation
    w["next_margin"] = w.groupby("TEAM_ABBREVIATION")["week_margin"].shift(-1)
    return w


try:
    raw = load(season)
except Exception as e:
    st.error(f"Couldn't load data: {e}")
    st.stop()

if raw.empty:
    st.warning("No games for this season yet. Try an earlier season.")
    st.stop()

wk = compute(raw, cap, min_games)
if wk.empty:
    st.warning("Not enough games yet to compute momentum.")
    st.stop()

weeks = sorted(wk["week"].unique())
tab1, tab2, tab3, tab4 = st.tabs(["Power rankings", "Team trends", "Heatmap", "Does it predict?"])

with tab1:
    sel = st.select_slider("Week starting", options=weeks, value=weeks[-1],
                           format_func=lambda x: pd.Timestamp(x).strftime("%b %d"))
    t = wk[wk["week"] == sel].sort_values("rank")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Hottest", t.iloc[0]["TEAM_ABBREVIATION"], f"{t.iloc[0]['momentum']:+.1f}")
    c2.metric("🥶 Coldest", t.iloc[-1]["TEAM_ABBREVIATION"], f"{t.iloc[-1]['momentum']:+.1f}")
    show = t[["rank", "TEAM_ABBREVIATION", "momentum", "week_margin", "baseline", "games", "rank_move"]]
    show.columns = ["Rank", "Team", "Momentum", "Week margin", "Baseline", "Games", "Rank Δ"]
    st.dataframe(show.round(1), hide_index=True, use_container_width=True)

with tab2:
    teams = sorted(wk["TEAM_ABBREVIATION"].unique())
    pick = st.multiselect("Teams", teams, default=teams[:3])
    if pick:
        fig = px.line(wk[wk["TEAM_ABBREVIATION"].isin(pick)], x="week", y="momentum",
                      color="TEAM_ABBREVIATION", markers=True, hover_data=["games", "rank"])
        fig.add_hline(y=0, line_dash="dot")
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    pv = wk.pivot(index="TEAM_ABBREVIATION", columns="week", values="momentum")
    pv.columns = [pd.Timestamp(c).strftime("%b %d") for c in pv.columns]
    fig = px.imshow(pv, color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                    aspect="auto", labels=dict(color="Momentum"))
    fig.update_layout(height=700)
    st.plotly_chart(fig, use_container_width=True)

with tab4:
    v = wk.dropna(subset=["next_margin"])
    corr = v["momentum"].corr(v["next_margin"])
    st.metric("Correlation: momentum → next week's margin", f"{corr:.2f}")
    st.caption("Near 0 means weekly momentum doesn't predict next week. "
               "Compare against the baseline's own correlation below.")
    st.metric("Correlation: baseline → next week's margin", f"{v['baseline'].corr(v['next_margin']):.2f}")
    st.plotly_chart(px.scatter(v, x="momentum", y="next_margin", trendline="ols",
                               hover_data=["TEAM_ABBREVIATION", "week"]), use_container_width=True)
