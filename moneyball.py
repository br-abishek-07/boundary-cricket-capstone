"""Deterministic Moneyball calculations. No network or LLM calls."""

import hashlib
import json

import pandas as pd

PHASES = (("Powerplay", 0, 5), ("Middle", 6, 15), ("Death", 16, 19))


def frame_fingerprint(frame):
    """Include all loaded source rows, columns and the loader's file digest."""
    return hashlib.sha256(
        pd.util.hash_pandas_object(frame, index=True).values.tobytes()
        + json.dumps(list(frame.columns)).encode()
        + str(frame.attrs.get("source_sha256", "")).encode()
    ).hexdigest()


def _require(frame, columns):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError("Missing Moneyball columns: " + ", ".join(sorted(missing)))


def _numbers(frame, columns):
    result = frame.copy()
    for column in columns:
        values = pd.to_numeric(result[column], errors="coerce")
        if not (values.notna() & values.ge(0) & values.lt(float("inf")) & values.mod(1).eq(0)).all():
            raise ValueError(f"Invalid or missing nonnegative integer in {column}; metrics withheld.")
        result[column] = values
    return result


def phase_batting_metrics(deliveries, player_id):
    """Batter runs / balls faced, excluding wides, including source-counted no-balls.

    A batter dot means zero BATTER runs on a counted ball faced. Byes/leg-byes
    can therefore be batter dots; this is not the team's scoreless-ball rate.
    User-defined fixed over bands are not rain-adjusted powerplay regulations.
    """
    required = ["delivery_id", "match_date", "striker_id", "is_super_over",
                "over_number_zero_based", "is_ball_faced_by_batter", "batter_runs"]
    _require(deliveries, required)
    rows = deliveries.loc[deliveries.striker_id.astype("string").eq(str(player_id))].copy()
    rows = _numbers(rows, ["is_super_over", "over_number_zero_based", "is_ball_faced_by_batter", "batter_runs"])
    if not rows.is_super_over.isin([0, 1]).all() or not rows.is_ball_faced_by_batter.isin([0, 1]).all():
        raise ValueError("Invalid delivery flags; phase metrics withheld.")
    if rows.delivery_id.isna().any() or rows.delivery_id.duplicated().any():
        raise ValueError("Missing or duplicate delivery IDs; phase metrics withheld.")
    rows = rows.loc[rows.is_super_over.eq(0)]
    if not rows.over_number_zero_based.between(0, 19).all():
        raise ValueError("Regular over outside the requested phase bands; metrics withheld.")
    dates = pd.to_datetime(rows.match_date, errors="coerce").dropna()
    result = []
    for phase, first, last in PHASES:
        group = rows.loc[rows.over_number_zero_based.between(first, last)]
        # Numerator is all batter runs in the phase; denominator is balls faced.
        runs = int(group.batter_runs.sum())
        faced = group.loc[group.is_ball_faced_by_batter.eq(1)]
        balls = len(faced)
        dots = int(faced.batter_runs.eq(0).sum())
        result.append({"phase": phase, "overs_zero_based": [first, last],
                       "runs": runs, "balls_faced": balls, "batter_dot_balls": dots,
                       "strike_rate": 100 * runs / balls if balls else None,
                       "dot_ball_percentage": 100 * dots / balls if balls else None})
    return {"competition": "IPL", "super_overs_excluded": True,
            "since": dates.min().date().isoformat() if len(dates) else None,
            "through_inclusive": dates.max().date().isoformat() if len(dates) else None,
            "rows": result, "source_fingerprint": frame_fingerprint(rows[required])}


def aggregate_season_impact(deliveries, wickets, rosters):
    """Observed IPL player-season runs and bowler wickets, never all dismissals.

    Roster membership establishes observed participation for zero-output players.
    A player absent from the season's rosters has unknown output, not zero output.
    """
    _require(deliveries, ["delivery_id", "match_id", "season_year", "striker_id", "bowler_id", "batter_runs", "is_super_over"])
    _require(wickets, ["wicket_id", "delivery_id", "is_super_over", "credited_to_bowler"])
    _require(rosters, ["match_id", "season_year", "player_id"])
    d = _numbers(deliveries, ["season_year", "batter_runs", "is_super_over"])
    w = _numbers(wickets, ["credited_to_bowler", "is_super_over"])
    r = _numbers(rosters, ["season_year"])
    if d.delivery_id.isna().any() or d.delivery_id.duplicated().any() or w.wicket_id.isna().any() or w.wicket_id.duplicated().any():
        raise ValueError("Duplicate or missing event IDs; impact calculation withheld.")
    if not d.is_super_over.isin([0, 1]).all() or not w.is_super_over.isin([0, 1]).all() or not w.credited_to_bowler.isin([0, 1]).all():
        raise ValueError("Invalid wicket or super-over flags; impact calculation withheld.")
    w = w.merge(d[["delivery_id", "season_year", "bowler_id", "is_super_over"]], on="delivery_id",
                how="left", validate="many_to_one", suffixes=("", "_delivery"))
    if w.bowler_id.isna().any() or not w.is_super_over.eq(w.is_super_over_delivery).all():
        raise ValueError("Wicket foreign key or super-over mismatch; impact calculation withheld.")
    regular = d.loc[d.is_super_over.eq(0)]
    runs = regular.groupby(["season_year", "striker_id"]).batter_runs.sum().rename("runs")
    runs.index.names = ["season_year", "player_id"]
    credits = w.loc[w.is_super_over.eq(0) & w.credited_to_bowler.eq(1)]
    counts = credits.groupby(["season_year", "bowler_id"]).size().rename("wickets")
    counts.index.names = ["season_year", "player_id"]
    result = r[["season_year", "player_id"]].drop_duplicates().set_index(["season_year", "player_id"])
    if not runs.index.isin(result.index).all() or not counts.index.isin(result.index).all():
        raise ValueError("Performance ID missing from same-season roster; metrics withheld.")
    result = result.join(runs).join(counts).fillna({"runs": 0, "wickets": 0}).reset_index()
    result[["runs", "wickets"]] = result[["runs", "wickets"]].astype(int)
    result.attrs["source_fingerprint"] = hashlib.sha256("|".join(
        frame_fingerprint(f) for f in [deliveries, wickets, rosters]).encode()).hexdigest()
    return result


def latest_auction_impact(auction, links, impact, selected_year="All Time"):
    """Latest sold transaction per exact person ID within the selected auction scope.

    All Time means each person's latest supplied sale, paired ONLY with that
    sale's IPL season output. A later uncertain sale suppresses an older exact
    match for that same normalized source name. No price extrapolation, FX,
    inflation adjustment, or fuzzy identity matching is performed.
    """
    _require(auction, ["auction_record_id", "season_year", "player_name", "team_id", "auction_status",
                       "winning_bid_native", "winning_bid_currency"])
    _require(links, ["auction_record_id", "season_year", "team_id", "cricsheet_person_id",
                     "join_method", "join_usable", "review_needed"])
    _require(impact, ["season_year", "player_id", "runs", "wickets"])
    if auction.auction_record_id.isna().any() or links.auction_record_id.isna().any() or auction.auction_record_id.duplicated().any() or links.auction_record_id.duplicated().any():
        raise ValueError("Auction or identity crosswalk has duplicate transaction IDs.")
    a = _numbers(auction, ["season_year"])
    if selected_year != "All Time":
        a = a.loc[a.season_year.eq(int(selected_year))].copy()
    a = a.loc[a.auction_status.astype("string").str.casefold().eq("sold")].copy()
    a["_name_key"] = a.player_name.astype("string").str.casefold().str.replace(r"\s+", " ", regex=True).str.strip()
    # Discard older source-name sales BEFORE exact-link filtering; do not backfill.
    a = a.loc[a.season_year.eq(a.groupby("_name_key").season_year.transform("max"))]
    a = a.merge(links, on="auction_record_id", how="left", suffixes=("", "_link"), validate="one_to_one")
    exact = (a.join_method.eq("exact_alias") & pd.to_numeric(a.join_usable, errors="coerce").eq(1)
             & pd.to_numeric(a.review_needed, errors="coerce").eq(0)
             & a.cricsheet_person_id.notna() & a.season_year.eq(pd.to_numeric(a.season_year_link, errors="coerce"))
             & a.team_id.eq(a.team_id_link))
    excluded_links = int((~exact).sum())
    usable = a.loc[exact].copy()
    latest_id_season = usable.season_year.eq(usable.groupby("cricsheet_person_id").season_year.transform("max"))
    superseded_alias_count = int((~latest_id_season).sum())
    usable = usable.loc[latest_id_season]
    ambiguous = usable.cricsheet_person_id.duplicated(keep=False)
    ambiguous_count = int(ambiguous.sum())
    usable = usable.loc[~ambiguous].copy()  # no arbitrary tie-breaking between same-season sales
    price = pd.to_numeric(usable.winning_bid_native, errors="coerce")
    valid_price = price.notna() & price.gt(0) & price.lt(float("inf")) & usable.winning_bid_currency.isin(["INR", "USD"])
    invalid_price_count = int((~valid_price).sum())
    usable = usable.loc[valid_price].copy()
    usable["price"] = price.loc[valid_price]
    usable = usable.merge(impact, left_on=["season_year", "cricsheet_person_id"],
                          right_on=["season_year", "player_id"], how="left", validate="one_to_one", indicator=True)
    usable["performance_available"] = usable._merge.eq("both")
    for metric, denominator in [("cost_per_run", "runs"), ("cost_per_wicket", "wickets")]:
        usable[metric] = usable.price.div(usable[denominator].where(usable[denominator].gt(0)))
        usable[metric] = usable[metric].where(usable[metric].lt(float("inf")))
    columns = ["auction_record_id", "season_year", "player_name", "team_id", "cricsheet_person_id",
               "winning_bid_currency", "price", "runs", "wickets", "cost_per_run", "cost_per_wicket", "performance_available"]
    result = usable[columns].sort_values(["winning_bid_currency", "price", "auction_record_id"], ascending=[True, False, True]).reset_index(drop=True)
    summary = {"selected_year": str(selected_year), "latest_source_name_sale_rows": len(a),
               "excluded_uncertain_links": excluded_links, "excluded_superseded_alias_sales": superseded_alias_count,
               "excluded_ambiguous_sales": ambiguous_count,
               "excluded_invalid_prices": invalid_price_count, "matched_price_rows": len(result),
               "missing_same_season_performance": int((~result.performance_available).sum())}
    digest = hashlib.sha256((frame_fingerprint(auction) + frame_fingerprint(links)
                             + str(impact.attrs.get("source_fingerprint", frame_fingerprint(impact)))).encode()).hexdigest()
    summary["source_fingerprint"] = digest
    return result, summary


def append_phase_evidence(packet, phase_result=None, issue=None):
    """Attach explicitly IPL-only phase evidence, keeping absent rates JSON null."""
    packet["limitations"] = [x for x in packet["limitations"] if x != "No peer benchmark or phase-specific scouting comparison is included in this packet."]
    packet["limitations"].extend([
        "Phase metrics use only the separate IPL delivery archive; other competitions are not included.",
        "Fixed phases are zero-based overs: Powerplay zero through five, Middle six through fifteen, Death sixteen through nineteen; rain-adjusted powerplays are not reconstructed.",
        "Batter dot percentage counts zero batter runs on counted balls faced, including byes and leg-byes; it is not team scoreless-ball percentage. Wides are excluded and source-counted no-balls remain balls faced.",
        "No peer benchmark, injury information or predictive model is supplied. Missing phase exposure gives null rates, not zero rates.",
    ])
    if phase_result is None:
        packet["phase_batting"] = {"available": False, "reason": issue or "IPL deliveries unavailable for this scope."}
        packet["limitations"].append(packet["phase_batting"]["reason"])
        return packet
    phase_result = json.loads(json.dumps(phase_result, allow_nan=False))
    for row in phase_result["rows"]:
        row["fact_ids"] = {}
        for field, unit in [("runs", "batter runs"), ("balls_faced", "balls faced"),
                            ("strike_rate", "batter runs per hundred balls faced"),
                            ("dot_ball_percentage", "percent of balls faced with zero batter runs")]:
            value = row[field]
            if value is None:
                continue
            fid = f"F{max([int(f['id'][1:]) for f in packet['facts']], default=0) + 1}"
            packet["facts"].append({"id": fid, "metric": f"IPL {row['phase']} {field}", "value": value, "unit": unit})
            row["fact_ids"][field] = fid
    packet["phase_batting"] = {"available": True, **phase_result}
    return packet


def append_impact_evidence(packet, table=None, summary=None, issue=None):
    """Bound the model context; full calculated table remains available in the UI.

    At most four high-price examples are selected within currency groups. Fact
    and byte budgets are checked without relaxing the agent validator's limits.
    """
    limitations = [
        "Moneyball prices come from a separate cleaned sold-transaction CSV; these prices have explicit native currencies but are not independently verified per transaction.",
        "Moneyball pairs each player's latest sale in its selected scope with observed output from that same IPL season, not career output. This is retrospective and must not be used as a pre-auction forecast.",
        "Cost per run and per wicket are separate descriptive ratios of the same price; do not add them or infer fair value. Retentions, trades, availability and non-IPL impact are not supplied.",
        "Only exact-alias crosswalks marked usable and not requiring review are joined by Cricsheet person ID. Heuristic and unresolved identities are excluded. Exact aliases are source matches, not independent identity certification.",
        "Native INR and USD remain separate; no currency conversion or inflation adjustment is applied. No season roster gives unknown performance; a zero denominator gives null cost, never infinity.",
        "Only a bounded sample of Moneyball rows is sent to the model; the complete calculated table is available in the app. Its scope may differ from the legacy auction charts and is explicitly stated.",
    ]
    packet["limitations"].extend(limitations)
    if table is None:
        packet["moneyball"] = {"available": False, "reason": issue or "Moneyball datasets unavailable."}
        packet["limitations"].append(packet["moneyball"]["reason"])
        return packet
    packet["moneyball"] = {"available": True, "scope": summary, "price_basis": "latest sold price per exact ID in the selected scope",
                           "performance_basis": "same IPL season; regular innings only; bowler-credited wickets",
                           "examples": [], "selection": "up to four highest prices, compared within native currency groups; not an overall value ranking"}
    # Round-robin currency groups avoids quietly removing all USD examples.
    groups = [g for _, g in table.groupby("winning_bid_currency", sort=True)]
    candidates = [g.iloc[i] for i in range(4) for g in groups if i < len(g)]
    for row in candidates:
        if len(packet["moneyball"]["examples"]) >= 4:
            break
        example = {key: str(row[key]) for key in ["auction_record_id", "player_name", "team_id", "cricsheet_person_id", "winning_bid_currency"]}
        example.update({"season_year": int(row.season_year), "performance_available": bool(row.performance_available), "fact_ids": {}})
        additions = []
        for field, unit in [("price", str(row.winning_bid_currency)), ("runs", "same-season IPL batter runs"),
                            ("wickets", "same-season IPL bowler-credited wickets"),
                            ("cost_per_run", f"{row.winning_bid_currency} per same-season IPL run"),
                            ("cost_per_wicket", f"{row.winning_bid_currency} per same-season IPL bowler wicket")]:
            value = float(row[field]) if pd.notna(row[field]) else None
            example[field] = value
            if value is not None:
                fid = f"F{max([int(f['id'][1:]) for f in packet['facts']], default=0) + len(additions) + 1}"
                additions.append({"id": fid, "metric": f"{row.player_name} · {int(row.season_year)} · {field}", "value": value, "unit": unit})
                example["fact_ids"][field] = fid
        packet["facts"].extend(additions)
        packet["moneyball"]["examples"].append(example)
        if len(packet["facts"]) > 80 or len(json.dumps(packet, ensure_ascii=False, allow_nan=False).encode()) > 24000:
            if additions:
                del packet["facts"][-len(additions):]
            packet["moneyball"]["examples"].pop()
            break
    return packet
