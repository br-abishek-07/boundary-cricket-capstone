"""Cached ingestion, player profiles, matchups and auction trends."""

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


def filter_team_matches(frame, team_a, team_b, team1_column, team2_column):
    """Select a pair in either home/away order using the supplied team names."""
    if team_a == team_b:
        raise ValueError("Choose two different teams.")
    missing = {team1_column, team2_column} - set(frame.columns)
    if missing:
        raise ValueError("Missing team columns: " + ", ".join(sorted(missing)))
    forward = frame[team1_column].eq(team_a) & frame[team2_column].eq(team_b)
    reverse = frame[team1_column].eq(team_b) & frame[team2_column].eq(team_a)
    return frame.loc[forward | reverse].copy()


def summarize_head_to_head(records, team_a, team_b, winner_column):
    """Keep absent and unrecognized winners separate from confirmed wins."""
    result = {
        "matches": len(records), "a_wins": None, "b_wins": None,
        "no_winner": None, "unrecognized": None,
    }
    if winner_column not in records.columns:
        return result
    winners = records[winner_column].astype("string").str.strip()
    absent = winners.isna() | winners.eq("").fillna(False)
    a_wins = winners.eq(team_a).fillna(False)
    b_wins = winners.eq(team_b).fillna(False)
    result.update(
        a_wins=int(a_wins.sum()), b_wins=int(b_wins.sum()),
        no_winner=int(absent.sum()),
        unrecognized=int((~absent & ~a_wins & ~b_wins).sum()),
    )
    return result


def recent_team_encounters(records, date_column, venue_column,
                           winner_column, margin_column):
    """Return five dated encounters with explicit placeholders for missing fields."""
    display_columns = ["Date", "Venue", "Winner", "Margin"]
    if date_column not in records.columns:
        return pd.DataFrame(columns=display_columns), len(records)
    recent = records.copy()
    dates = pd.to_datetime(recent[date_column], errors="coerce")
    invalid_dates = int(dates.isna().sum())
    recent[date_column] = dates
    recent = recent.loc[dates.notna()].sort_values(date_column, ascending=False, kind="stable").head(5)
    display = pd.DataFrame(index=recent.index)
    display["Date"] = recent[date_column].dt.strftime("%Y-%m-%d")
    for label, column in [("Venue", venue_column), ("Winner", winner_column), ("Margin", margin_column)]:
        if column not in recent.columns:
            display[label] = "Not available in source"
        else:
            values = recent[column].astype("string")
            empty = values.isna() | values.str.strip().eq("").fillna(False)
            placeholder = "No recorded winner" if label == "Winner" else "Not recorded"
            display[label] = values.mask(empty, placeholder)
    return display.reset_index(drop=True), invalid_dates


def prepare_auction_records(frame, year_column, amount_column):
    """Preserve source rows and derive validated calendar years and amounts.

    Numeric strings may contain thousands separators. Currency symbols and
    crore/lakh suffixes are not guessed or silently converted.
    """
    missing = {year_column, amount_column} - set(frame.columns)
    if missing:
        raise ValueError("Missing auction columns: " + ", ".join(sorted(missing)))
    records = frame.copy()
    years = pd.to_numeric(records[year_column], errors="coerce")
    valid_year = years.notna() & years.ge(1) & years.le(9999) & years.mod(1).eq(0)
    records["_auction_year"] = years.where(valid_year).astype("Int64")
    amounts = pd.to_numeric(
        records[amount_column].astype("string").str.strip().str.replace(",", "", regex=False),
        errors="coerce",
    )
    valid_amount = amounts.notna() & amounts.ge(0) & amounts.lt(float("inf"))
    records["_auction_amount"] = amounts.where(valid_amount)
    return records


def aggregate_auction_spending(records, group_column):
    """Sum usable recorded amounts, retaining unnamed groups for reconciliation."""
    if group_column not in records.columns:
        raise ValueError(f"Auction grouping column not found: {group_column}")
    usable = records.loc[records["_auction_amount"].notna()].copy()
    groups = usable[group_column].astype("string").str.strip()
    groups = groups.mask(groups.isna() | groups.eq("").fillna(False), "Not recorded")
    result = usable.groupby(groups, dropna=False)["_auction_amount"].sum()
    result = result.sort_values(ascending=False, kind="stable").to_frame("Recorded amount")
    total = result["Recorded amount"].sum()
    result["Share (%)"] = 100 * result["Recorded amount"] / total if total > 0 else float("nan")
    return result


def top_auction_buys(records, player_column, team_column, category_columns, limit=10):
    """Rank individual source records, keeping repeat players and auction years."""
    usable = records.loc[records["_auction_amount"].notna()]
    top = usable.sort_values("_auction_amount", ascending=False, kind="stable").head(limit)
    display = pd.DataFrame(index=top.index)
    for label, column in [("Player", player_column), ("Team", team_column)]:
        values = top[column].astype("string").str.strip()
        display[label] = values.mask(values.isna() | values.eq("").fillna(False), "Not recorded")
    display["Year"] = top["_auction_year"].astype("string").fillna("Not recorded")
    display["Recorded amount"] = top["_auction_amount"]
    for column in dict.fromkeys(category_columns):
        if column in top.columns and column not in display.columns:
            values = top[column].astype("string").str.strip()
            display[column] = values.mask(values.isna() | values.eq("").fillna(False), "Not recorded")
    return display.reset_index(drop=True)


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
    st.caption("Phase 2 · Profiles, matchups and auctions")


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
        "Use the sidebar to explore player profiles, "
        "team matchups and historical auction trends."
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
    # EDIT THESE MAPPINGS to match a different match export.
    TEAM1_COLUMN = "team1"
    TEAM2_COLUMN = "team2"
    WINNER_COLUMN = "winner"
    DATE_COLUMN = "date"
    VENUE_COLUMN = "venue"
    MARGIN_COLUMN = "margin"  # Absent in the current export: shown as unavailable.
    COMPETITION_COLUMN = "competition"

    st.title("Team Matchups")
    st.caption(
        "Head-to-head evidence from the full supplied match archive. "
        "Historical team names are kept as supplied; coverage may be incomplete."
    )
    with st.expander("Inspect match headers and field availability"):
        st.write(matches.columns.tolist())
        st.caption("Column mappings are defined at the top of the Team Matchups block.")

    matchup_pool = matches
    if COMPETITION_COLUMN in matches.columns:
        competitions = sorted(matches[COMPETITION_COLUMN].dropna().astype(str).unique())
        scope_options = ["All supplied competitions", *competitions]
        scope = st.selectbox(
            "Matchup competition", scope_options,
            index=scope_options.index("IPL") if "IPL" in competitions else 0,
            key="matchup_competition",
        )
        if scope != "All supplied competitions":
            matchup_pool = matches.loc[matches[COMPETITION_COLUMN].astype(str).eq(scope)]
    else:
        scope = "All supplied records (competition column unavailable)"

    required_team_columns = {TEAM1_COLUMN, TEAM2_COLUMN}
    if not required_team_columns.issubset(matchup_pool.columns):
        st.warning("Map both team columns above to enable head-to-head research.")
    else:
        team_names = pd.concat(
            [matchup_pool[TEAM1_COLUMN], matchup_pool[TEAM2_COLUMN]], ignore_index=True
        ).dropna().astype(str)
        teams = sorted(team_names.loc[team_names.str.strip().ne("")].unique(), key=str.casefold)
        if len(teams) < 2:
            st.info("At least two named teams are needed for a matchup.")
        else:
            left, right = st.columns(2)
            team_a = left.selectbox(
                "Team A", teams, index=teams.index("RCB") if "RCB" in teams else 0,
                key="matchup_team_a",
            )
            team_b_options = [name for name in teams if name != team_a]
            team_b = right.selectbox(
                "Team B", team_b_options,
                index=team_b_options.index("CSK") if "CSK" in team_b_options else 0,
                key=f"matchup_team_b_{team_a}",
            )
            encounters = filter_team_matches(
                matchup_pool, team_a, team_b, TEAM1_COLUMN, TEAM2_COLUMN
            )
            summary = summarize_head_to_head(encounters, team_a, team_b, WINNER_COLUMN)
            st.subheader("Head-to-head summary")
            st.caption(f"{scope} · {team_a} vs {team_b} · both team orders included.")
            boxes = st.columns(4)
            for box, label, key in zip(
                boxes,
                ["Total Matches", f"{team_a} Wins", f"{team_b} Wins", "No recorded winner"],
                ["matches", "a_wins", "b_wins", "no_winner"],
            ):
                value = summary[key]
                box.metric(label, "N/A" if value is None else f"{value:,}")
            st.caption(
                "The current export omits outcome type. Matches with no recorded winner "
                "cannot be confirmed or separated into no-results and ties from this file."
            )
            if WINNER_COLUMN not in encounters.columns:
                st.warning("Winner column unavailable. Map it above to calculate wins and venue rates.")
            if summary["unrecognized"]:
                st.warning(
                    f"{summary['unrecognized']} records name a winner outside the selected pair. "
                    "They are included in total matches but excluded from win and no-winner counts."
                )
            if encounters.empty:
                st.info("No encounters between these teams were found in the selected archive scope.")

            st.subheader("Recent encounters")
            recent, invalid_dates = recent_team_encounters(
                encounters, DATE_COLUMN, VENUE_COLUMN, WINNER_COLUMN, MARGIN_COLUMN
            )
            if invalid_dates:
                st.warning(f"{invalid_dates} encounters lack valid dates and are omitted from the recent table.")
            if recent.empty:
                st.info("No dated encounters are available for the recent-match table.")
            else:
                st.dataframe(recent, hide_index=True, width="stretch")
                st.caption("Up to five latest dated matches. Same-date matches retain source order.")
            if MARGIN_COLUMN not in encounters.columns:
                st.caption("Margins are not included in this export; no margins have been inferred.")

            st.subheader("Venue impact · head-to-head win rates")
            if VENUE_COLUMN not in matchup_pool.columns:
                st.info("Map the venue column above to enable venue analysis.")
            else:
                venue_names = matchup_pool[VENUE_COLUMN].dropna().astype(str)
                venues = sorted(venue_names.loc[venue_names.str.strip().ne("")].unique())
                if not venues:
                    st.info("No named venues are available in the selected archive scope.")
                else:
                    observed_venues = encounters[VENUE_COLUMN].dropna().astype(str)
                    observed_venues = observed_venues.loc[observed_venues.isin(venues)].value_counts()
                    default_venue = observed_venues.index[0] if not observed_venues.empty else venues[0]
                    venue = st.selectbox(
                        "Venue", venues, index=venues.index(default_venue), key="matchup_venue"
                    )
                    venue_encounters = encounters.loc[encounters[VENUE_COLUMN].astype(str).eq(venue)]
                    venue_summary = summarize_head_to_head(venue_encounters, team_a, team_b, WINNER_COLUMN)
                    sample = venue_summary["matches"]
                    rates_available = sample > 0 and venue_summary["a_wins"] is not None
                    venue_boxes = st.columns(3)
                    venue_boxes[0].metric("Encounters at venue", f"{sample:,}")
                    for box, name, key in zip(venue_boxes[1:], [team_a, team_b], ["a_wins", "b_wins"]):
                        value = 100 * venue_summary[key] / sample if rates_available else None
                        box.metric(f"{name} Win %", "N/A" if value is None else f"{value:.1f}%")
                    st.caption(
                        "Win percentage = team wins ÷ all head-to-head encounters at this venue × 100. "
                        "Matches with no recorded winner remain in the denominator. "
                        "Venue names use exact source labels; spelling variants are not merged. "
                        "These are descriptive archive rates; small samples do not establish a venue advantage."
                    )
                    if not sample:
                        st.info("No encounters between these teams at this venue; win rates are unavailable.")
                    elif rates_available:
                        if venue_summary["unrecognized"]:
                            st.warning("Unrecognized winners at this venue are excluded from wins but included in the denominator.")
                        st.bar_chart(
                            pd.DataFrame(
                                {"Win percentage": [
                                    100 * venue_summary["a_wins"] / sample,
                                    100 * venue_summary["b_wins"] / sample,
                                ]}, index=[team_a, team_b]
                            ), y_label="Win percentage (0–100)",
                        )


elif selected_module == "Auction Trends":
    # EDIT THESE MAPPINGS for a different auction CSV.
    YEAR_COLUMN = "Year"
    PLAYER_COLUMN = "Player"
    AMOUNT_COLUMN = "Amount"
    TEAM_COLUMN = "Team"
    ROLE_COLUMN = "Role"
    ORIGIN_COLUMN = "Player Origin"
    CATEGORY_COLUMNS = [ROLE_COLUMN, ORIGIN_COLUMN]
    AMOUNT_UNIT_LABEL = "recorded source units (currency unverified)"

    st.title("Auction Trends")
    st.caption(
        "Explore historical amounts in the supplied CSV. Currency, units and transaction "
        "types are not documented in this file; these are not verified auction-purse totals "
        "or current market prices."
    )
    with st.expander("Inspect auction headers and column mappings"):
        st.write(auction.columns.tolist())
        st.caption("Edit the mapping variables at the top of the Auction Trends block.")

    required_columns = {YEAR_COLUMN, PLAYER_COLUMN, AMOUNT_COLUMN, TEAM_COLUMN}
    missing_columns = required_columns - set(auction.columns)
    if missing_columns:
        st.warning("Map the required auction columns above: " + ", ".join(sorted(missing_columns)))
    elif auction.empty:
        st.info("The auction dataset contains no records.")
    else:
        auction_records = prepare_auction_records(auction, YEAR_COLUMN, AMOUNT_COLUMN)
        years = sorted(auction_records["_auction_year"].dropna().astype(int).unique(), reverse=True)
        selected_year = st.selectbox(
            "Auction year", ["All Time", *[str(year) for year in years]], key="auction_year"
        )
        if selected_year == "All Time":
            scoped_auction = auction_records
        else:
            scoped_auction = auction_records.loc[
                auction_records["_auction_year"].eq(int(selected_year)).fillna(False)
            ].copy()
        undated_count = int(auction_records["_auction_year"].isna().sum())
        if undated_count:
            st.caption(
                f"{undated_count:,} records have no valid calendar year. "
                "They are included in All Time and excluded from individual-year selections."
            )
        usable_auction = scoped_auction.loc[scoped_auction["_auction_amount"].notna()]
        invalid_amount_count = len(scoped_auction) - len(usable_auction)
        if invalid_amount_count:
            st.warning(
                f"{invalid_amount_count:,} records have missing, negative or non-numeric amounts "
                "and are excluded from rankings and totals. Amounts must be finite numbers; "
                "currency symbols and unit suffixes need an explicit conversion."
            )
        total_amount = usable_auction["_auction_amount"].sum()
        boxes = st.columns(3)
        boxes[0].metric("Records in scope", f"{len(scoped_auction):,}")
        boxes[1].metric("Usable amount records", f"{len(usable_auction):,}")
        boxes[2].metric("Total recorded amount", f"{total_amount:,.0f}" if len(usable_auction) else "N/A")
        st.caption(f"Scope: {selected_year} · Amounts: {AMOUNT_UNIT_LABEL}. No inflation adjustment is applied.")

        if usable_auction.empty:
            st.info("No usable amounts are available for this selection.")
        else:
            st.subheader("Top 10 buys · recorded amounts")
            top_buys = top_auction_buys(
                scoped_auction, PLAYER_COLUMN, TEAM_COLUMN, CATEGORY_COLUMNS
            )
            st.dataframe(
                top_buys, hide_index=True, width="stretch",
                column_config={"Recorded amount": st.column_config.NumberColumn(format="localized")},
            )
            st.caption(
                "Each row is one source record. A player can appear more than once across years; "
                "All Time ranks individual records, not a player's cumulative earnings. "
                "Amounts are displayed without an assumed currency conversion."
            )

            st.subheader("Franchise spending · recorded amounts")
            team_totals = aggregate_auction_spending(scoped_auction, TEAM_COLUMN)
            st.bar_chart(
                team_totals[["Recorded amount"]],
                x_label="Team (source name)", y_label=AMOUNT_UNIT_LABEL,
                sort=False,
            )
            st.dataframe(team_totals, width="stretch")
            st.caption(
                "Totals sum usable records in the selected scope. Historical franchise names "
                "remain separate. Missing team names are included under Not recorded. "
                "These figures do not establish complete or official auction spending."
            )

            st.subheader("Category breakdown")
            available_categories = [
                column for column in dict.fromkeys(CATEGORY_COLUMNS) if column in scoped_auction.columns
            ]
            if not available_categories:
                st.info("No mapped role or origin categories are available in this CSV.")
            for category in available_categories:
                breakdown = aggregate_auction_spending(scoped_auction, category)
                st.markdown(f"**{category}**")
                st.bar_chart(
                    breakdown[["Recorded amount"]], x_label=category,
                    y_label=AMOUNT_UNIT_LABEL, sort=False,
                )
                st.dataframe(
                    breakdown, width="stretch",
                    column_config={"Share (%)": st.column_config.NumberColumn(format="%.2f%%")},
                )
            if available_categories:
                st.caption(
                    "Each category breakdown covers the same usable amount records. "
                    "Missing categories appear as Not recorded; role and origin breakdowns "
                    "are separate views of the same total. Percentage shares are unavailable "
                    "when the total amount is zero."
                )
