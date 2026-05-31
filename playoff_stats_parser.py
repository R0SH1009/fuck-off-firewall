import pandas as pd
from collections import defaultdict

TOP_SCORER_MIN_GAMES = 2
DOUBLE_DOUBLE_THRESHOLD = 10

df = pd.read_csv("playoff_stats.csv")
df["Game_Date"] = pd.to_datetime(df["Game_Date"])
df["Win"] = df["Game_Outcome"].str.startswith("W")


def score_from_outcome(outcome):
    """Parse 'W 111-103' or 'L 114-127' into (team_score, opp_score)."""
    parts = outcome.split()
    scores = parts[1].split("-")
    team_score, opp_score = int(scores[0]), int(scores[1])
    if parts[0] == "L":
        team_score, opp_score = opp_score, team_score
    return team_score, opp_score


def compute_player_totals(df):
    agg = (
        df.groupby(["Team", "Player"])
        .agg(
            Games=("Game", "nunique"),
            Total_PTS=("PTS", "sum"),
            Total_AST=("AST", "sum"),
            Total_REB=("REB", "sum"),
            Total_MIN=("MIN", "sum"),
            Total_PF=("PF", "sum"),
        )
        .reset_index()
    )
    agg["PPG"] = (agg["Total_PTS"] / agg["Games"]).round(1)
    agg["APG"] = (agg["Total_AST"] / agg["Games"]).round(1)
    agg["RPG"] = (agg["Total_REB"] / agg["Games"]).round(1)
    return agg.sort_values("Total_PTS", ascending=False)


def compute_team_records(df):
    game_rows = df.drop_duplicates(subset=["Team", "Game"])
    records = {}
    for team, group in game_rows.groupby("Team"):
        wins = group["Win"].sum()
        losses = (~group["Win"]).sum()
        records[team] = {"wins": wins, "losses": losses, "games": len(group)}
    return records


def find_double_doubles(df, threshold=DOUBLE_DOUBLE_THRESHOLD):
    mask = (
        ((df["PTS"] >= threshold) & (df["REB"] >= threshold)) |
        ((df["PTS"] >= threshold) & (df["AST"] >= threshold)) |
        ((df["REB"] >= threshold) & (df["AST"] >= threshold))
    )
    return df[mask][["Team", "Game_Date", "Game", "Player", "PTS", "AST", "REB"]].copy()


def find_top_performers(df, stat="PTS", n=3):
    return df.nlargest(n, stat)[["Team", "Game", "Player", stat, "Game_Date"]]


def compute_game_scores(df):
    game_scores = []
    for (team, game, date, outcome, opponent), _ in df.groupby(
        ["Team", "Game", "Game_Date", "Game_Outcome", "Opponent"]
    ):
        team_score, opp_score = score_from_outcome(outcome)
        margin = team_score - opp_score
        game_scores.append({
            "Date": date.date(),
            "Game": game,
            "Team": team,
            "Opponent": opponent,
            "Score": f"{team_score}-{opp_score}",
            "Result": "W" if margin > 0 else "L",
            "Margin": abs(margin),
        })
    return sorted(game_scores, key=lambda x: x["Date"])


def generate_report(df, player_totals, team_records, double_doubles, game_scores):
    lines = []
    lines.append("=" * 60)
    lines.append("      NBA PLAYOFF STATS ANALYSIS REPORT")
    lines.append(f"Generated : {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    lines.append(f"\nTotal game-player entries : {len(df)}")
    lines.append(f"Players tracked           : {df['Player'].nunique()}")
    lines.append(f"Teams                     : {df['Team'].nunique()}")
    lines.append(f"Games covered             : {df['Game'].nunique()} per team")

    lines.append("\n--- TEAM RECORDS ---")
    for team, rec in sorted(team_records.items()):
        lines.append(f"  {team:<25} {rec['wins']}W - {rec['losses']}L  ({rec['games']} games)")

    lines.append("\n--- GAME LOG ---")
    lines.append(f"  {'Date':<12} {'Game':<8} {'Team':<25} {'vs':<25} {'Score':<10} {'Res':<4} {'Margin':>6}")
    lines.append(f"  {'-'*12} {'-'*8} {'-'*25} {'-'*25} {'-'*10} {'-'*4} {'-'*6}")
    for g in game_scores:
        lines.append(
            f"  {str(g['Date']):<12} {g['Game']:<8} {g['Team']:<25} "
            f"{g['Opponent']:<25} {g['Score']:<10} {g['Result']:<4} {g['Margin']:>6}"
        )

    lines.append("\n--- TOP SINGLE-GAME SCORING PERFORMANCES ---")
    top = find_top_performers(df, "PTS", 5)
    lines.append(f"  {'Player':<22} {'Team':<25} {'Game':<8} {'PTS':>4}")
    lines.append(f"  {'-'*22} {'-'*25} {'-'*8} {'-'*4}")
    for _, row in top.iterrows():
        lines.append(f"  {row['Player']:<22} {row['Team']:<25} {row['Game']:<8} {row['PTS']:>4}")

    lines.append("\n--- DOUBLE-DOUBLE PERFORMANCES ---")
    if double_doubles.empty:
        lines.append("  None recorded in this dataset.")
    else:
        lines.append(f"  {'Player':<22} {'Team':<25} {'Game':<8} {'PTS':>4} {'AST':>4} {'REB':>4}")
        lines.append(f"  {'-'*22} {'-'*25} {'-'*8} {'-'*4} {'-'*4} {'-'*4}")
        for _, row in double_doubles.iterrows():
            lines.append(
                f"  {row['Player']:<22} {row['Team']:<25} {row['Game']:<8} "
                f"{row['PTS']:>4} {row['AST']:>4} {row['REB']:>4}"
            )

    lines.append("\n--- PLAYER AVERAGES (sorted by total PTS) ---")
    lines.append(
        f"  {'Player':<22} {'Team':<25} {'G':>2} "
        f"{'PPG':>5} {'APG':>5} {'RPG':>5} {'Total PTS':>9}"
    )
    lines.append(
        f"  {'-'*22} {'-'*25} {'-'*2} "
        f"{'-'*5} {'-'*5} {'-'*5} {'-'*9}"
    )
    for _, row in player_totals.iterrows():
        lines.append(
            f"  {row['Player']:<22} {row['Team']:<25} {row['Games']:>2} "
            f"{row['PPG']:>5.1f} {row['APG']:>5.1f} {row['RPG']:>5.1f} {row['Total_PTS']:>9}"
        )

    lines.append("\n--- TEAM SCORING LEADERS ---")
    for team in sorted(df["Team"].unique()):
        team_players = player_totals[player_totals["Team"] == team].head(3)
        lines.append(f"\n  {team}")
        for _, row in team_players.iterrows():
            lines.append(
                f"    {row['Player']:<22}  {row['PPG']:>5.1f} PPG  "
                f"{row['APG']:>5.1f} APG  {row['RPG']:>5.1f} RPG"
            )

    lines.append("\n" + "=" * 60)
    total_pts = df["PTS"].sum()
    top_scorer = player_totals.iloc[0]
    lines.append(
        f"  Series leader: {top_scorer['Player']} ({top_scorer['Total_PTS']} PTS, "
        f"{top_scorer['PPG']} PPG across {top_scorer['Games']} games)"
    )
    lines.append(f"  Combined points scored across all tracked games: {total_pts}")
    lines.append("=" * 60)

    report_text = "\n".join(lines)
    with open("playoff_stats_report.txt", "w") as f:
        f.write(report_text)
    print(report_text)


player_totals = compute_player_totals(df)
team_records  = compute_team_records(df)
double_doubles = find_double_doubles(df)
game_scores   = compute_game_scores(df)

generate_report(df, player_totals, team_records, double_doubles, game_scores)

print("\n✅ Analysis complete! Check playoff_stats_report.txt for the full report.")
