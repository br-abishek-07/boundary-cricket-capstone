"""Cached data ingestion, navigation and Phase 2 player profiles."""

import pandas as pd
import streamlit as st

from data_loader import (
    load_auction,
    load_match_players,
    load_matches,
    load_player_registry,
    load_squads,
)


def filter_player_records(frame, player_id, player_id_column):
    """Join a registry selection to match records by ID, never by name."""
    if player_id_column not in frame.columns:
        raise ValueError(f"Player ID column not found: {player_id_column}")
    return frame.loc[
        frame[player_id_column].astype("string").eq(str(player_id))
    ].copy()


def calculate_career_metrics(records, stat_columns):
    """Aggregate supplied records; rates use total balls, not mean match rates.

    Return None for unavailable or invalid statistics. Economy is normalized
    to six legal balls, including when comparing different competitions.
    """
    totals = {}
    issues = []
    for statistic, column in stat_columns.items():
        if column not in records.columns:
            totals[statistic] = None
            issues.append(f"Missing column: {column}")
            continue
        values = pd.to_numeric(records[column], errors="coerce")
        valid = values.notna() & values.ge(0) & values.lt(float("inf"))
        if not valid.all():
            totals[statistic] = None
            issues.append(f"Invalid or missing numeric values in: {column}")
        else:
            total = values.sum()
            totals[statistic] = float(total) if pd.notna(total) else None

    runs = totals["runs"]
    balls = totals["balls"]
    conceded = totals["conceded"]
    legal_balls = totals["legal_balls"]
    metrics = {
        "runs": runs,
        "strike_rate": (
            100 * runs / balls
            if runs is not None and balls is not None and balls > 0 else None
        ),
        "wickets": totals["wickets"],
        "economy": (
            6 * conceded / legal_balls
            if conceded is not None and legal_balls is not None
            and legal_balls > 0 else None
        ),
    }
    return metrics, issues


st.set_page_config(
    page_title="IPL Intelligence 360°",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Sidebar navigation
with st.sidebar:
    st.title("IPL Intelligence 360°")
    st.caption("Cricket research and scouting")
    selected_module = st.radio(
        "Workspace",
        options=[
            "Home/Overview",
            "Player Profile",
            "Team Matchups",
            "Auction Trends",
        ],
    )
    st.divider()
    st.caption("Phase 2 · Player profiles")


# Initialize datasets. Cached loaders reuse their results on UI reruns.
try:
    with st.spinner("Preparing cricket datasets..."):
        matches = load_matches()
        match_players = load_match_players()
        squads = load_squads()
        auction = load_auction()
        player_registry = load_player_registry()
except (OSError, ValueError) as exc:
    st.error(f"Unable to load the project data: {exc}")
    st.info(
        "Check that all five files exist inside creaseiq/data/ "
        "or the repository's data/ folder and match the filenames "
        "in data_loader.py."
    )
    st.stop()


# Route to the selected workspace.
if selected_module == "Home/Overview":
    st.title("IPL Intelligence 360°")
    st.write(
        "A workspace for franchise scouting, player research, "
        "team comparisons and historical auction analysis."
    )
    st.success("All five datasets loaded successfully.")
    col1, col2, col3 = st.columns(3)
    col1.metric("Match records", f"{len(matches):,}")
    col2.metric("Player-match records", f"{len(match_players):,}")
    col3.metric("Registry entries", f"{len(player_registry):,}")
    st.caption(
        f"Squad records: {len(squads):,} · "
        f"Auction records: {len(auction):,}"
    )
    with st.expander("Preview the supplied match data"):
        st.dataframe(matches.head(10), width="stretch")
    st.info(
        "Use the sidebar to switch workspaces. "
        "Analytical tools will be added in Phase 2."
    )

elif selected_module == "Player Profile":
    # EDIT THESE MAPPINGS if the dataset headers change.
    PLAYER_ID_COLUMN = "player_id"
    REGISTRY_NAME_COLUMN = "name"
    RUNS_COLUMN = "runs"
    BALLS_FACED_COLUMN = "balls"
    WICKETS_COLUMN = "wickets"
    RUNS_CONCEDED_COLUMN = "conceded"
    LEGAL_BALLS_COLUMN = "legal_balls"
    DATE_COLUMN = "date"
    MATCH_ID_COLUMN = "match_id"
    COMPETITION_COLUMN = "competition"
    RECENT_MATCH_COUNT = 10

    st.title("Player Profile")
    st.caption(
        "Inspect the supplied archive by player identity. All phases are included; "
        "these records may not cover a complete official career."
    )
    with st.expander("Inspect dataset headers and column mappings"):
        st.write(match_players.columns.tolist())
        st.caption(
            "Statistical mappings are defined at the top of the Player Profile block. "
            "Bowling uses conceded runs and legal balls; legal balls are not decimal overs."
        )

    if REGISTRY_NAME_COLUMN not in player_registry.columns:
        st.warning(f"Registry name column not found: {REGISTRY_NAME_COLUMN}")
    else:
        names = player_registry[REGISTRY_NAME_COLUMN].dropna().astype(str)
        names = names.loc[names.str.strip().ne("")].sort_values(
            key=lambda values: values.str.casefold(), kind="stable"
        )
        name_by_id = {str(pid): name for pid, name in names.items()}
        if not name_by_id:
            st.info("No named players are available in the registry.")
        else:
            selected_player_id = st.selectbox(
                "Search for a player",
                options=list(name_by_id),
                format_func=lambda pid: f"{name_by_id[pid]} · {pid}",
                help="Type a name to search. The registry ID distinguishes identical names.",
            )
            try:
                player_records = filter_player_records(
                    match_players, selected_player_id, PLAYER_ID_COLUMN
                )
            except ValueError as exc:
                st.warning(str(exc))
            else:
                if player_records.empty:
                    st.info("No match records were found for this registry ID.")
                else:
                    # Keep competition scope explicit instead of silently mixing leagues.
                    if COMPETITION_COLUMN in player_records.columns:
                        competitions = sorted(
                            player_records[COMPETITION_COLUMN].dropna().astype(str).unique()
                        )
                        scope_options = ["All supplied competitions", *competitions]
                        scope = st.selectbox(
                            "Competition",
                            scope_options,
                            index=scope_options.index("IPL") if "IPL" in competitions else 0,
                            key=f"profile_competition_{selected_player_id}",
                        )
                        if scope != "All supplied competitions":
                            player_records = player_records.loc[
                                player_records[COMPETITION_COLUMN].astype(str).eq(scope)
                            ].copy()
                    else:
                        scope = "All supplied records (competition column unavailable)"
                    st.caption(
                        f"{name_by_id[selected_player_id]} · {selected_player_id} · "
                        f"{scope} · {len(player_records):,} recorded player-match rows. "
                        "These totals use the full supplied sample, not the scouting filters."
                    )

                    metrics, issues = calculate_career_metrics(
                        player_records,
                        {
                            "runs": RUNS_COLUMN,
                            "balls": BALLS_FACED_COLUMN,
                            "wickets": WICKETS_COLUMN,
                            "conceded": RUNS_CONCEDED_COLUMN,
                            "legal_balls": LEGAL_BALLS_COLUMN,
                        },
                    )
                    if issues:
                        st.warning("Some metrics are unavailable. " + "; ".join(issues))
                    columns = st.columns(4)
                    for box, label, key, decimals in zip(
                        columns,
                        ["Total Runs", "Batting Strike Rate", "Total Wickets", "Bowling Economy"],
                        ["runs", "strike_rate", "wickets", "economy"],
                        [0, 2, 0, 2],
                    ):
                        value = metrics[key]
                        box.metric(label, "N/A" if value is None else f"{value:,.{decimals}f}")
                    st.caption(
                        "Strike rate = 100 × total runs ÷ balls faced. "
                        "Economy = 6 × conceded runs ÷ legal balls. "
                        "N/A means unavailable data or a zero denominator."
                    )
                    with st.expander("Inspect selected player's raw match records"):
                        st.dataframe(player_records, width="stretch", hide_index=True)

                    st.subheader("Recent form · runs by match")
                    st.caption(
                        "A basic line-chart starting point for the last ten recorded appearances. "
                        "Zero runs can include an appearance without batting."
                    )
                    if not {DATE_COLUMN, RUNS_COLUMN}.issubset(player_records.columns):
                        st.info("Map the date and runs columns above to enable the recent-form chart.")
                    else:
                        recent = player_records.copy()
                        recent[DATE_COLUMN] = pd.to_datetime(recent[DATE_COLUMN], errors="coerce")
                        recent[RUNS_COLUMN] = pd.to_numeric(recent[RUNS_COLUMN], errors="coerce")
                        valid = (
                            recent[DATE_COLUMN].notna()
                            & recent[RUNS_COLUMN].notna()
                            & recent[RUNS_COLUMN].ge(0)
                            & recent[RUNS_COLUMN].lt(float("inf"))
                        )
                        if not valid.all():
                            st.warning("Rows with invalid dates or runs were omitted from the chart.")
                        order = [DATE_COLUMN]
                        if MATCH_ID_COLUMN in recent.columns:
                            order.append(MATCH_ID_COLUMN)
                        recent = recent.loc[valid].sort_values(order, kind="stable").tail(RECENT_MATCH_COUNT)
                        if recent.empty:
                            st.info("No dated numeric run records are available for a line chart.")
                        else:
                            chart_data = pd.DataFrame(
                                {"Match": range(1, len(recent) + 1), "Runs": recent[RUNS_COLUMN].to_numpy()}
                            )
                            st.line_chart(
                                chart_data, x="Match", y="Runs",
                                x_label="Recent appearances (oldest to newest)", y_label="Runs",
                            )
                            st.caption(
                                f"Chart window: {recent[DATE_COLUMN].min():%Y-%m-%d} "
                                f"to {recent[DATE_COLUMN].max():%Y-%m-%d}."
                            )


elif selected_module == "Team Matchups":
    st.title("Team Matchups")
    st.write(
        "Compare teams using the supplied historical match records."
    )
    st.info(
        "Phase 2: team selection, head-to-head summaries "
        "and matchup analysis."
    )
    st.caption(f"Available: {len(matches):,} match records.")

elif selected_module == "Auction Trends":
    st.title("Auction Trends")
    st.write("Inspect the supplied historical auction records.")
    st.info(
        "Phase 2: auction exploration and trends, "
        "after reviewing the dataset's fields and units."
    )
    st.caption(f"Available: {len(auction):,} auction records.")
