"""Rolling-origin descriptive role study. No future data enters training ranks."""

from pathlib import Path
import json, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from boundary_core.analytics import load, scout, window
from boundary_core.branding import TEAMS


def build():
    players, _, _ = load()
    rows = []
    for year in [2024, 2025, 2026]:
        cutoff = f"{year}-01-01"
        end = f"{year+1}-01-01"
        for discipline in ["Batting", "Bowling"]:
            for phase in ["All", "Powerplay", "Middle", "Death"]:
                train = scout(
                    players, "IPL", window(cutoff), 60, discipline, cutoff, phase
                )
                future = scout(players, "IPL", cutoff, 30, discipline, end, phase)
                metric = "strike_rate" if discipline == "Batting" else "economy"
                ranks = {
                    "Boundary descriptive score": train.sort_values(
                        ["score", "player_id"], ascending=[False, True]
                    ),
                    "Raw historical rate": train.sort_values(
                        [metric, "player_id"], ascending=[discipline == "Bowling", True]
                    ),
                }
                follow = future.set_index("player_id")
                both = train.merge(
                    future[["player_id", metric]],
                    on="player_id",
                    suffixes=("_train", "_future"),
                )
                rho = (
                    float(
                        spearmanr(
                            both.score,
                            both[metric + "_future"]
                            * (1 if discipline == "Batting" else -1),
                        ).statistic
                    )
                    if len(both) > 2
                    else None
                )
                for method, ordered in ranks.items():
                    shortlist = ordered.head(5)
                    observed = follow.loc[
                        follow.index.intersection(shortlist.player_id)
                    ]
                    rows.append(
                        {
                            "test_year": year,
                            "discipline": discipline,
                            "phase": phase,
                            "method": method,
                            "training_before": cutoff,
                            "training_from": window(cutoff),
                            "training_min_balls": 60,
                            "followup_min_balls": 30,
                            "eligible_training_players": len(train),
                            "selected": len(shortlist),
                            "with_followup_sample": len(observed),
                            "without_followup_sample": len(shortlist) - len(observed),
                            "mean_future_rate": (
                                round(float(observed[metric].mean()), 4)
                                if len(observed)
                                else None
                            ),
                            "future_rate_metric": metric,
                            "mean_future_wicket_rate_per_100_balls": (
                                round(
                                    float(
                                        (
                                            100
                                            * observed.wickets
                                            / observed.legal_balls.replace(0, np.nan)
                                        ).mean()
                                    ),
                                    4,
                                )
                                if discipline == "Bowling" and len(observed)
                                else None
                            ),
                            "score_future_rate_spearman_all_followed": (
                                round(rho, 4)
                                if rho is not None and np.isfinite(rho)
                                else None
                            ),
                            "selected_ids": "|".join(shortlist.player_id),
                            "selected_names": " | ".join(shortlist.player),
                            "latest_test_match": players[(players.competition == "IPL") & (players.date >= cutoff) & (players.date < end)].date.max(),
                        }
                    )
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "data/scouting_benchmark.csv", index=False)
    report = {
        "design": "24 fixed rolling-origin settings: 2024, 2025 and available 2026 IPL follow-up; batting/bowling; all, powerplay, middle, death. Two ranking methods per setting. Three previous years of training only. Top five chosen before inspecting follow-up.",
        "comparison": "Boundary descriptive score versus raw historical strike rate (batting) or economy (bowling). Follow-up rate is an unweighted average across selected players with sufficient future exposure. Bowling wicket-taking is also reported.",
        "sample_rules": "At least 60 relevant training balls and 30 follow-up balls. No future exposure is used to choose the shortlist. Missing follow-up players stay counted in the exported denominator.",
        "limitations": [
            "Only three seasons, correlated players and overlapping training windows.",
            "Players without follow-up evidence are not assigned zero performance; observed-only means have exposure and survivorship bias.",
            "Role, schedule, venue, opposition, availability and tactical fit are not controlled.",
            "Batting strike rate and bowling economy alone do not capture the full scoring objective.",
            "2026 means the available uploaded season, not a live feed.",
            "No parameter tuning was performed from these results. No causal, scouting superiority or future-value claim is justified.",
        ],
        "human_review": "20 team tasks are supplied separately. No authenticated professional reviews have been collected.",
        "rows": len(frame),
        "settings": 24,
    }
    (ROOT / "data/scouting_benchmark_report.json").write_text(
        json.dumps(report, indent=2)
    )
    tasks = []
    for team, name in TEAMS.items():
        tasks += [
            {
                "id": team + "-SCOUT",
                "team": team,
                "task": f"Compare death-bowling options for {name[0]} using IPL, three-year evidence and at least 120 phase balls.",
                "controls": {
                    "competition": "IPL",
                    "phase": "Death",
                    "discipline": "Bowling",
                    "min_balls": 120,
                },
                "review_steps": [
                    "Check every named identity, sample and last relevant match.",
                    "Compare raw economy and wickets beside the descriptive score.",
                    "Record what is missing about current eligibility, availability, venue and acquisition.",
                ],
                "rubric": [
                    "Evidence support (1–5)",
                    "Role relevance (1–5)",
                    "Clarity (1–5)",
                    "Usefulness (1–5)",
                ],
                "reviewer_rating": None,
            },
            {
                "id": team + "-XI",
                "team": team,
                "task": "Build the default supported XI. Exclude its leading scheduled bowler, repeat and compare the change.",
                "review_steps": [
                    "Check 11 distinct players, keeper, overseas and role requirements.",
                    "Check 20 overs, no consecutive overs, maximum four, phase eligibility and excluded player absent.",
                    "Explain changes and uncertainty without calling the scenario score a win probability.",
                    "Export a decision pack and reproduce the active assumptions.",
                ],
                "rubric": [
                    "Evidence support (1–5)",
                    "Role relevance (1–5)",
                    "Clarity (1–5)",
                    "Usefulness (1–5)",
                ],
                "reviewer_rating": None,
            },
        ]
    (ROOT / "data/review_tasks.json").write_text(json.dumps(tasks, indent=2))
    print(f"{len(frame)} study rows; {len(tasks)} unrated review tasks")


if __name__ == "__main__":
    build()
