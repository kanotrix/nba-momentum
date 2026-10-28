from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="NBA Winning Analysis", layout="wide")
st.title("📈 NBA Winning Analysis")
st.caption("How offense and defense connect to winning. Uses the same filters as the other pages.")

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

NUM = ["PTS", "PLUS_MINUS", "OPP_PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "STL", "BLK", "DREB", "TOV"]
for c in NUM:
    if c not in raw.columns:
        raw[c] = pd.NA
    raw[c] = pd.to_numeric(raw[c], errors="coerce")
raw["OPP_PTS"] = raw["OPP_PTS"].fillna(raw["PTS"] - raw["PLUS_MINUS"])

OPP = [("FGM", "OPP_FGM"), ("FGA", "OPP_FGA"), ("FG3M", "OPP_FG3M"), ("FG3A", "OPP_FG3A"), ("TOV", "OPP_TOV")]
if "GAME_ID" in raw.columns and raw["GAME_ID"].notna().any():
    for c, o in OPP:
        g = raw.groupby("GAME_ID")[c]
        raw[o] = (g.transform("sum") - raw[c]).where(g.transform("count") == 2)
else:
    for _, o in OPP:
        raw[o] = np.nan
for _, o in OPP:
    raw[o] = pd.to_numeric(raw[o], errors="coerce")

dmin, dmax = raw["GAME_DATE"].min().date(), raw["GAME_DATE"].max().date()
span = st.sidebar.date_input("Games between", (dmin, dmax), min_value=dmin, max_value=dmax)
last_n = st.sidebar.selectbox("Games per team", ["All", "Last 10", "Last 20", "Last 30"])
conf = st.sidebar.radio("Conference", ["All teams", "Eastern", "Western"])

df = raw.copy()
if conf == "Eastern":
    df = df[df["TEAM_ABBREVIATION"].isin(EAST)]
elif conf == "Western":
    df = df[df["TEAM_ABBREVIATION"].isin(WEST)]
if isinstance(span, tuple) and len(span) == 2:
    df = df[(df["GAME_DATE"].dt.date >= span[0]) & (df["GAME_DATE"].dt.date <= span[1])]
if last_n != "All":
    df = df.groupby("TEAM_ABBREVIATION", group_keys=False).tail(int(last_n.split()[1]))
if df.empty:
    st.warning("No games in that range.")
    st.stop()


def ssum(s):
    return s.sum(min_count=1)   # stays empty (not 0) when a stat is missing


t = df.groupby("TEAM_ABBREVIATION").agg(
    GP=("PTS", "size"), W=("WL", lambda x: (x == "W").sum()),
    PF=("PTS", "sum"), PA=("OPP_PTS", "sum"),
    FGM=("FGM", ssum), FGA=("FGA", ssum), F3M=("FG3M", ssum), F3A=("FG3A", ssum),
    FTM=("FTM", ssum), FTA=("FTA", ssum),
    OFGM=("OPP_FGM", ssum), OFGA=("OPP_FGA", ssum), O3M=("OPP_FG3M", ssum), O3A=("OPP_FG3A", ssum),
    STL=("STL", ssum), BLK=("BLK", ssum), DREB=("DREB", ssum), TOV=("TOV", ssum), OTOV=("OPP_TOV", ssum),
).reset_index().rename(columns={"TEAM_ABBREVIATION": "Team"})
t["L"] = t["GP"] - t["W"]
t["Win%"] = t["W"] / t["GP"]
t["PPG"] = t["PF"] / t["GP"]
t["Opp PPG"] = t["PA"] / t["GP"]

if t["GP"].median() < 8:
    st.info("Few games played so far, so treat these results as rough. They get more reliable as the season goes on.")

tab1, tab2, tab3 = st.tabs(["Offense vs defense map", "What drives winning", "Expected wins"])

# ---------------- 1. Offense vs defense map ----------------
with tab1:
    avg_off, avg_def = t["PPG"].mean(), t["Opp PPG"].mean()

    def style(r):
        good_o, good_d = r["PPG"] >= avg_off, r["Opp PPG"] <= avg_def
        return ("Good at both" if good_o and good_d else
                "Offense-led" if good_o else
                "Defense-led" if good_d else "Struggling at both")

    t["Profile"] = t.apply(style, axis=1)
    fig = px.scatter(t, x="PPG", y="Opp PPG", color="Win%", text="Team",
                     color_continuous_scale="RdYlGn", hover_data=["GP", "W", "L"],
                     labels={"PPG": "Points scored per game", "Opp PPG": "Points allowed per game"})
    fig.update_traces(textposition="top center", marker=dict(size=13))
    fig.add_vline(x=avg_off, line_dash="dot")
    fig.add_hline(y=avg_def, line_dash="dot")
    fig.update_yaxes(autorange="reversed")   # up = better defense
    fig.update_layout(height=600)
    st.plotly_chart(fig, width="stretch")
    st.caption("Right = better offense. Up = better defense. Dotted lines mark the average. "
               "Top-right teams are good at both; color shows win rate.")
    m = t[["Team", "Profile", "PPG", "Opp PPG", "W", "L", "Win%"]].copy()
    m["Win%"] = (m["Win%"] * 100).round(1)
    st.dataframe(m.sort_values("Win%", ascending=False).round(1), hide_index=True, width="stretch")

# ---------------- 2. What drives winning ----------------
with tab2:
    def p(a, b):
        return (t[a] / t[b] * 100).where(t[b] > 0)

    drivers = {
        "Points scored / game": t["PPG"],
        "Points allowed / game": t["Opp PPG"],
        "FG%": p("FGM", "FGA"), "3P%": p("F3M", "F3A"), "FT%": p("FTM", "FTA"),
        "Opponent FG%": p("OFGM", "OFGA"), "Opponent 3P%": p("O3M", "O3A"),
        "Steals / game": t["STL"] / t["GP"], "Blocks / game": t["BLK"] / t["GP"],
        "Def. rebounds / game": t["DREB"] / t["GP"],
        "Turnovers / game (own)": t["TOV"] / t["GP"],
        "Turnovers forced / game": t["OTOV"] / t["GP"],
    }
    rows = []
    for name, ser in drivers.items():
        ok = ser.notna() & t["Win%"].notna()
        if ok.sum() >= 5 and ser[ok].std() > 0:
            rows.append({"Stat": name, "r": ser[ok].corr(t.loc[ok, "Win%"])})
    if len(t) < 5 or not rows:
        st.info("Need at least 5 teams with data to compare stats. Try 'All teams' or an earlier season.")
    else:
        c = pd.DataFrame(rows)
        c["Strength"] = pd.cut(c["r"].abs(), [-0.01, 0.3, 0.6, 1.01], labels=["Weak", "Moderate", "Strong"])
        c["Direction"] = np.where(c["r"] >= 0, "Higher = more wins", "Higher = fewer wins")
        c = c.sort_values("r")
        fig = px.bar(c, x="r", y="Stat", orientation="h", color="Direction",
                     color_discrete_map={"Higher = more wins": "#2e9e5b", "Higher = fewer wins": "#d6455d"},
                     labels={"r": "Link to win rate (-1 to +1)"})
        fig.update_layout(height=520, yaxis_title=None)
        st.plotly_chart(fig, width="stretch")

        # offense vs defense
        r_off = t["PPG"].corr(t["Win%"])
        r_def = -t["Opp PPG"].corr(t["Win%"])   # flip so higher = better defense
        X = np.column_stack([np.ones(len(t)), t["PPG"], t["Opp PPG"]])
        beta, *_ = np.linalg.lstsq(X, t["Win%"].to_numpy(), rcond=None)
        r2 = 1 - ((t["Win%"] - X @ beta) ** 2).sum() / ((t["Win%"] - t["Win%"].mean()) ** 2).sum()
        a, b, d = st.columns(3)
        a.metric("Offense explains", f"{r_off**2*100:.0f}% of win-rate gaps")
        b.metric("Defense explains", f"{r_def**2*100:.0f}% of win-rate gaps")
        d.metric("Both together", f"{r2*100:.0f}%")
        lead = "offense" if r_off**2 > r_def**2 else "defense"
        st.success(f"In this sample, {lead} is more closely linked to winning "
                   f"(based on {len(t)} teams).")
        show = c.sort_values("r", key=abs, ascending=False)[["Stat", "r", "Strength", "Direction"]]
        st.dataframe(show.round(2), hide_index=True, width="stretch")
        st.caption("A link is not a cause. Points scored and allowed are tied to winning by definition, so the "
                   "underlying stats (shooting, steals, turnovers) are the more interesting rows. "
                   "With only 30 teams, small differences between rows are noise.")

# ---------------- 3. Expected wins ----------------
with tab3:
    K = 14   # standard exponent for the NBA
    t["Exp win%"] = 1 / (1 + (t["PA"].astype(float) / t["PF"].astype(float)) ** K)
    t["Exp W"] = t["Exp win%"] * t["GP"]
    t["Diff"] = t["W"] - t["Exp W"]
    t["Verdict"] = np.where(t["Diff"] >= 1, "Overperforming",
                            np.where(t["Diff"] <= -1, "Underperforming", "In line"))
    d = t.sort_values("Diff")
    fig = px.bar(d, x="Team", y="Diff", color="Verdict",
                 color_discrete_map={"Overperforming": "#2e9e5b", "Underperforming": "#d6455d", "In line": "#8a8f98"},
                 labels={"Diff": "Actual wins minus expected wins"}, hover_data=["W", "Exp W"])
    fig.update_layout(xaxis_title=None)
    st.plotly_chart(fig, width="stretch")
    st.caption("Expected wins come from points scored and allowed (the Pythagorean formula, exponent 14). "
               "Overperforming teams won more than their scoring suggests, often through close games, "
               "and tend to drift back toward their expected record. Underperforming teams often rise.")
    out = t[["Team", "GP", "W", "L", "Exp W", "Diff", "Verdict"]].sort_values("Diff", ascending=False).copy()
    out.insert(0, "Sr. no.", range(1, len(out) + 1))
    st.dataframe(out.round(1), hide_index=True, width="stretch")
