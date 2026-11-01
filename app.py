"""Cricket analytics with evidence-bound DeepSeek specialist reports."""

import hashlib
import json
from pathlib import Path
from importlib.util import find_spec

import pandas as pd
import streamlit as st

from agent_runtime import AgentRuntimeError, load_agents

# Use one coherent local agent version, independent of cached 'agents' packages.
agent_layer_ready = False
try:
    agent_api = load_agents(Path(__file__).resolve().parent)
    # Check this UI's complete contract even if an older runtime is still cached.
    required_agent_functions = (
        "generate_player_scout_report", "scout_context_fingerprint",
        "generate_matchup_report", "matchup_context_fingerprint",
        "generate_auction_report", "auction_context_fingerprint",
        "generate_squad_report", "squad_context_fingerprint",
    )
    if any(not callable(getattr(agent_api, name, None)) for name in required_agent_functions):
        raise AgentRuntimeError("The current UI requires a newer agent release.")
except AgentRuntimeError:
    class ScoutReportError(Exception):
        """Optional agents are unavailable while statistical tools remain usable."""

    def _agent_unavailable(*args, **kwargs):
        raise ScoutReportError(
            "AI components are updating or unavailable. Statistical tools remain available. "
            "Wait for deployment to finish, then reboot the dev app if this message persists."
        )

    generate_player_scout_report = scout_context_fingerprint = _agent_unavailable
    generate_matchup_report = matchup_context_fingerprint = _agent_unavailable
    generate_auction_report = auction_context_fingerprint = _agent_unavailable
    generate_squad_report = squad_context_fingerprint = _agent_unavailable
else:
    ScoutReportError = agent_api.ScoutReportError
    generate_player_scout_report = agent_api.generate_player_scout_report
    scout_context_fingerprint = agent_api.scout_context_fingerprint
    generate_matchup_report = agent_api.generate_matchup_report
    matchup_context_fingerprint = agent_api.matchup_context_fingerprint
    generate_auction_report = agent_api.generate_auction_report
    auction_context_fingerprint = agent_api.auction_context_fingerprint
    generate_squad_report = agent_api.generate_squad_report
    squad_context_fingerprint = agent_api.squad_context_fingerprint
    agent_layer_ready = True

from data_loader import (
    load_auction,
    load_deliveries, load_clean_auction, load_auction_player_links, load_season_impact,
    load_match_players,
    load_matches,
    load_player_registry,
    load_squads,
)

from moneyball import (phase_batting_metrics, latest_auction_impact,
                       append_phase_evidence, append_impact_evidence)


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
        "No peer benchmark is included in this packet.",
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


def prepare_squad_snapshot(records, columns, expected_roles):
    """Count source rows and explicit flags without merging placeholder IDs."""
    def text_field(key):
        column = columns[key]
        values = records[column] if column in records else pd.Series(pd.NA, index=records.index, dtype="string")
        values = values.astype("string").str.strip()
        return values.mask(values.isna() | values.eq("").fillna(False), "Not recorded")

    def flag_field(key, yes, no):
        column = columns[key]
        values = pd.to_numeric(records[column], errors="coerce") if column in records else pd.Series(float("nan"), index=records.index)
        labels = pd.Series("Unknown", index=records.index, dtype="string")
        labels.loc[values.eq(1).fillna(False)] = yes
        labels.loc[values.eq(0).fillna(False)] = no
        return labels

    names = text_field("player")
    roles = text_field("role")
    origins = flag_field("overseas", "Overseas", "Domestic")
    keepers = flag_field("keeper", "Yes", "No")
    role_labels = list(dict.fromkeys([*expected_roles, *sorted(roles.unique())]))
    role_counts = {label: int(roles.eq(label).sum()) for label in role_labels}
    origin_counts = {label: int(origins.eq(label).sum()) for label in ["Domestic", "Overseas", "Unknown"]}
    keeper_counts = {label: int(keepers.eq(label).sum()) for label in ["Yes", "No", "Unknown"]}
    known_names = names.loc[names.ne("Not recorded")]
    registry_ids = text_field("registry")
    summary = {
        "listed_players": len(records), "distinct_listed_names": int(known_names.nunique()),
        "missing_player_names": int(names.eq("Not recorded").sum()),
        "duplicate_name_entries": int(known_names.duplicated().sum()),
        "unclassified_role_entries": int((~roles.isin(expected_roles)).sum()),
        "nonstandard_or_missing_registry_entries": int((~registry_ids.str.fullmatch(r"[0-9a-f]{8}", case=False).fillna(False)).sum()),
    }
    display = pd.DataFrame({
        "Player": names, "Primary role": roles, "Origin (flag)": origins,
        "Nationality": text_field("nationality"), "Wicketkeeper flag": keepers,
        "Designation": text_field("designation"), "Registry ID": registry_ids,
    })
    return display.reset_index(drop=True), summary, role_counts, origin_counts, keeper_counts


def build_squad_evidence(records, franchise_id, franchise_name, columns, expected_roles):
    """Build an auditable squad composition packet from the selected supplied pool."""
    display, summary, role_counts, origins, keepers = prepare_squad_snapshot(records, columns, expected_roles)
    facts = []
    def add(label, value, unit):
        fid = f"F{len(facts) + 1}"
        facts.append({"id": fid, "metric": label, "value": int(value), "unit": unit})
        return fid
    add("Listed squad entries", summary["listed_players"], "source rows, not certified registered players")
    add("Distinct listed player names", summary["distinct_listed_names"], "source names, not verified unique identities")
    add("Entries with missing player names", summary["missing_player_names"], "source rows")
    add("Additional entries with repeated player names", summary["duplicate_name_entries"], "source rows requiring identity review")
    role_rows = [{"role": role, "count": count, "fact_id": add(
        f"Entries with primary role label {role}", count, "source rows; zero does not prove absent capability"
    )} for role, count in role_counts.items()]
    origin_rows = [{"origin": label, "count": count, "fact_id": add(
        f"Entries classified {label} by overseas flag", count, "source rows; nationality is not used to infer origin"
    )} for label, count in origins.items()]
    keeper_rows = [{"flag": label, "count": count, "fact_id": add(
        f"Entries with wicketkeeper flag {label}", count, "source rows; overlaps primary roles"
    )} for label, count in keepers.items()]
    limitations = [
        "This supplied pool is not a verified current registered squad; the CSV provides no snapshot date.",
        "The pool may contain outgoing players and replacements; current registration, eligibility and availability need verification.",
        "Primary role labels describe metadata, not verified capability, quality, batting position or bowling workload.",
        "Zero entries with a primary role label do not prove that no listed player can perform that role.",
        "Domestic and overseas counts use only explicit source flags; unknown flags are not inferred from nationality or names.",
        "Wicketkeeper flags are an overlapping view and must not be added to primary role totals.",
        "Pace/spin specialisms, current form, fitness, budgets and match-day conditions are not supplied.",
        "These counts do not certify competition quotas, a legal playing XI or future performance.",
        "Names and registry IDs may be incomplete or placeholders; source entries are preserved rather than merged automatically.",
    ]
    if summary["missing_player_names"] or summary["duplicate_name_entries"]:
        limitations.append("Missing or repeated player names require identity review before interpreting a unique player count.")
    if summary["unclassified_role_entries"]:
        limitations.append("Some primary role labels are missing or outside the configured expected set; role coverage needs metadata review.")
    if origins["Unknown"] or keepers["Unknown"]:
        limitations.append("Some origin or wicketkeeper flags are unknown; metadata coverage is incomplete.")
    source_hash = hashlib.sha256(
        pd.util.hash_pandas_object(records, index=True).values.tobytes()
        + json.dumps(list(records.columns)).encode("utf-8")
    ).hexdigest()
    return {
        "task": "squad_analysis", "franchise": {"id": str(franchise_id), "name": str(franchise_name)},
        "scope": {"source": "squads.csv (loaded selected franchise rows)",
                  "roster_status": "Supplied snapshot; current registered squad not certified", "snapshot_date": None},
        "summary": summary, "role_counts": role_rows, "origin_counts": origin_rows,
        "wicketkeeper_flags": keeper_rows,
        "roster": json.loads(display.drop(columns="Registry ID").to_json(orient="records")),
        "facts": facts, "limitations": limitations, "source_fingerprint": source_hash,
    }


def describe_system_status(datasets, agent_layer_ready):
    """Inspect local readiness without a provider request or returning secrets."""
    rows = []
    for name, frame in datasets.items():
        loaded = isinstance(frame, pd.DataFrame)
        rows.append({"Dataset": name, "Rows": len(frame) if loaded else 0,
                     "Status": "Loaded" if loaded and not frame.empty else "Empty" if loaded else "Unavailable"})
    datasets_ready = bool(rows) and all(row["Status"] == "Loaded" for row in rows)
    try:
        sdk_discoverable = find_spec("openai") is not None
    except (ImportError, ValueError):
        sdk_discoverable = False
    credentials_present = False
    model_valid = True
    settings_readable = True
    try:
        key = st.secrets.get("DEEPSEEK_API_KEY", "")
        credentials_present = isinstance(key, str) and bool(key.strip())
        model = st.secrets.get("DEEPSEEK_MODEL", "deepseek-flash")
        model_valid = isinstance(model, str) and bool(model.strip()) and len(model) <= 100
    except FileNotFoundError:
        pass  # Missing secrets are normal for local statistical use.
    except Exception:
        settings_readable = False
        model_valid = False
    return {
        "datasets_ready": datasets_ready,
        "loaded_datasets": sum(row["Status"] == "Loaded" for row in rows),
        "dataset_count": len(rows), "dataset_rows": rows,
        "agent_layer_ready": bool(agent_layer_ready), "sdk_discoverable": sdk_discoverable,
        "credentials_present": credentials_present, "model_configuration_valid": model_valid,
        "settings_readable": settings_readable,
        "ai_configuration_ready": bool(agent_layer_ready and sdk_discoverable
                                       and credentials_present and model_valid and settings_readable),
    }


st.set_page_config(
    page_title="IPL Intelligence 360°",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="auto",
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
            "Squad Analysis",
            "Auction Trends",
        ],
    )
    st.divider()
    st.caption("Phase 3 · Evidence-first specialists + Moneyball routing")


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
    home_status = describe_system_status(
        {"Match archive": matches, "Player-match records": match_players,
         "Squad pool": squads, "Auction records": auction, "Player registry": player_registry},
        agent_layer_ready,
    )
    row_counts = {row["Dataset"]: row["Rows"] for row in home_status["dataset_rows"]}

    st.title("IPL Intelligence 360°")
    st.caption("FRANCHISE RESEARCH · SCOUTING EVIDENCE · DECISION SUPPORT")
    st.markdown(
        "An **empirical, hybrid multi-agent AI scouting platform** combining deterministic "
        "analytics with specialist reasoning. Explore player evidence, team matchups, "
        "historical auction records and supplied squad composition, then inspect the "
        "facts, interpretations and limitations behind each report."
    )
    columns = st.columns(3)
    columns[0].metric("Archive matches", f"{row_counts['Match archive']:,}")
    columns[1].metric("Player-match records", f"{row_counts['Player-match records']:,}")
    columns[2].metric("Registry identities", f"{row_counts['Player registry']:,}")
    st.caption(
        f"Also loaded: {row_counts['Auction records']:,} historical auction records and "
        f"{row_counts['Squad pool']:,} supplied squad entries. "
        "Source coverage varies; current registration and monetary units require verification."
    )

    st.divider()
    st.subheader("Hybrid 6-Agent Architecture")
    st.write(
        "Six logical roles support one evidence-led workflow: four DeepSeek specialists "
        "and two deterministic Python control roles."
    )
    specialists, controls = st.columns([1.15, 1])
    with specialists:
        with st.container(border=True):
            st.markdown("**LLM specialists · interpretation**")
            for title, description in [
                ("Player Scout", "Interprets selected player statistics and recent evidence, with explicit identity and scope."),
                ("Matchup Analyst", "Explains historical head-to-head and venue patterns, with encounter counts and caveats."),
                ("Auction Analyst", "Reviews recorded buys, franchise totals and category distributions without asserting current value."),
                ("Squad Analyst", "Reviews listed role and origin coverage while keeping roster and capability uncertainty visible."),
            ]:
                st.markdown(f"**{title}**")
                st.caption(description)
    with controls:
        with st.container(border=True):
            st.markdown("**Python control roles · coordination and checks**")
            st.markdown("**Research Coordinator**")
            st.caption(
                "Workspace and selection-driven context routing: chooses the requested specialist "
                "and assembles the relevant filtered evidence."
            )
            st.markdown("**Evidence Reviewer**")
            st.caption(
                "Validates response structure, known fact IDs and output bounds. "
                "Python supplies the cited numerical values and preserves source limitations."
            )
            st.info(
                "The coordinator and reviewer are Python logic. A report requests its selected "
                "specialist; all six roles do not trigger separate LLM calls."
            )

    st.subheader("Empirical Evidence First")
    left, right = st.columns(2)
    with left:
        st.markdown("**Calculate before interpreting**")
        st.write(
            "Pandas filters the source records and computes totals, rates and distributions. "
            "DeepSeek receives a bounded JSON evidence packet."
        )
        st.markdown("**Keep the decision context attached**")
        st.write(
            "Reports retain the selected identity, teams, year or venue, source fingerprints "
            "and fact references. Changing the context makes the saved report stale."
        )
    with right:
        st.markdown("**Guard against unsupported claims**")
        st.write(
            "Prompts restrict reasoning to supplied evidence. JSON and citation checks reject "
            "malformed reports and unknown fact references. Observations stay separate from tentative interpretations."
        )
        st.markdown("**Expose limits before decisions**")
        st.write(
            "Coverage gaps, unknown metadata, unverified currency and sample limitations remain "
            "visible. Statistical tools remain usable when the optional AI layer is unavailable."
        )
    st.caption(
        "Validation reduces some unsupported outputs; it does not guarantee hallucination-free "
        "prose, prove that every interpretation follows from its citations, or establish predictive "
        "or tactical advantage. Human review remains part of the workflow."
    )

    st.subheader("Technology & Methodology")
    for box, title, detail in zip(
        st.columns(4), ["Python", "Streamlit", "Pandas", "DeepSeek API"],
        ["Routing, validation and reproducible evidence.",
         "Interactive workspaces and session-bound reports.",
         "Cached ingestion and deterministic calculations.",
         "Structured specialist interpretation through an OpenAI-compatible client."],
    ):
        box.markdown(f"**{title}**")
        box.caption(detail)
    with st.expander("How to use the platform"):
        st.markdown(
            "1. Choose a workspace from the sidebar and confirm the selection.\n"
            "2. Inspect the calculated statistics, source rows and evidence packet.\n"
            "3. Generate a report, review its citations and limitations, then decide what needs further investigation."
        )
        st.caption("Selecting filters does not make a provider request. Report generation is an explicit action.")

    st.divider()
    st.subheader("System Status")
    if home_status["datasets_ready"]:
        st.success("System Online: all five empirical datasets are loaded through cached data loaders.")
    else:
        st.warning(
            f"Data readiness: {home_status['loaded_datasets']} of {home_status['dataset_count']} "
            "datasets contain records. Review dataset availability below."
        )
    if home_status["ai_configuration_ready"]:
        st.success("AI configuration ready: specialist functions, SDK package and credentials are present.")
    else:
        missing = []
        if not home_status["agent_layer_ready"]:
            missing.append("agent components are unavailable or updating")
        if not home_status["sdk_discoverable"]:
            missing.append("the optional OpenAI-compatible SDK package is not discoverable")
        if not home_status["settings_readable"]:
            missing.append("Streamlit Secrets could not be read")
        elif not home_status["credentials_present"]:
            missing.append("the DeepSeek API key is not configured")
        if not home_status["model_configuration_valid"]:
            missing.append("the DeepSeek model setting needs review")
        st.info("AI configuration needs attention: " + "; ".join(missing) + ". Statistical tools remain available.")
    st.caption(
        "Status checks inspect local configuration only. API authentication, endpoint availability "
        "and report quality are not verified here. Home makes no paid provider requests."
    )
    with st.expander("Dataset availability"):
        st.dataframe(pd.DataFrame(home_status["dataset_rows"]), hide_index=True, width="stretch")


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
                    st.subheader("IPL batting phases · delivery evidence")
                    phase_result = None
                    phase_issue = None
                    if scope not in ["IPL", "All supplied competitions"]:
                        phase_issue = "IPL phase metrics do not apply to the selected non-IPL competition."
                    else:
                        try:
                            with st.spinner("Preparing cached IPL phase metrics..."):
                                phase_result = phase_batting_metrics(load_deliveries(), selected_player_id)
                        except (OSError, ValueError) as exc:
                            phase_issue = str(exc)
                    if phase_result is not None:
                        phase_table = pd.DataFrame(phase_result["rows"]).rename(columns={
                            "phase": "Phase", "overs_zero_based": "Overs (zero-based)",
                            "runs": "Batter runs", "balls_faced": "Balls faced",
                            "batter_dot_balls": "Batter dot balls", "strike_rate": "Strike rate",
                            "dot_ball_percentage": "Dot ball %",
                        })
                        st.dataframe(phase_table, hide_index=True, width="stretch")
                        st.caption(
                            "IPL delivery archive only; super overs excluded. Powerplay: overs 0–5; "
                            "Middle: 6–15; Death: 16–19. Strike rate = 100 × batter runs / balls faced. "
                            "Batter dot % = 100 × counted balls with zero batter runs / balls faced. "
                            "Wides excluded; source-counted no-balls included. Byes/leg-byes may be batter dots. "
                            "No exposure gives N/A rates. Fixed bands are not rain-adjusted powerplays."
                        )
                        st.caption(f"Phase evidence window: {phase_result['since'] or 'No recorded balls'} "
                                   f"to {phase_result['through_inclusive'] or 'N/A'}.")
                    else:
                        st.info(phase_issue or "IPL phase metrics unavailable.")
                    scout_packet = append_phase_evidence(scout_packet, phase_result, phase_issue)
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


elif selected_module == "Squad Analysis":
    # EDIT THESE MAPPINGS when using a different squad source.
    FRANCHISE_COLUMN = "franchise_id"
    FRANCHISE_NAME_COLUMN = "team_name"
    PLAYER_COLUMN = "player_name"
    ROLE_COLUMN = "role"
    OVERSEAS_COLUMN = "is_overseas"
    KEEPER_COLUMN = "is_wicketkeeper"
    NATIONALITY_COLUMN = "nationality"
    DESIGNATION_COLUMN = "designation"
    REGISTRY_COLUMN = "cricsheet_id"
    EXPECTED_ROLE_LABELS = ["Batter", "Bowler", "All Rounder", "Wicket Keeper"]

    st.title("Squad Analysis")
    st.caption(
        "Review the supplied franchise squad snapshot. Current registration, availability "
        "and roster completeness are not certified; the CSV has no snapshot date."
    )
    with st.expander("Inspect squad headers and column mappings"):
        st.write(squads.columns.tolist())
        st.caption("Mappings and expected primary role labels are defined at the top of this workspace.")
    required_columns = {FRANCHISE_COLUMN, PLAYER_COLUMN}
    if not required_columns.issubset(squads.columns):
        st.warning("Map the franchise and player-name columns above to enable squad analysis.")
    else:
        franchise_values = squads[FRANCHISE_COLUMN].dropna().astype(str)
        franchises = sorted(franchise_values.loc[franchise_values.str.strip().ne("")].unique())
        if not franchises:
            st.info("No franchises are available in the supplied squad dataset.")
        else:
            franchise_names = {}
            for franchise in franchises:
                rows = squads.loc[squads[FRANCHISE_COLUMN].astype(str).eq(franchise)]
                names = rows[FRANCHISE_NAME_COLUMN].dropna().astype(str).unique() if FRANCHISE_NAME_COLUMN in rows else []
                franchise_names[franchise] = names[0] if len(names) == 1 else franchise
            selected_franchise = st.selectbox(
                "Franchise", franchises,
                index=franchises.index("RCB") if "RCB" in franchises else 0,
                format_func=lambda code: f"{code} · {franchise_names[code]}", key="squad_franchise",
            )
            squad_records = squads.loc[squads[FRANCHISE_COLUMN].astype(str).eq(selected_franchise)].copy()
            squad_columns = {
                "player": PLAYER_COLUMN, "role": ROLE_COLUMN, "overseas": OVERSEAS_COLUMN,
                "keeper": KEEPER_COLUMN, "nationality": NATIONALITY_COLUMN,
                "designation": DESIGNATION_COLUMN, "registry": REGISTRY_COLUMN,
            }
            roster, summary, role_counts, origin_counts, keeper_counts = prepare_squad_snapshot(
                squad_records, squad_columns, EXPECTED_ROLE_LABELS
            )
            st.subheader("Supplied squad snapshot")
            boxes = st.columns(4)
            boxes[0].metric("Listed players (rows)", f"{summary['listed_players']:,}")
            boxes[1].metric("Domestic (flag)", f"{origin_counts['Domestic']:,}")
            boxes[2].metric("Overseas (flag)", f"{origin_counts['Overseas']:,}")
            boxes[3].metric("Unknown origin", f"{origin_counts['Unknown']:,}")
            st.dataframe(roster, hide_index=True, width="stretch")
            st.caption(
                "Source rows are preserved. Repeated placeholder registry IDs are not merged. "
                "These are listed entries, not a certified count of currently registered players."
            )
            if summary["duplicate_name_entries"] or summary["missing_player_names"]:
                st.warning("Some names are missing or repeated; verify identities before counting distinct players.")
            if summary["unclassified_role_entries"] or origin_counts["Unknown"] or keeper_counts["Unknown"]:
                st.warning("Some role or flag metadata is unknown or unclassified. Review the source before drawing balance conclusions.")
            left, right = st.columns(2)
            with left:
                st.markdown("**Primary role counts**")
                st.dataframe(pd.DataFrame({"Primary role": list(role_counts), "Entries": list(role_counts.values())}), hide_index=True, width="stretch")
            with right:
                st.markdown("**Origin counts from source flags**")
                st.dataframe(pd.DataFrame({"Origin": list(origin_counts), "Entries": list(origin_counts.values())}), hide_index=True, width="stretch")
            st.caption(
                "Origin uses is_overseas: zero means Domestic, one means Overseas, other values mean Unknown. "
                "Role counts use primary labels; zero does not establish absent capability. "
                "Wicketkeeper flags overlap primary roles."
            )

            st.divider()
            st.subheader("Squad Analyst · DeepSeek")
            st.caption("Generate a cited review of the selected snapshot. Only clicking the button sends its evidence to DeepSeek.")
            squad_packet = build_squad_evidence(
                squad_records, selected_franchise, franchise_names[selected_franchise],
                squad_columns, EXPECTED_ROLE_LABELS,
            )
            with st.expander("Inspect evidence sent to the Squad Analyst"):
                st.json(squad_packet)
            try:
                squad_fingerprint = squad_context_fingerprint(squad_packet)
            except ScoutReportError as exc:
                st.warning(str(exc))
            else:
                saved_squad = st.session_state.get("squad_analyst_report")
                if st.button("Generate Squad Report", disabled=squad_records.empty):
                    if saved_squad and saved_squad["fingerprint"] == squad_fingerprint:
                        st.info("Using the saved squad report for this exact evidence and model.")
                    else:
                        st.session_state.pop("squad_analyst_report", None)
                        saved_squad = None
                        try:
                            with st.spinner("Analysing squad..."):
                                squad_report = generate_squad_report(squad_packet)
                            if squad_report["_provenance"]["context_fingerprint"] != squad_fingerprint:
                                raise ScoutReportError("The squad context changed. Generate a new report.")
                            saved_squad = {"fingerprint": squad_fingerprint, "report": squad_report}
                            st.session_state["squad_analyst_report"] = saved_squad
                        except ScoutReportError as exc:
                            st.error(str(exc))
                        except Exception:
                            st.error("The squad report could not be completed. Your squad table remains available.")
                if saved_squad and saved_squad["fingerprint"] != squad_fingerprint:
                    st.info("The saved squad report belongs to a different franchise, evidence or settings. Generate a matching report.")
                elif saved_squad:
                    squad_report = saved_squad["report"]
                    facts = {fact["id"]: fact for fact in squad_packet["facts"]}
                    for section, label in [("observations", "Squad composition observations"),
                                           ("interpretations", "Tentative tactical interpretations")]:
                        st.markdown(f"**{label}**")
                        if not squad_report[section]:
                            st.caption("No supported interpretation was returned.")
                        for finding in squad_report[section]:
                            st.write(finding["text"])
                            st.caption(" · ".join(
                                f"[{fid}] {facts[fid]['metric']}: {facts[fid]['value']:,} {facts[fid]['unit']}"
                                for fid in finding["fact_ids"]
                            ))
                    st.markdown("**Limitations**")
                    for limitation in dict.fromkeys(squad_packet["limitations"] + squad_report["limitations"]):
                        st.warning(limitation)
                    if squad_report["next_steps"]:
                        st.markdown("**Next Steps**")
                        for action in squad_report["next_steps"]:
                            st.write(action)
                    st.caption(
                        "AI-generated snapshot interpretation. Structure and citations are checked; "
                        "current eligibility, tactical balance and future performance are not certified. "
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
    st.caption("Legacy chart source: auction.csv. The separate Moneyball section below uses cleaned 2013–2026 sale records.")
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
        st.subheader("Moneyball · latest auction price and same-season impact")
        st.caption(
            "This assessment uses the new cleaned auction file independently of the legacy charts above. "
            "All Time selects each exact-ID player's latest supplied sale; a single season restricts sales to that season. "
            "Each price is divided only by that same IPL season's output. This is retrospective, not a pre-auction forecast."
        )
        impact_table = impact_summary = None
        impact_issue = None
        try:
            clean_prices = load_clean_auction()
            clean_years = pd.to_numeric(clean_prices["season_year"], errors="coerce").dropna()
            clean_years = sorted(clean_years.loc[clean_years.mod(1).eq(0)].astype(int).unique(), reverse=True)
            impact_year = st.selectbox("Moneyball sale season", ["All Time", *map(str, clean_years)], key="moneyball_year")
            with st.spinner("Preparing cached season impact..."):
                impact_table, impact_summary = latest_auction_impact(
                    clean_prices, load_auction_player_links(), load_season_impact(), impact_year,
                )
            view = impact_table.rename(columns={
                "season_year": "Sale / performance season", "player_name": "Player", "team_id": "Purchasing team",
                "winning_bid_currency": "Currency", "price": "Latest price (native units)",
                "runs": "Same-season runs", "wickets": "Same-season bowler wickets",
                "cost_per_run": "Cost per run", "cost_per_wicket": "Cost per wicket",
                "performance_available": "Observed in season roster",
            })
            display_columns = ["Player", "Sale / performance season", "Currency", "Latest price (native units)",
                               "Cost per run", "Cost per wicket", "Same-season runs", "Same-season bowler wickets",
                               "Purchasing team", "Observed in season roster"]
            st.dataframe(view[display_columns], width="stretch", hide_index=True,
                         column_config={"Sale / performance season": st.column_config.NumberColumn("Season", format="%d"),
                                        "Latest price (native units)": st.column_config.NumberColumn("Native price"),
                                        "Cost per run": st.column_config.NumberColumn("Cost/run", format="%.2f"),
                                        "Cost per wicket": st.column_config.NumberColumn("Cost/wicket", format="%.2f")})
            st.download_button("Download full Moneyball table", view.to_csv(index=False).encode("utf-8"),
                               file_name=f"moneyball_{impact_year.replace(' ', '_')}.csv", mime="text/csv")
            st.caption(
                f"{impact_summary['matched_price_rows']:,} exact-ID prices; "
                f"{impact_summary['excluded_uncertain_links']:,} latest source-name sale rows excluded for uncertain links; "
                f"{impact_summary['excluded_superseded_alias_sales']:,} older alias sale rows superseded; "
                f"{impact_summary['excluded_ambiguous_sales']:,} ambiguous sale rows excluded; "
                f"{impact_summary['excluded_invalid_prices']:,} invalid prices excluded; "
                f"{impact_summary['missing_same_season_performance']:,} prices have no observed same-season roster. "
                "INR and USD are native currencies and remain separate; rows are sorted within currency, not across currencies. "
                "No inflation adjustment or currency conversion. Missing output or a zero denominator gives N/A. "
                "Price/output covers all observed IPL teams in that season; it does not attribute output to the purchasing team alone. "
                "A roster entry can include a substitute who never batted or bowled. "
                "Identity matches and prices are not independently certified."
            )
        except (OSError, ValueError, KeyError) as exc:
            impact_issue = str(exc)
            st.info("Moneyball metrics unavailable: " + impact_issue)

        st.divider()
        st.subheader("Auction Analyst · DeepSeek")
        st.caption(
            "Interpret the legacy auction selection and the separately scoped Moneyball evidence below. "
            "Only clicking the button sends this evidence packet to DeepSeek."
        )
        auction_packet = build_auction_evidence(
            scoped_auction, selected_year, PLAYER_COLUMN, TEAM_COLUMN,
            CATEGORY_COLUMNS, AMOUNT_UNIT_LABEL,
        )
        auction_packet = append_impact_evidence(auction_packet, impact_table, impact_summary, impact_issue)
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
