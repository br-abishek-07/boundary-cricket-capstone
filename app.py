"""Cricket analytics with evidence-bound DeepSeek specialist reports."""

import hashlib
import json

import pandas as pd
import streamlit as st

from agents import (
    ScoutReportError, generate_player_scout_report, scout_context_fingerprint,
    generate_matchup_report, matchup_context_fingerprint,
    generate_auction_report, auction_context_fingerprint,
)

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


def build_player_scout_evidence(records, player_id, player_name, competition,
                               metrics, metric_issues, stat_columns,
                               date_column, match_id_column):
    """Build a small JSON packet from the complete selected loaded sample."""
    facts = []
    definitions = [
        ("F1", "Total runs", metrics["runs"], "runs"),
        ("F3", "Batting strike rate", metrics["strike_rate"], "runs per hundred balls faced"),
        ("F4", "Bowler-credited wickets", metrics["wickets"], "wickets"),
        ("F7", "Bowling economy", metrics["economy"], "runs per six legal balls"),
        ("F8", "Named player-match records", len(records), "records, including possible no-batting appearances"),
    ]
    raw_totals = {}
    for key, fid, label, unit in [
        ("balls", "F2", "Balls faced", "balls"),
        ("conceded", "F5", "Bowling runs conceded", "runs"),
        ("legal_balls", "F6", "Legal balls bowled", "balls"),
    ]:
        column = stat_columns[key]
        if column in records:
            values = pd.to_numeric(records[column], errors="coerce")
            if (values.notna() & values.ge(0) & values.lt(float("inf"))).all():
                raw_totals[key] = float(values.sum())
                definitions.append((fid, label, raw_totals[key], unit))
    for fid, label, value, unit in sorted(definitions):
        if value is not None:
            facts.append({"id": fid, "metric": label, "value": float(value), "unit": unit})

    limitations = [
        "Figures describe the supplied archive, whose completeness is not certified.",
        "Technique, fitness, current availability, market value and future performance are not supplied.",
        "Named player-match records can include appearances without batting or bowling.",
        "No peer benchmark or phase-specific scouting comparison is included in this packet.",
    ]
    limitations.extend(metric_issues)
    if not raw_totals.get("balls"):
        limitations.append("Usable batting exposure is unavailable or zero.")
    if not raw_totals.get("legal_balls"):
        limitations.append("Usable bowling exposure is unavailable or zero.")

    dates = pd.to_datetime(records[date_column], errors="coerce") if date_column in records else pd.Series(pd.NaT, index=records.index)
    valid_dates = dates.dropna()
    if dates.isna().any():
        limitations.append("Some records lack valid dates and are omitted from the recent-match sample.")
    selected_columns = list(dict.fromkeys(
        column for column in [match_id_column, date_column, *stat_columns.values()]
        if column in records.columns
    ))
    recent = records.loc[dates.notna(), selected_columns].copy()
    if date_column in recent:
        recent[date_column] = dates.loc[recent.index]
        order = [date_column]
        if match_id_column in recent:
            recent[match_id_column] = recent[match_id_column].astype(str)
            order.append(match_id_column)
        recent = recent.sort_values(order, kind="stable").tail(10)
    # Hash the full loaded selected records, not just the recent ten rows.
    source_hash = hashlib.sha256(
        pd.util.hash_pandas_object(records, index=True).values.tobytes()
        + json.dumps(list(records.columns)).encode("utf-8")
    ).hexdigest()
    recent_rows = json.loads(recent.to_json(orient="records", date_format="iso"))
    # Give recent batting evidence its own references for supported form comments.
    for offset, row in enumerate(recent_rows):
        runs = pd.to_numeric(row.get(stat_columns["runs"]), errors="coerce")
        if pd.notna(runs) and runs >= 0 and runs < float("inf"):
            fid = f"F{9 + offset}"
            row["fact_id"] = fid
            facts.append({
                "id": fid,
                "metric": f"Runs in recorded match {row.get(match_id_column, 'unidentified')} on {row.get(date_column, 'undated')}",
                "value": float(runs), "unit": "runs; the appearance may include no batting",
            })
    return {
        "task": "player_scouting",
        "player": {"id": str(player_id), "name": str(player_name)},
        "scope": {
            "competition": competition, "phase": "All",
            "since": valid_dates.min().date().isoformat() if len(valid_dates) else None,
            "through_inclusive": valid_dates.max().date().isoformat() if len(valid_dates) else None,
            "coverage": "Full selected supplied archive sample; not a certified complete career",
            "source": "match_players.csv.gz (loaded selected records)",
        },
        "facts": facts,
        "recent_matches": recent_rows,
        "limitations": list(dict.fromkeys(limitations)),
        "source_fingerprint": source_hash,
    }


def build_matchup_evidence(encounters, team_a, team_b, competition, selected_venue,
                           winner_column, date_column, venue_column, margin_column):
    """Compute matchup evidence from the same complete records used by the UI."""
    overall = summarize_head_to_head(encounters, team_a, team_b, winner_column)
    recent, invalid_dates = recent_team_encounters(
        encounters, date_column, venue_column, winner_column, margin_column
    )
    limitations = [
        "The supplied archive may not provide complete historical coverage.",
        "Historical patterns do not establish current superiority or future win probabilities.",
        "Current lineups, fitness, pitch, weather and tactical player matchups are not supplied.",
        "Team and venue names use exact source labels; naming variants are not merged.",
        "Recent encounters and venue samples may be too small for tactical conclusions.",
    ]
    if winner_column not in encounters:
        limitations.append("Winner data is unavailable in this export.")
    limitations.append("Outcome type is unavailable; absent winners cannot be confirmed as ties or no-results.")
    if margin_column not in encounters:
        limitations.append("Match margins are unavailable and have not been inferred.")
    if overall["unrecognized"]:
        limitations.append("Some winner labels fall outside the selected pair and are excluded from win counts.")
    if invalid_dates:
        limitations.append("Some encounters lack valid dates and are omitted from the recent sample.")

    facts = []
    def add(fid, label, value, unit):
        if value is not None:
            facts.append({"id": fid, "metric": label, "value": value, "unit": unit})
    for fid, label, key in [
        ("F1", "Overall head-to-head encounters", "matches"),
        ("F2", f"Overall wins by {team_a}", "a_wins"),
        ("F3", f"Overall wins by {team_b}", "b_wins"),
        ("F4", "Overall encounters with no recorded winner", "no_winner"),
        ("F5", "Overall encounters with unrecognized winners", "unrecognized"),
    ]:
        add(fid, label, overall[key], "matches in the selected archive scope")

    venue_summary = None
    a_rate = b_rate = None
    if selected_venue is not None and venue_column in encounters:
        venue_records = encounters.loc[encounters[venue_column].astype(str).eq(selected_venue)]
        venue_summary = summarize_head_to_head(venue_records, team_a, team_b, winner_column)
        for fid, label, key in [
            ("F6", "Encounters at selected venue", "matches"),
            ("F7", f"Wins by {team_a} at selected venue", "a_wins"),
            ("F8", f"Wins by {team_b} at selected venue", "b_wins"),
            ("F9", "Selected-venue encounters with no recorded winner", "no_winner"),
        ]:
            add(fid, label, venue_summary[key], "head-to-head matches at the exact selected venue label")
        if venue_summary["matches"] and venue_summary["a_wins"] is not None:
            a_rate = 100 * venue_summary["a_wins"] / venue_summary["matches"]
            b_rate = 100 * venue_summary["b_wins"] / venue_summary["matches"]
            add("F10", f"Historical venue win percentage for {team_a}", a_rate, "percent of all head-to-head encounters at selected venue")
            add("F11", f"Historical venue win percentage for {team_b}", b_rate, "percent of all head-to-head encounters at selected venue")
        else:
            limitations.append("Venue win percentages are unavailable because encounters or winner data are absent.")
    else:
        limitations.append("No venue-specific evidence is selected or available.")
    recent_rows = json.loads(recent.to_json(orient="records"))
    for offset, row in enumerate(recent_rows):
        fid = f"F{12 + offset}"
        row["fact_id"] = fid
        add(fid, f"Recorded winner for recent encounter on {row['Date']}",
            row["Winner"], "source result label; absence does not confirm a tie")
    dates = pd.to_datetime(encounters[date_column], errors="coerce").dropna() if date_column in encounters else pd.Series(dtype="datetime64[ns]")
    source_hash = hashlib.sha256(
        pd.util.hash_pandas_object(encounters, index=True).values.tobytes()
        + json.dumps(list(encounters.columns)).encode("utf-8")
    ).hexdigest()
    return {
        "task": "matchup_analysis", "teams": {"team_a": team_a, "team_b": team_b},
        "scope": {
            "competition": competition, "venue": selected_venue,
            "since": dates.min().date().isoformat() if len(dates) else None,
            "through_inclusive": dates.max().date().isoformat() if len(dates) else None,
            "coverage": "Full selected supplied head-to-head archive, including both team orders",
            "source": "matches.csv.gz (loaded selected records)",
        },
        "head_to_head": overall, "recent_matches": recent_rows,
        "venue": {"name": selected_venue, "head_to_head": venue_summary,
                  "team_a_win_percentage": a_rate, "team_b_win_percentage": b_rate,
                  "denominator": "All head-to-head encounters at the exact selected venue label, including absent winners"},
        "facts": facts, "limitations": limitations, "source_fingerprint": source_hash,
    }


def build_auction_evidence(records, selected_year, player_column, team_column,
                           category_columns, amount_unit_label):
    """Build cited auction evidence from the selected, validated source rows."""
    usable = records.loc[records["_auction_amount"].notna()]
    total = float(usable["_auction_amount"].sum()) if len(usable) else None
    invalid_count = len(records) - len(usable)
    unknown_year_count = int(records["_auction_year"].isna().sum())
    limitations = [
        "Currency, amount units and transaction definitions are unverified in the supplied CSV.",
        "No inflation adjustment or currency conversion is applied.",
        "These historical records do not establish current market prices, fair value or recommended bids.",
        "Source rows are not verified winning bids; auction, retention and transfer classifications are not supplied.",
        "Rows are source records, not necessarily unique players; top buys rank individual records, not cumulative earnings.",
        "Historical franchise names remain separate and source coverage may be incomplete.",
        "Role and origin distributions are separate views of the same total and must not be added together.",
    ]
    if unknown_year_count:
        limitations.append("Some records have unknown years; All Time includes them while individual-year views exclude them.")
    if invalid_count:
        limitations.append("Records with unusable amounts are excluded from monetary rankings and totals.")
    if total == 0:
        limitations.append("Recorded total amount is zero; percentage shares are unavailable.")
    if not len(usable):
        limitations.append("No usable amounts are available for this selection.")

    facts = []
    def add(label, value, unit):
        if value is None:
            return None
        fid = f"F{len(facts) + 1}"
        facts.append({"id": fid, "metric": label, "value": value, "unit": unit})
        return fid
    add("Total recorded amount in selection", total, amount_unit_label)
    add("Source records in selection", len(records), "source rows, not necessarily unique players")
    add("Records with usable amounts", len(usable), "source rows")
    add("Records excluded from monetary totals", invalid_count, "source rows")
    add("Records with unknown year in selection", unknown_year_count, "source rows")
    top = top_auction_buys(records, player_column, team_column, category_columns)
    top_rows = json.loads(top.to_json(orient="records"))
    for rank, row in enumerate(top_rows, 1):
        row["rank_in_selected_records"] = rank
        row["fact_ids"] = {"amount": add(
            f"Recorded amount for {row['Player']} · {row['Team']} · {row['Year']}",
            float(row["Recorded amount"]), amount_unit_label,
        )}

    def grouped_rows(column, label_key):
        table = aggregate_auction_spending(records, column)
        result = []
        for name, row in table.iterrows():
            amount = float(row["Recorded amount"])
            share = float(row["Share (%)"]) if pd.notna(row["Share (%)"]) else None
            refs = {"amount": add(f"Total recorded amount for {column}: {name}", amount, amount_unit_label)}
            if share is not None:
                refs["share_percent"] = add(
                    f"Share of selected recorded amount for {column}: {name}", share,
                    "percent of the same selected usable-amount total",
                )
            result.append({label_key: str(name), "recorded_amount": amount,
                           "share_percent": share, "fact_ids": refs})
        return result

    franchise_totals = grouped_rows(team_column, "team")
    categories = {}
    for category in dict.fromkeys(category_columns):
        if category in records:
            categories[category] = grouped_rows(category, "category")
    if not categories:
        limitations.append("No mapped role or origin categories are available.")
    limitations.append("Missing franchise or category labels are retained under Not recorded, not inferred.")
    source_hash = hashlib.sha256(
        pd.util.hash_pandas_object(records, index=True).values.tobytes()
        + json.dumps(list(records.columns)).encode("utf-8")
    ).hexdigest()
    return {
        "task": "auction_analysis",
        "scope": {
            "selected_year": str(selected_year), "amount_unit_label": amount_unit_label,
            "known_years_in_selection": sorted(records["_auction_year"].dropna().astype(int).unique().tolist()),
            "coverage": "Selected supplied source records; completeness and transaction types unverified",
            "source": "auction.csv (loaded selected records and validated derived amounts)",
            "inflation_adjusted": False, "currency_verified": False,
        },
        "summary": {"source_records": len(records), "usable_amount_records": len(usable),
                    "excluded_amount_records": invalid_count, "unknown_year_records": unknown_year_count,
                    "total_recorded_amount": total},
        "top_buys": top_rows, "franchise_spending": franchise_totals,
        "category_breakdowns": categories, "facts": facts,
        "limitations": limitations, "source_fingerprint": source_hash,
    }


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
    st.caption("Phase 3 · Scout, Matchup and Auction")


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


                    st.divider()
                    st.subheader("Player Scout · DeepSeek")
                    st.caption(
                        "Generate an interpretation of the selected archive evidence. "
                        "This sends the evidence packet to DeepSeek only when you click the button. "
                        "Numerical values remain calculated and displayed by Python."
                    )
                    scout_packet = build_player_scout_evidence(
                        player_records, selected_player_id, name_by_id[selected_player_id],
                        scope, metrics, issues,
                        {"runs": RUNS_COLUMN, "balls": BALLS_FACED_COLUMN,
                         "wickets": WICKETS_COLUMN, "conceded": RUNS_CONCEDED_COLUMN,
                         "legal_balls": LEGAL_BALLS_COLUMN},
                        DATE_COLUMN, MATCH_ID_COLUMN,
                    )
                    with st.expander("Inspect evidence sent to the scout"):
                        st.json(scout_packet)
                    try:
                        scout_fingerprint = scout_context_fingerprint(scout_packet)
                    except ScoutReportError as exc:
                        st.warning(str(exc))
                    else:
                        saved_scout = st.session_state.get("player_scout_report")
                        if st.button("Generate Scouting Report", disabled=len(scout_packet["facts"]) < 2):
                            if saved_scout and saved_scout["fingerprint"] == scout_fingerprint:
                                st.info("Using the saved report for this exact evidence and model.")
                            else:
                                st.session_state.pop("player_scout_report", None)
                                saved_scout = None
                                try:
                                    with st.spinner("Scouting player..."):
                                        scout_report = generate_player_scout_report(scout_packet)
                                    if scout_report["_provenance"]["context_fingerprint"] != scout_fingerprint:
                                        raise ScoutReportError("The report context changed. Generate a new report.")
                                    saved_scout = {"fingerprint": scout_fingerprint, "report": scout_report}
                                    st.session_state["player_scout_report"] = saved_scout
                                except ScoutReportError as exc:
                                    st.error(str(exc))
                                except Exception:
                                    st.error("The scouting request could not be completed. Your statistics remain available.")
                        if saved_scout and saved_scout["fingerprint"] != scout_fingerprint:
                            st.info("The saved report belongs to different evidence or settings. Generate a matching report.")
                        elif saved_scout:
                            scout_report = saved_scout["report"]
                            fact_lookup = {fact["id"]: fact for fact in scout_packet["facts"]}
                            for section, label in [
                                ("observations", "Evidence-backed observations"),
                                ("interpretations", "Tentative interpretations"),
                            ]:
                                st.markdown(f"**{label}**")
                                if not scout_report[section]:
                                    st.caption("No supported interpretation was returned.")
                                for finding in scout_report[section]:
                                    st.write(finding["text"])
                                    st.caption(" · ".join(
                                        f"[{fid}] {fact_lookup[fid]['metric']}: "
                                        f"{fact_lookup[fid]['value']:,.2f} {fact_lookup[fid]['unit']}"
                                        for fid in finding["fact_ids"]
                                    ))
                            st.markdown("**Limitations**")
                            for limitation in dict.fromkeys(scout_packet["limitations"] + scout_report["limitations"]):
                                st.warning(limitation)
                            if scout_report["next_steps"]:
                                st.markdown("**Suggested review actions**")
                                for action in scout_report["next_steps"]:
                                    st.write(action)
                            st.caption(
                                "AI-generated interpretation; citations and structure are checked. "
                                "These checks do not certify tactical correctness or future performance. "
                                "This report is saved only in this browser session."
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
    selected_venue = None

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
                    selected_venue = venue
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


            st.divider()
            st.subheader("Matchup Analyst · DeepSeek")
            st.caption(
                "Generate an interpretation of the selected head-to-head and venue evidence. "
                "Only clicking the button sends this packet to DeepSeek."
            )
            matchup_packet = build_matchup_evidence(
                encounters, team_a, team_b, scope, selected_venue,
                WINNER_COLUMN, DATE_COLUMN, VENUE_COLUMN, MARGIN_COLUMN,
            )
            with st.expander("Inspect evidence sent to the Matchup Analyst"):
                st.json(matchup_packet)
            try:
                matchup_fingerprint = matchup_context_fingerprint(matchup_packet)
            except ScoutReportError as exc:
                st.warning(str(exc))
            else:
                saved_matchup = st.session_state.get("matchup_analyst_report")
                if st.button("Generate Matchup Report", disabled=encounters.empty):
                    if saved_matchup and saved_matchup["fingerprint"] == matchup_fingerprint:
                        st.info("Using the saved matchup report for this exact evidence and model.")
                    else:
                        st.session_state.pop("matchup_analyst_report", None)
                        saved_matchup = None
                        try:
                            with st.spinner("Analysing matchup..."):
                                matchup_report = generate_matchup_report(matchup_packet)
                            if matchup_report["_provenance"]["context_fingerprint"] != matchup_fingerprint:
                                raise ScoutReportError("The matchup context changed. Generate a new report.")
                            saved_matchup = {"fingerprint": matchup_fingerprint, "report": matchup_report}
                            st.session_state["matchup_analyst_report"] = saved_matchup
                        except ScoutReportError as exc:
                            st.error(str(exc))
                        except Exception:
                            st.error("The matchup report could not be completed. Your match statistics remain available.")
                if saved_matchup and saved_matchup["fingerprint"] != matchup_fingerprint:
                    st.info("The saved matchup report belongs to different teams, venue, evidence or settings. Generate a matching report.")
                elif saved_matchup:
                    matchup_report = saved_matchup["report"]
                    fact_lookup = {fact["id"]: fact for fact in matchup_packet["facts"]}
                    for section, label in [
                        ("observations", "Historical observations"),
                        ("interpretations", "Tentative tactical interpretations"),
                    ]:
                        st.markdown(f"**{label}**")
                        if not matchup_report[section]:
                            st.caption("No supported interpretation was returned.")
                        for finding in matchup_report[section]:
                            st.write(finding["text"])
                            citations = []
                            for fid in finding["fact_ids"]:
                                fact = fact_lookup[fid]
                                value = fact["value"]
                                display_value = f"{value:,.2f}" if isinstance(value, (int, float)) else str(value)
                                citations.append(f"[{fid}] {fact['metric']}: {display_value} {fact['unit']}")
                            st.caption(" · ".join(citations))
                    st.markdown("**Limitations**")
                    for limitation in dict.fromkeys(matchup_packet["limitations"] + matchup_report["limitations"]):
                        st.warning(limitation)
                    if matchup_report["next_steps"]:
                        st.markdown("**Suggested review actions**")
                        for action in matchup_report["next_steps"]:
                            st.write(action)
                    st.caption(
                        "AI-generated historical interpretation. Structure and citations are checked; "
                        "tactical correctness and future performance are not certified. "
                        "This report is saved only in this browser session."
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

        st.divider()
        st.subheader("Auction Analyst · DeepSeek")
        st.caption(
            "Generate a historical interpretation of this year's selection or All Time. "
            "Only clicking the button sends this evidence packet to DeepSeek."
        )
        auction_packet = build_auction_evidence(
            scoped_auction, selected_year, PLAYER_COLUMN, TEAM_COLUMN,
            CATEGORY_COLUMNS, AMOUNT_UNIT_LABEL,
        )
        with st.expander("Inspect evidence sent to the Auction Analyst"):
            st.json(auction_packet)
        try:
            auction_fingerprint = auction_context_fingerprint(auction_packet)
        except ScoutReportError as exc:
            st.warning(str(exc))
        else:
            saved_auction = st.session_state.get("auction_analyst_report")
            if st.button("Generate Auction Report", disabled=usable_auction.empty):
                if saved_auction and saved_auction["fingerprint"] == auction_fingerprint:
                    st.info("Using the saved auction report for this exact evidence and model.")
                else:
                    st.session_state.pop("auction_analyst_report", None)
                    saved_auction = None
                    try:
                        with st.spinner("Analysing auction..."):
                            auction_report = generate_auction_report(auction_packet)
                        if auction_report["_provenance"]["context_fingerprint"] != auction_fingerprint:
                            raise ScoutReportError("The auction context changed. Generate a new report.")
                        saved_auction = {"fingerprint": auction_fingerprint, "report": auction_report}
                        st.session_state["auction_analyst_report"] = saved_auction
                    except ScoutReportError as exc:
                        st.error(str(exc))
                    except Exception:
                        st.error("The auction report could not be completed. Your statistics remain available.")
            if saved_auction and saved_auction["fingerprint"] != auction_fingerprint:
                st.info("The saved auction report belongs to a different year, evidence or settings. Generate a matching report.")
            elif saved_auction:
                auction_report = saved_auction["report"]
                fact_lookup = {fact["id"]: fact for fact in auction_packet["facts"]}
                for section, label in [
                    ("observations", "Historical observations"),
                    ("interpretations", "Tentative market interpretations"),
                ]:
                    st.markdown(f"**{label}**")
                    if not auction_report[section]:
                        st.caption("No supported interpretation was returned.")
                    for finding in auction_report[section]:
                        st.write(finding["text"])
                        st.caption(" · ".join(
                            f"[{fid}] {fact_lookup[fid]['metric']}: "
                            f"{fact_lookup[fid]['value']:,.2f} {fact_lookup[fid]['unit']}"
                            for fid in finding["fact_ids"]
                        ))
                st.markdown("**Limitations**")
                for limitation in dict.fromkeys(auction_packet["limitations"] + auction_report["limitations"]):
                    st.warning(limitation)
                if auction_report["next_steps"]:
                    st.markdown("**Suggested review actions**")
                    for action in auction_report["next_steps"]:
                        st.write(action)
                st.caption(
                    "AI-generated historical interpretation. Structure and citations are checked; "
                    "market value and future outcomes are not certified. "
                    "This report is saved only in this browser session."
                )
