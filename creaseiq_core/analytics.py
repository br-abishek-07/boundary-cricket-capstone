"""Dated evidence and workload-constrained planning. Scores are explicit heuristics."""

from pathlib import Path
import json, re, unicodedata
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[1]
CORRECTIONS = {"ce794613": "T Natarajan", "2c25d4f5": "Devdutt Padikkal"}


def normal(s):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s)).lower())


def load():
    p = pd.read_csv(
        ROOT / "data/match_players.csv.gz",
        dtype={"player_id": str, "match_id": str, "season": str},
    )
    s = pd.read_csv(ROOT / "data/squads.csv")
    a = pd.read_csv(ROOT / "data/auction.csv", encoding="utf-8-sig")
    registry = json.loads((ROOT / "data/player_registry.json").read_text())["people"]
    known = s.cricsheet_id.astype(str).str.fullmatch(r"[0-9a-f]{8}")
    s.loc[~known, "cricsheet_id"] = [
        "SQUAD:" + t + ":" + normal(n)
        for t, n in zip(s.loc[~known, "franchise_id"], s.loc[~known, "player_name"])
    ]
    names = {pid: r["name"] for pid, r in registry.items()}
    aliases = {
        pid: "|".join(sorted({normal(x) for x in r["aliases"] + [r["name"]]}))
        for pid, r in registry.items()
    }
    p["alias"] = p.player
    p["player"] = p.player_id.map(names).fillna(p.player)
    p["aliases"] = p.player_id.map(aliases).fillna(p.player.map(normal))
    p["matches"] = 1
    p["last_date"] = p.date
    s["source_player_name"] = s.player_name
    s.player_name = s.cricsheet_id.map(names).fillna(s.player_name)
    s["attack_type"] = s.cricsheet_id.map(
        {pid: r.get("attack_type", "Unknown") for pid, r in registry.items()}
    ).fillna("Unknown")
    return p, s, a


def resolve(players, query):
    q = normal(query)
    if not q:
        return []
    cols = ["player_id", "player"] + (
        ["aliases"] if "aliases" in players else ["alias"]
    )
    pairs = players[cols].drop_duplicates("player_id").copy()
    names = pairs["aliases"] if "aliases" in pairs else pairs.alias.map(normal)
    exact = (
        names.map(lambda x: q in x.split("|"))
        | pairs.player.map(normal).eq(q)
        | pairs.player_id.eq(str(query).strip())
    )
    if exact.any():
        return pairs.loc[exact, ["player_id", "player"]].to_dict("records")
    hits = names.str.contains(q, regex=False) | pairs.player.map(normal).str.contains(
        q, regex=False
    )
    return pairs.loc[hits, ["player_id", "player"]].head(12).to_dict("records")


def identity_label(players, hit, until):
    rows = players[
        (players.player_id == hit["player_id"]) & (players.date < until)
    ].sort_values("date")
    competitions = (
        ", ".join(sorted(rows.competition.unique())) or "No earlier match records"
    )
    teams = " / ".join(rows.team[rows.team.ne("")].drop_duplicates().tail(2).tolist())
    return f"{hit['player']} · {hit['player_id']} · {competitions}" + (
        f" · {teams}" if teams else ""
    )


def squads_asof(squads, until):
    if pd.Timestamp(until).year != 2026:
        raise ValueError(
            "The supplied roster is a 2026 snapshot used as a research pool. XI scenarios require a cutoff within 2026; other seasons need a separately verified roster."
        )
    r = squads.copy()
    events = json.loads((ROOT / "data/squad_events.json").read_text())
    for event in events["events"]:
        if event["date"] < until:
            mask = r.player_name.eq(event["player"])
            r.loc[mask, "franchise_id"] = event["to"]
            r.loc[mask, "designation"] = "Player"
    r["selection_blocked"] = False
    r["status_note"] = (
        "Supplied pool; current registration and availability not fully verified"
    )
    r["status_source"] = ""
    status_file = ROOT / "data/roster_status.json"
    if status_file.exists():
        for notice in json.loads(status_file.read_text())["notices"]:
            if pd.Timestamp(until).year != notice["season"]:
                continue
            outgoing = r.cricsheet_id.eq(notice["player_id"])
            incoming = r.cricsheet_id.eq(notice.get("replacement_id"))
            if notice["published_date"] < until:
                r.loc[outgoing, "selection_blocked"] = True
                r.loc[outgoing, "status_note"] = (
                    notice["status"] + "; published " + notice["published_date"]
                )
                r.loc[outgoing, "status_source"] = notice["source"]
                r.loc[incoming, "status_note"] = (
                    "Replacement recorded "
                    + notice["published_date"]
                    + "; current availability still needs verification"
                )
                r.loc[incoming, "status_source"] = notice["source"]
            else:
                r.loc[incoming, "selection_blocked"] = True
                r.loc[incoming, "status_note"] = (
                    "Replacement joined after this evidence cutoff"
                )
                r.loc[incoming, "status_source"] = notice["source"]
    r["roster_source"] = (
        "Supplied 2026 research pool + dated trades and selected availability notices"
    )

    return r


def window(until, years=3):
    return (pd.Timestamp(until) - pd.DateOffset(years=years)).date().isoformat()


def select_window(players, competition, since, until, phase):
    if since >= until:
        raise ValueError("Window start must precede the exclusive cutoff.")
    p = players[(players.date >= since) & (players.date < until)].copy()
    if competition != "ALL":
        p = p[p.competition == competition]
    if phase != "All":
        pre = {"Powerplay": "pp", "Middle": "mid", "Death": "death"}[phase]
        for target, col in [
            ("runs", pre + "_runs"),
            ("balls", pre + "_balls"),
            ("conceded", pre + "_conceded"),
            ("legal_balls", pre + "_legal"),
            ("wickets", pre + "_wickets"),
            ("dismissals", pre + "_dismissals"),
        ]:
            p[target] = p[col]
    return p


def scout(
    players,
    competition="IPL",
    since=None,
    min_balls=60,
    discipline="Batting",
    until="2026-10-18",
    phase="All",
):
    since = since or window(until)
    p = select_window(players, competition, since, until, phase)
    cols = [
        "matches",
        "runs",
        "balls",
        "conceded",
        "legal_balls",
        "wickets",
        "dismissals",
        "pp_legal",
        "mid_legal",
        "death_legal",
    ]
    keys = ["player_id", "player"] + (["competition"] if competition == "ALL" else [])
    p["weight"] = np.exp2(
        -(pd.Timestamp(until) - pd.to_datetime(p.date)).dt.days / 365.0
    )
    for col in ["runs", "balls", "conceded", "legal_balls", "wickets", "dismissals"]:
        p["weighted_" + col] = p[col] * p.weight
    weighted = [
        "weighted_" + col
        for col in ["runs", "balls", "conceded", "legal_balls", "wickets", "dismissals"]
    ]
    g = p.groupby(keys, as_index=False)[cols + weighted].sum()
    sample = "balls" if discipline == "Batting" else "legal_balls"
    g = g[g[sample] >= min_balls].copy()
    last = (
        p[p[sample] > 0]
        .groupby(keys, as_index=False)
        .date.max()
        .rename(columns={"date": "last_played"})
    )
    g = g.merge(last, on=keys, how="left")
    g["strike_rate"] = 100 * g.runs / g.balls.replace(0, np.nan)
    g["economy"] = 6 * g.conceded / g.legal_balls.replace(0, np.nan)
    g["reliability"] = g["weighted_" + sample] / (g["weighted_" + sample] + 120)
    # Separate competition baselines; ALL is grouped, never a league-strength translation.
    group_keys = ["competition"] if competition == "ALL" else []
    g["score"] = 0.0
    groups = g.groupby("competition") if group_keys else [("", g)]
    for comp, sub in groups:
        raw = p[p.competition == comp] if group_keys else p
        if discipline == "Batting":
            b = max(raw.weighted_balls.sum(), 1)
            par = raw.weighted_runs.sum() / b
            d = raw.weighted_dismissals.sum() / b
            score = 100 * (
                (sub.weighted_runs + 120 * par) / (sub.weighted_balls + 120) - par
            ) - 18 * 100 * (
                (sub.weighted_dismissals + 120 * d) / (sub.weighted_balls + 120) - d
            )
        else:
            b = max(raw.weighted_legal_balls.sum(), 1)
            par = raw.weighted_conceded.sum() / b
            w = raw.weighted_wickets.sum() / b
            score = 6 * (
                par
                - (sub.weighted_conceded + 120 * par) / (sub.weighted_legal_balls + 120)
            ) + 12 * 6 * (
                (sub.weighted_wickets + 120 * w) / (sub.weighted_legal_balls + 120) - w
            )
        g.loc[sub.index, "score"] = score
    g = g.sort_values(
        (["competition"] if competition == "ALL" else []) + ["score", "player_id"],
        ascending=([True] if competition == "ALL" else []) + [False, True],
    )
    return g.round(4)


def roster_scores(players, squads, team, until="2026-10-18", competition="IPL"):
    dated = squads_asof(squads, until)
    r = dated[dated.franchise_id == team].copy()
    since = window(until)
    for discipline, col, sample in [
        ("Batting", "bat_score", "balls"),
        ("Bowling", "bowl_score", "legal_balls"),
    ]:
        scores = scout(
            players, competition, since, min_balls=1, discipline=discipline, until=until
        )
        cols = ["player_id", "score", sample] + (
            ["pp_legal", "mid_legal", "death_legal"] if discipline == "Bowling" else []
        )
        r = r.merge(
            scores[cols].rename(columns={"player_id": "cricsheet_id", "score": col}),
            on="cricsheet_id",
            how="left",
        )
    r["evidence_missing"] = r.bat_score.isna() & r.bowl_score.isna()
    fill = [
        "bat_score",
        "bowl_score",
        "balls",
        "legal_balls",
        "pp_legal",
        "mid_legal",
        "death_legal",
    ]
    r[fill] = r[fill].fillna(0)
    r["utility"] = r.bat_score / 10 + r.bowl_score
    r["bowling_capacity"] = np.where(r.legal_balls >= 120, 4, 0)
    for phase, threshold in [("pp", 36), ("mid", 36), ("death", 24)]:
        r[phase + "_capacity"] = np.where(
            (r.bowling_capacity > 0) & (r[phase + "_legal"] >= threshold), 4, 0
        )
    for phase, prefix in [("Powerplay", "pp"), ("Middle", "mid"), ("Death", "death")]:
        scores = scout(
            players,
            competition,
            since,
            min_balls=1,
            discipline="Bowling",
            until=until,
            phase=phase,
        )
        r[prefix + "_score"] = r.cricsheet_id.map(
            scores.set_index("player_id").score
        ).fillna(0)
    return r


def validate_schedule(players, schedule):
    """Check the returned schedule independently from the constraint matrix."""
    errors = []
    if len(players) != 11 or players.cricsheet_id.duplicated().any():
        errors.append("Eleven distinct players are required.")
    if len(schedule) != 20 or sorted(schedule.over.tolist()) != list(range(1, 21)):
        errors.append("Every over from 1 to 20 must appear once.")
    if schedule.empty:
        return errors + ["A complete schedule is required."]
    ids = set(players.cricsheet_id)
    if not set(schedule.player_id) <= ids:
        errors.append("A scheduled bowler is not selected.")
    ordered = schedule.sort_values("over")
    if ordered.player_id.eq(ordered.player_id.shift()).any():
        errors.append("A bowler has consecutive overs.")
    if not ordered.legal_balls.eq(6).all():
        errors.append("Every planned over must contain six legal balls.")
    for row in players.itertuples():
        z = ordered[ordered.player_id == row.cricsheet_id]
        if len(z) > min(4, int(row.bowling_capacity)):
            errors.append(row.player_name + " exceeds the total workload cap.")
        for label, prefix in [
            ("Powerplay", "pp"),
            ("Middle", "mid"),
            ("Death", "death"),
        ]:
            if len(z[z.phase == label]) > int(getattr(row, prefix + "_capacity")):
                errors.append(row.player_name + " exceeds " + label + " eligibility.")
    for row in ordered.itertuples():
        expected = (
            "Powerplay" if row.over <= 6 else ("Middle" if row.over <= 16 else "Death")
        )
        if row.phase != expected:
            errors.append("Incorrect phase for over " + str(row.over))
    return errors


def optimize(
    roster,
    excluded=(),
    size=11,
    max_overseas=4,
    min_bowlers=5,
    min_batters=5,
    costs=None,
    budget=None,
    locked=(),
    min_spin=0,
    min_pace=0,
    overrides=None,
):
    """Select eleven and solve a full 20-over assignment, then prefer phase evidence."""

    def fail(reason, details=None):
        return {"ok": False, "reason": reason, "diagnostics": details or []}

    if size != 11:
        return fail("This planner supports eleven-player, twenty-over scenarios.")
    r = (
        roster[~roster.player_name.isin(excluded)]
        .copy()
        .sort_values("cricsheet_id")
        .reset_index(drop=True)
    )
    if len(r) < 11:
        return fail("Fewer than eleven players remain after exclusions.")
    if not set(locked) <= set(r.player_name):
        return fail("A locked player is excluded or is not in this dated squad.")
    eligible = ~r.evidence_missing
    override_notes = []
    for name, o in (overrides or {}).items():
        if name not in set(r.player_name):
            return fail("An override names a player outside the available dated squad.")
        if not str(o.get("reason", "")).strip():
            return fail("Every capability assumption needs a written justification.")
        try:
            cap = float(o.get("capacity", 0))
            if not np.isfinite(cap) or not 0 <= cap <= 4:
                return fail("Maximum overs must be finite and between zero and four.")
            idx = r.index[r.player_name.eq(name)][0]
            r.loc[idx, "bowling_capacity"] = int(cap)
            for ph in ["pp", "mid", "death"]:
                value = float(o.get(ph, 0))
                if not np.isfinite(value) or not 0 <= value <= cap:
                    return fail(
                        "Phase caps must be finite, nonnegative and no greater than the total cap."
                    )
                r.loc[idx, ph + "_capacity"] = int(value)
            style = o.get("attack_type", "Unknown")
            if style not in ["Spin", "Pace", "Unknown"]:
                return fail("Use Spin, Pace or Unknown for the reference style.")
            r.loc[idx, "attack_type"] = style
            if r.loc[idx, "evidence_missing"]:
                value = float(o.get("utility", float("nan")))
                if not np.isfinite(value):
                    return fail(
                        "An unobserved player needs an explicit finite utility assumption."
                    )
                r.loc[idx, "utility"] = value
                eligible.loc[idx] = True
        except (ValueError, TypeError):
            return fail("Capability and utility assumptions must be valid numbers.")
        override_notes.append({"player": name, **o})
    if "selection_blocked" in r:
        eligible &= ~r.selection_blocked.astype(bool)
    active = r[eligible]
    diagnostics = []
    checks = [
        ("Eligible players", len(active), 11),
        ("Keepers", int(active.is_wicketkeeper.sum()), 1),
        (
            "Supported bowling options",
            int((active.bowling_capacity > 0).sum()),
            min_bowlers,
        ),
        ("Observed batting options", int((active.balls >= 30).sum()), min_batters),
        (
            "Spin options",
            int(((active.attack_type == "Spin") & (active.bowling_capacity > 0)).sum()),
            min_spin,
        ),
        (
            "Pace options",
            int(((active.attack_type == "Pace") & (active.bowling_capacity > 0)).sum()),
            min_pace,
        ),
        ("Powerplay options", int((active.pp_capacity > 0).sum()), 2),
        ("Death options", int((active.death_capacity > 0).sum()), 2),
    ]
    for name, available, required in checks:
        diagnostics.append(
            {
                "constraint": name,
                "available": available,
                "required": required,
                "enough": available >= required,
            }
        )
        if available < required:
            return fail(
                f"{name}: {available} available, {required} required. Adjust availability, evidence or justified assumptions.",
                diagnostics,
            )
    if active.bowling_capacity.sum() < 20:
        return fail("The eligible players cannot cover twenty overs.", diagnostics)
    if any(not bool(eligible.loc[r.index[r.player_name.eq(n)][0]]) for n in locked):
        return fail(
            "A locked player lacks relevant evidence or has a dated selection block. Capability assumptions cannot override a sourced availability or registration block.",
            diagnostics,
        )
    if int(r[r.player_name.isin(locked)].is_overseas.sum()) > max_overseas:
        return fail(
            "The locked players already exceed the overseas limit.", diagnostics
        )
    prices = None
    if budget is not None:
        if not np.isfinite(budget) or budget < 0:
            return fail("The XI budget must be a finite nonnegative number.")
        if costs is None or any(n not in costs for n in r.player_name):
            return fail("Enter an assumed cost for every available player.")
        try:
            prices = np.array([costs[n] for n in r.player_name], float)
        except (ValueError, TypeError):
            return fail("Costs must be numeric.")
        if not np.isfinite(prices).all() or (prices < 0).any():
            return fail("Costs must be finite and nonnegative.")
        cheapest = float(np.sort(prices[eligible.to_numpy()])[:11].sum())
        if cheapest > budget + 1e-8:
            return fail(
                f"Even the eleven cheapest eligible players cost {cheapest:.2f} Cr, above the {budget:.2f} Cr budget.",
                diagnostics,
            )
    n = len(r)
    v = 21 * n
    rows = []
    lower = []
    upper = []

    def add(coeff, lo, hi):
        rows.append(coeff)
        lower.append(lo)
        upper.append(hi)

    def selected(vector):
        return {i: float(x) for i, x in enumerate(vector) if x}

    def slot(i, over):
        return n + over * n + i

    add(selected(np.ones(n)), 11, 11)
    add(selected(r.is_overseas), 0, max_overseas)
    add(selected(r.is_wicketkeeper), 1, np.inf)
    add(selected((r.bowling_capacity > 0).astype(int)), min_bowlers, np.inf)
    add(selected((r.balls >= 30).astype(int)), min_batters, np.inf)
    add(
        selected(((r.attack_type == "Spin") & (r.bowling_capacity > 0)).astype(int)),
        min_spin,
        np.inf,
    )
    add(
        selected(((r.attack_type == "Pace") & (r.bowling_capacity > 0)).astype(int)),
        min_pace,
        np.inf,
    )
    if prices is not None:
        add(selected(prices), 0, budget)
    for over in range(20):
        add({slot(i, over): 1 for i in range(n)}, 1, 1)
    for i in range(n):
        add(
            {
                i: -min(4, int(r.loc[i, "bowling_capacity"])),
                **{slot(i, o): 1 for o in range(20)},
            },
            -np.inf,
            0,
        )
        for ph, overs in [
            ("pp", range(0, 6)),
            ("mid", range(6, 16)),
            ("death", range(16, 20)),
        ]:
            add(
                {i: -int(r.loc[i, ph + "_capacity"]), **{slot(i, o): 1 for o in overs}},
                -np.inf,
                0,
            )
        for o in range(19):
            add({slot(i, o): 1, slot(i, o + 1): 1}, 0, 1)
    row_idx = []
    col_idx = []
    values = []
    for j, row in enumerate(rows):
        for i, value in row.items():
            row_idx.append(j)
            col_idx.append(i)
            values.append(value)
    matrix = coo_matrix((values, (row_idx, col_idx)), shape=(len(rows), v)).tocsr()
    lb = np.zeros(v)
    lb[:n] = r.player_name.isin(locked).astype(int)
    ub = np.ones(v)
    ub[:n] = eligible.astype(int)
    # Primary objective owns selection. The phase objective only arranges the selected XI.
    objective = np.zeros(v)
    objective[:n] = -r.utility.to_numpy() + np.arange(n) * 1e-8
    constraints = LinearConstraint(matrix, lower, upper)
    result = milp(
        objective,
        integrality=np.ones(v),
        bounds=Bounds(lb, ub),
        constraints=constraints,
        options={"time_limit": 12, "mip_rel_gap": 0.00001},
    )
    if not result.success:
        reason = (
            "The solver reached its time limit. No plan is presented as optimal."
            if result.status == 1
            else "The combined availability, role, phase, overseas and budget requirements cannot form a supported twenty-over XI."
        )
        return fail(reason, diagnostics)
    chosen_mask = result.x[:n] > 0.5
    phase_objective = np.zeros(v)
    for over in range(20):
        ph = "pp" if over < 6 else ("mid" if over < 16 else "death")
        for i in range(n):
            phase_objective[slot(i, over)] = (
                -float(r.loc[i, ph + "_score"]) if ph + "_score" in r else 0
            )
    lb2 = lb.copy()
    ub2 = ub.copy()
    lb2[:n] = chosen_mask.astype(int)
    ub2[:n] = chosen_mask.astype(int)
    arranged = milp(
        phase_objective,
        integrality=np.ones(v),
        bounds=Bounds(lb2, ub2),
        constraints=constraints,
        options={"time_limit": 5},
    )
    solution = arranged.x if arranged.success else result.x
    assignment = solution[n:].reshape(20, n)
    plan = []
    for over in range(20):
        i = int(np.argmax(assignment[over]))
        phase = "Powerplay" if over < 6 else ("Middle" if over < 16 else "Death")
        plan.append(
            {
                "over": over + 1,
                "phase": phase,
                "player_id": r.loc[i, "cricsheet_id"],
                "bowler": r.loc[i, "player_name"],
                "legal_balls": 6,
            }
        )
    schedule = pd.DataFrame(plan)
    chosen = r[chosen_mask].copy()
    for phase, ph in [("Powerplay", "pp"), ("Middle", "mid"), ("Death", "death")]:
        totals = (
            schedule[schedule.phase == phase].groupby("player_id").legal_balls.sum()
        )
        chosen[ph + "_allocated_balls"] = (
            chosen.cricsheet_id.map(totals).fillna(0).astype(int)
        )
    if prices is not None:
        chosen["scenario_cost_cr"] = chosen.player_name.map(costs)
    errors = validate_schedule(chosen, schedule)
    if errors:
        raise RuntimeError(
            "The independent schedule check did not accept this plan. " + errors[0]
        )
    chosen["selection_reason"] = [
        ("Locked by analyst; " if row.player_name in locked else "")
        + (
            "Explicit analyst utility assumption; "
            if row.evidence_missing
            else "Observed evidence; "
        )
        + f"{int((schedule.player_id==row.cricsheet_id).sum())} scheduled overs; selected under the active constraints."
        for row in chosen.itertuples()
    ]
    alternatives = r[~chosen_mask][
        ["player_name", "utility", "attack_type", "evidence_missing"]
    ].copy()
    alternatives["explanation"] = np.where(
        ~eligible.loc[alternatives.index],
        "Not selectable: review missing evidence and any dated availability block.",
        "Outside the optimal XI for these constraints. Lock this player to compare a counterfactual.",
    )
    return {
        "ok": True,
        "players": chosen,
        "schedule": schedule,
        "utility": float(chosen.utility.sum()),
        "overseas": int(chosen.is_overseas.sum()),
        "bowlers": int((chosen.bowling_capacity > 0).sum()),
        "keepers": int(chosen.is_wicketkeeper.sum()),
        "cost": float(chosen.scenario_cost_cr.sum()) if prices is not None else None,
        "override_notes": override_notes,
        "alternatives": alternatives,
        "diagnostics": diagnostics,
        "schedule_checks": {
            "overs": 20,
            "legal_balls": 120,
            "no_consecutive_overs": True,
            "maximum_four_overs": True,
            "phase_eligibility": True,
        },
        "phase_arrangement_optimized": bool(arranged.success),
        "scope": "Twenty-over planning with a 6/10/4 phase structure, one bowler per over, no consecutive overs and at most four overs per player. Styles, evidence thresholds and overrides are planning assumptions. Full Impact Player and competition eligibility certification are outside this model.",
    }


def player_interval(
    players,
    pid,
    discipline="Batting",
    until="2026-10-18",
    since=None,
    competition="IPL",
    phase="All",
):
    p = select_window(players, competition, since or window(until), until, phase)
    p = p[p.player_id == pid]
    sample = "balls" if discipline == "Batting" else "legal_balls"
    runs = "runs" if discipline == "Batting" else "conceded"
    scale = 100 if discipline == "Batting" else 6
    p = p[p[sample] > 0]
    if len(p) < 5:
        return {
            "matches": len(p),
            "interval": None,
            "note": "At least five relevant match samples required.",
        }
    rng = np.random.default_rng(42)
    idx = rng.integers(0, len(p), (500, len(p)))
    rate = scale * p[runs].to_numpy()[idx].sum(1) / p[sample].to_numpy()[idx].sum(1)
    return {
        "matches": len(p),
        "rate": float(scale * p[runs].sum() / p[sample].sum()),
        "interval": np.quantile(rate, [0.025, 0.975]).round(2).tolist(),
        "window": {
            "since": since or window(until),
            "until": until,
            "competition": competition,
            "phase": phase,
        },
        "note": "Observed-rate match-bootstrap interval, not future performance; independent-match assumption.",
    }
