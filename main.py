# NBA Game Visualizer - Version 1
# --------------------------------
# Set GAME_ID below, run program, get summary and an interactive Plotly momentum chart in browser.

import requests
import pandas as pd
import plotly.graph_objects as go
import os

GAME_ID = "401585723"  #Placeholder for now, will update so the user can choose

# Path to  CSV 
DATA_DIR = "data"
OUTPUT_HTML = "output.html"

# Fetch JSON from ESPN's play-by-play endpoint
def fetch_game_data(game_id):
    url = (
        f"http://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
        f"summary?event={game_id}"
    )
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Could not reach ESPN API: {e}")
        raise SystemExit(1)

    data = response.json()

    if "header" not in data:
        print("[ERROR] Check your GAME_ID.")
        raise SystemExit(1)

    return data

# Extract team names from JSON header section
def build_team_map(header):
    team_map = {}
    competitions = header.get("competitions", [{}])
    competitors = competitions[0].get("competitors", [])

    for competitor in competitors:
        team_id = competitor.get("id", "unknown")
        team_name = (
            competitor.get("team", {}).get("displayName")
            or competitor.get("team", {}).get("name")
            or team_id
        )
        team_map[team_id] = team_name

    return team_map

def clock_to_seconds(clock_str):
    if not clock_str:
        return 0

    parts = clock_str.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    elif len(parts) == 1:
        return float(parts[0])
    else:
        return 0
    
def elapsed_time(period, clock_str):
    if period < 1:
        return 0

    if period <= 4:
        total_seconds = (period - 1) * 720
    else:
        total_seconds = (4 * 720) + ((period - 4) * 300)

    total_seconds += (720 if period <= 4 else 300) - clock_to_seconds(clock_str)

    return total_seconds

def period_label(period):
    if period is None:
        return "Unknown"
    elif period == 1:
        return "1st"
    elif period == 2:
        return "2nd"
    elif period == 3:
        return "3rd"
    elif period == 4:
        return "4th"
    else:
        return f"OT{period - 4}"

def parse_plays(plays, team_map):

    rows = []

    for play in plays:
        # Resolve which team made this play
        team_id = str(play.get("team", {}).get("id", ""))
        team_name = team_map.get(team_id, team_id or "Unknown")

        row = {
            "period":       play.get("period", {}).get("number", None),
            "clock":        play.get("clock", {}).get("displayValue", ""),
            "team":         team_name,
            "type":         play.get("type", {}).get("text", ""),
            "text":         play.get("text", ""),
            "scoreValue":   play.get("scoreValue", 0),
            "homeScore":    play.get("homeScore", None),
            "awayScore":    play.get("awayScore", None),
            "scoringPlay":  play.get("scoringPlay", False),
            "periodLabel":  period_label(play.get("period", {}).get("number", None)),
            "elapsedTime":  elapsed_time(play.get("period", {}).get("number", 0), play.get("clock", {}).get("displayValue", "")),
        }
        rows.append(row)

    return rows

# Build momentum column

def compute_momentum(df):

    # Drop rows where scores are missing 
    df = df.dropna(subset=["homeScore", "awayScore"]).copy()

    df["homeScore"] = pd.to_numeric(df["homeScore"], errors="coerce").fillna(0)
    df["awayScore"] = pd.to_numeric(df["awayScore"], errors="coerce").fillna(0)

    df["momentum"] = df["homeScore"] - df["awayScore"]
    df["swing"]    = df["momentum"].diff().abs()
    df = df.reset_index(drop=True)

    return df


# Identify biggest momentum swings

def find_top_swings(df, n=5):

    scoring = df[df["scoringPlay"] == True].copy()
    if scoring.empty:
        scoring = df.copy()

    top = scoring.nlargest(n, "swing")
    return top

# Plotly graph
def plot_momentum(df, top_swings, home_name="Home", away_name="Away"):

    fig = go.Figure()

    # --- Main momentum line ---
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df["momentum"],
        mode="lines",
        name="Score differential",
        line=dict(color="#1d428a", width=2),   # NBA blue
        hovertemplate=(
            "Play %{x}<br>"
            "Differential: %{y}<br>"
            "%{customdata[0]} %{customdata[1]}<br>"
            "%{customdata[2]}<extra></extra>"
        ),
        customdata=df[["periodLabel", "elapsedTime", "text"]],
    ))

    # --- Horizontal zero line (tied game) ---
    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="gray",
        annotation_text="Tied",
        annotation_position="right",
    )

    # --- Top-swing markers ---
    if not top_swings.empty:
        fig.add_trace(go.Scatter(
            x=top_swings.index,
            y=top_swings["momentum"],
            mode="markers+text",
            name="Big swing",
            marker=dict(color="#c8102e", size=12, symbol="star"),   # NBA red
            text=top_swings["swing"].apply(lambda s: f"+{int(s)}"),
            textposition="top center",
            hovertemplate=(
                "Play %{x}<br>"
                "Differential: %{y}<br>"
                "Swing: %{customdata}<br>"
                "<extra></extra>"
            ),
            customdata=top_swings["text"],
        ))

# --- Quarter / OT divider lines along the game-minute scale ---
    for boundary in (12, 24, 36):
        fig.add_vline(x=boundary, line_dash="dot",
                      line_color="rgba(0,0,0,0.18)", line_width=1)
    for label, x_pos in (("Q1", 6), ("Q2", 18), ("Q3", 30), ("Q4", 42)):
        fig.add_annotation(x=x_pos, y=1, yref="paper", text=label,
                           showarrow=False,
                           font=dict(size=11, color="rgba(0,0,0,0.45)"))

    fig.update_layout(
        title=f"NBA Game Visualizer — {home_name} vs {away_name}",
        xaxis_title="Play number",
        yaxis_title="Score differential (home − away)",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    return fig


def save_csv(df, path):

    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)



def main():
    raw = fetch_game_data(GAME_ID)
    header = raw.get("header", {})
    plays_raw = raw.get("plays", [])
    team_map = build_team_map(header)
    competitions = header.get("competitions", [{}])
    competitors  = competitions[0].get("competitors", [])
    home_name, away_name = "Home", "Away"
    for c in competitors:
        name = c.get("team", {}).get("displayName", "")
        if c.get("homeAway") == "home":
            home_name = name
        else:
            away_name = name

    rows = parse_plays(plays_raw, team_map)
    if not rows:
        print("[ERROR] No play data found. Try a different GAME_ID.")
        raise SystemExit(1)


    df = pd.DataFrame(rows)
    df = compute_momentum(df)

    # Summary
    final_home = int(df["homeScore"].iloc[-1]) if not df.empty else "?"
    final_away = int(df["awayScore"].iloc[-1]) if not df.empty else "?"
    print("\n" + "=" * 50)
    print(f"  Game ID   : {GAME_ID}")
    print(f"  {home_name} (home) vs {away_name} (away)")
    print(f"  Final score: {home_name} {final_home} – {away_name} {final_away}")
    print(f"  Total plays: {len(df)}")
    print("=" * 50 + "\n")

    top_swings = find_top_swings(df, n=5)
    print("Top 5 momentum swings:")
    for i, (_, row) in enumerate(top_swings.iterrows(), 1):
        swing_val = int(row["swing"]) if pd.notna(row["swing"]) else 0
        print(f"  {i}. [{row['team']}] {row['text'][:80]}  (swing: +{swing_val})")
    print()

    csv_path = os.path.join(DATA_DIR, f"play_by_play_{GAME_ID}.csv")
    save_csv(df, csv_path)

    # Build chart and open in browser
    fig = plot_momentum(df, top_swings, home_name=home_name, away_name=away_name)
    fig.write_html(OUTPUT_HTML)
    print(f"[chart] Chart saved to {OUTPUT_HTML}")
    fig.show()   # opens in default browser


if __name__ == "__main__":
    main()
