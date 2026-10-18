"""Reproducible sampled official comparisons; preserve discrepancies and source URLs."""

from pathlib import Path
import sys, json, zipfile
import pandas as pd

R = Path(__file__).resolve().parents[1]
import argparse

parser = argparse.ArgumentParser(
    description="Recalculate numeric checkpoints transcribed from primary pages reviewed on 2026-10-18. This does not fetch live official records."
)
parser.add_argument("--output", type=Path, default=Path("work/accuracy-audit"))
O = parser.parse_args().output
O.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(R))
from creaseiq_core.analytics import load, resolve

p, s, _ = load()
m = pd.read_csv(
    R / "data/matches.csv.gz",
    dtype={"match_id": str, "season": str},
    keep_default_na=False,
)
checks = []
base = "https://www.iplt20.com/news/article/"


def add(kind, subject, metric, expected, observed, url, scope, coverage=False):
    checks.append(
        {
            "kind": kind,
            "subject": subject,
            "metric": metric,
            "official_value": expected,
            "archive_value": int(observed),
            "difference": int(observed) - expected,
            "status": (
                "MATCH"
                if observed == expected
                else ("COVERAGE GAP" if coverage else "MISMATCH")
            ),
            "scope": scope,
            "source": url,
        }
    )


def pid(query, comp):
    hits = resolve(p, query)
    ids = [
        v["player_id"]
        for v in hits
        if (p.player_id.eq(v["player_id"]) & p.competition.eq(comp)).any()
    ]
    assert len(ids) == 1, (query, comp, ids)
    return ids[0]


def fact(mid, query, metric, value, url):
    z = p[(p.match_id == str(mid)) & (p.player_id == pid(query, "IPL"))]
    assert len(z) == 1, (mid, query)
    add("IPL match", query, metric, value, z[metric].sum(), url, "Match " + str(mid))


# Explicit numerical player facts transcribed from the official match reports.
rows = {
    "1529309": (
        "tata-ipl-2026-match-66-gt-v-csk-match-report",
        [
            ("Sai Sudharsan", "runs", 84),
            ("Sai Sudharsan", "balls", 53),
            ("Shubman Gill", "runs", 64),
            ("Shubman Gill", "balls", 37),
            ("Jos Buttler", "runs", 57),
            ("Jos Buttler", "balls", 27),
            ("Spencer Johnson", "wickets", 1),
            ("Spencer Johnson", "conceded", 47),
            ("Anshul Kamboj", "wickets", 1),
            ("Anshul Kamboj", "conceded", 57),
            ("Sanju Samson", "runs", 0),
        ],
    ),
    "1529310": (
        "tata-ipl-2026-match-67-srh-v-rcb-match-report",
        [
            ("Travis Head", "runs", 26),
            ("Travis Head", "balls", 16),
            ("Abhishek Sharma", "runs", 56),
            ("Abhishek Sharma", "balls", 22),
            ("Ishan Kishan", "runs", 79),
            ("Ishan Kishan", "balls", 46),
            ("Heinrich Klaasen", "runs", 51),
            ("Heinrich Klaasen", "balls", 24),
            ("Rasikh Salam", "wickets", 2),
            ("Rasikh Salam", "conceded", 52),
            ("Nitish Kumar Reddy", "runs", 29),
            ("Nitish Kumar Reddy", "balls", 12),
            ("Venkatesh Iyer", "runs", 44),
            ("Venkatesh Iyer", "balls", 19),
            ("Virat Kohli", "runs", 15),
            ("Virat Kohli", "balls", 11),
            ("Rajat Patidar", "runs", 56),
            ("Rajat Patidar", "balls", 39),
            ("Eshan Malinga", "wickets", 2),
            ("Eshan Malinga", "conceded", 33),
            ("Sakib Hussain", "wickets", 1),
            ("Sakib Hussain", "conceded", 31),
            ("Krunal Pandya", "runs", 41),
            ("Krunal Pandya", "balls", 31),
            ("Tim David", "runs", 15),
            ("Tim David", "balls", 7),
        ],
    ),
    "1529311": (
        "tata-ipl-2026-match-68-lsg-vs-pbks-match-report",
        [
            ("Arshdeep Singh", "wickets", 0),
            ("Arshdeep Singh", "conceded", 52),
            ("Arshin Kulkarni", "runs", 0),
            ("Azmatullah Omarzai", "wickets", 1),
            ("Azmatullah Omarzai", "conceded", 29),
            ("Marco Jansen", "wickets", 2),
            ("Marco Jansen", "conceded", 33),
            ("Nicholas Pooran", "runs", 2),
            ("Nicholas Pooran", "balls", 7),
            ("Josh Inglis", "runs", 72),
            ("Josh Inglis", "balls", 44),
            ("Ayush Badoni", "runs", 43),
            ("Ayush Badoni", "balls", 18),
            ("Yuzvendra Chahal", "wickets", 2),
            ("Yuzvendra Chahal", "conceded", 25),
            ("Rishabh Pant", "runs", 26),
            ("Rishabh Pant", "balls", 22),
            ("Shashank Singh", "wickets", 1),
            ("Shashank Singh", "conceded", 29),
            ("Abdul Samad", "runs", 37),
            ("Abdul Samad", "balls", 20),
            ("Mohammed Shami", "wickets", 2),
            ("Mohammed Shami", "conceded", 45),
            ("Cooper Connolly", "runs", 18),
            ("Cooper Connolly", "balls", 10),
            ("Prabhsimran Singh", "runs", 69),
            ("Prabhsimran Singh", "balls", 39),
            ("Shreyas Iyer", "runs", 101),
            ("Shreyas Iyer", "balls", 51),
            ("Suryansh Shedge", "runs", 9),
        ],
    ),
    "1529312": (
        "tata-ipl-2026-match-69-mi-v-rr-match-report",
        [
            ("Vaibhav Sooryavanshi", "runs", 4),
            ("Yashasvi Jaiswal", "runs", 27),
            ("Riyan Parag", "runs", 14),
            ("Dhruv Jurel", "runs", 38),
            ("Dhruv Jurel", "balls", 26),
            ("Jofra Archer", "runs", 32),
            ("Jofra Archer", "balls", 15),
            ("Rohit Sharma", "runs", 0),
            ("Naman Dhir", "runs", 6),
            ("Will Jacks", "runs", 33),
            ("Will Jacks", "balls", 18),
            ("Suryakumar Yadav", "runs", 60),
            ("Suryakumar Yadav", "balls", 42),
        ],
    ),
    "1529313": (
        "tata-ipl-2026-match-70-kkr-v-dc-match-report",
        [
            ("Abhishek Porel", "runs", 22),
            ("Abhishek Porel", "balls", 18),
            ("KL Rahul", "runs", 60),
            ("Axar Patel", "runs", 39),
            ("Axar Patel", "balls", 25),
            ("David Miller", "runs", 28),
            ("Ashutosh Sharma", "runs", 18),
            ("Kartik Tyagi", "conceded", 55),
            ("Finn Allen", "runs", 20),
            ("Finn Allen", "balls", 13),
            ("Manish Pandey", "runs", 25),
            ("Lungi Ngidi", "wickets", 3),
            ("Lungi Ngidi", "conceded", 27),
            ("Mitchell Starc", "wickets", 2),
            ("Mitchell Starc", "conceded", 26),
            ("Kuldeep Yadav", "wickets", 3),
            ("Kuldeep Yadav", "conceded", 29),
        ],
    ),
    "1535465": (
        "tata-ipl-2026-final-rcb-v-gt-match-report",
        [
            ("Washington Sundar", "runs", 50),
            ("Washington Sundar", "balls", 37),
            ("Arshad Khan", "runs", 15),
            ("Arshad Khan", "balls", 6),
            ("Rahul Tewatia", "runs", 7),
            ("Jason Holder", "runs", 7),
            ("Venkatesh Iyer", "runs", 32),
            ("Venkatesh Iyer", "balls", 16),
            ("Devdutt Padikkal", "runs", 1),
            ("Virat Kohli", "runs", 75),
            ("Virat Kohli", "balls", 42),
        ],
    ),
}
for mid, (slug, values) in rows.items():
    for query, metric, value in values:
        fact(mid, query, metric, value, base + slug)
expected_points = {
    "RCB": (14, 9, 5, 0, 18),
    "GT": (14, 9, 5, 0, 18),
    "SRH": (14, 9, 5, 0, 18),
    "RR": (14, 8, 6, 0, 16),
    "PBKS": (14, 7, 6, 1, 15),
    "DC": (14, 7, 7, 0, 14),
    "KKR": (14, 6, 7, 1, 13),
    "CSK": (14, 6, 8, 0, 12),
    "MI": (14, 4, 10, 0, 8),
    "LSG": (14, 4, 10, 0, 8),
}
league = (
    m[(m.competition == "IPL") & (m.season == "2026")]
    .sort_values(["date", "match_id"])
    .iloc[:70]
)
for team, values in expected_points.items():
    z = league[(league.team1 == team) | (league.team2 == team)]
    won = int(z.winner.eq(team).sum())
    nr = int(z.winner.eq("").sum())
    observed = (len(z), won, len(z) - won - nr, nr, 2 * won + nr)
    for metric, expected, obs in zip(
        ["played", "won", "lost", "no_result", "points"], values, observed
    ):
        add(
            "IPL league table",
            team,
            metric,
            expected,
            obs,
            "https://www.iplt20.com/points-table",
            "2026 league stage",
        )
# Full-season / career checkpoints, with explicitly different scopes and coverage failures retained.
for year, expected, url in [
    (
        2024,
        741,
        "https://www.royalchallengers.com/rcb-cricket-news/news/when-i-talk-about-him-i-see-a-phenomenal-player-simon-doull-on-virat-kohli",
    ),
    (
        2025,
        657,
        "https://royalchallengers.com/rcb-cricket-news/news/video-virat-kohli-all-set-to-roar-in-ipl-2026",
    ),
    (
        2026,
        675,
        "https://www.royalchallengers.com/rcb-cricket-news/news/virat-is-a-very-instinctive-player-freddie-wilde-on-rcb-stars-explosive",
    ),
]:
    z = p[
        (p.player_id == pid("Virat Kohli", "IPL"))
        & (p.competition == "IPL")
        & (p.season == str(year))
    ]
    add("IPL season", "Virat Kohli", "runs", expected, z.runs.sum(), url, str(year))
for query, metric, expected in [
    ("Vaibhav Sooryavanshi", "runs", 776),
    ("Kagiso Rabada", "wickets", 29),
    ("Bhuvneshwar Kumar", "wickets", 28),
    ("Jofra Archer", "wickets", 25),
]:
    z = p[
        (p.player_id == pid(query, "IPL"))
        & (p.competition == "IPL")
        & (p.season == "2026")
    ]
    add(
        "IPL season",
        query,
        metric,
        expected,
        z[metric].sum(),
        "https://www.iplt20.com/",
        "2026",
    )
icc = "https://www.icc-cricket.com/news/india-s-big-conundrum-at-the-top-who-replaces-rohit-and-kohli-in-t20is"
for query, expected in [
    ("Virat Kohli", 4188),
    ("Rohit Sharma", 4231),
    ("Yashasvi Jaiswal", 502),
    ("Shubman Gill", 335),
    ("KL Rahul", 2265),
    ("Ruturaj Gaikwad", 500),
    ("Ishan Kishan", 796),
]:
    identities = resolve(p, query)
    ids = [
        v["player_id"]
        for v in identities
        if (
            (p.player_id == v["player_id"])
            & (p.competition == "T20I")
            & (p.team == "India")
        ).any()
    ]
    assert len(ids) == 1, (query, ids)
    z = p[(p.player_id == ids[0]) & (p.competition == "T20I") & (p.date < "2024-07-01")]
    add(
        "T20I career coverage",
        query,
        "runs",
        expected,
        z.runs.sum(),
        icc,
        "Before 2024-07-01",
        True,
    )
for query, metric, expected in [
    ("Liam Livingstone", "runs", 348),
    ("Adam Milne", "wickets", 12),
    ("M de Lange", "wickets", 12),
    ("Rashid Khan", "wickets", 12),
    ("AU Rashid", "wickets", 12),
]:
    z = p[
        (p.player_id == pid(query, "Hundred"))
        & (p.competition == "Hundred")
        & (p.season == "2021")
    ]
    add(
        "Hundred season",
        query,
        metric,
        expected,
        z[metric].sum(),
        "https://www.thehundred.com/news/2368831",
        "2021",
    )
url = "https://www.cricket.com.au/news/4439167/big-bash-bbl15-final-match-report-scores-highlights-perth-scorchers-sydney-sixers-optus-stadium-allen-marsh-beardman-smith-starc-davies-turner"
for query, metric, expected in [
    ("Mitchell Marsh", "runs", 44),
    ("Mitchell Marsh", "balls", 43),
    ("Finn Allen", "runs", 36),
    ("Josh Inglis", "runs", 29),
    ("SPD Smith", "runs", 24),
    ("SPD Smith", "balls", 13),
    ("JR Philippe", "runs", 24),
    ("JR Philippe", "balls", 24),
    ("David Payne", "wickets", 3),
    ("David Payne", "conceded", 18),
    ("AM Hardie", "wickets", 1),
    ("AM Hardie", "conceded", 16),
    ("JA Richardson", "wickets", 3),
    ("JA Richardson", "conceded", 32),
]:
    hits = resolve(p, query)
    ids = [
        v["player_id"]
        for v in hits
        if (p.player_id.eq(v["player_id"]) & p.competition.eq("BBL")).any()
    ]
    assert len(ids) == 1, (query, ids)
    z = p[(p.player_id == ids[0]) & (p.competition == "BBL") & (p.date == "2026-01-25")]
    add("BBL final", query, metric, expected, z[metric].sum(), url, "2026-01-25")
z = p[
    (p.player_id == pid("SPD Smith", "BBL"))
    & (p.competition == "BBL")
    & (p.season == "2025/26")
]
add("BBL season", "Steve Smith", "runs", 299, z.runs.sum(), url, "2025/26")
url = "https://www.bcci.tv/video/5564739/smat-2024-qf4-mumbai-vs-vidarbha-ajinkya-rahane-sets-the-platform-with-stylish-8445"
z = p[
    (p.player_id == pid("Ajinkya Rahane", "SMAT"))
    & (p.competition == "SMAT")
    & (p.date == "2024-12-11")
]
for metric, expected in [("runs", 84), ("balls", 45)]:
    add(
        "SMAT quarterfinal",
        "Ajinkya Rahane",
        metric,
        expected,
        z[metric].sum(),
        url,
        "2024-12-11",
    )
f = pd.DataFrame(checks)
f["checked_on"] = "2026-10-18"
f["review_note"] = ""
conflict = (f.subject == "Anshul Kamboj") & (f.metric == "conceded")
f.loc[conflict, "review_note"] = (
    "Unresolved source conflict: IPL report says 57; archive and independently retrieved Cricbuzz scorecard say 56. Official dynamic scorecard did not expose bowling rows. Preserve archive value pending primary scorecard review. Secondary corroboration: https://m.cricbuzz.com/player-match-highlights/152229/1/14598/bowling"
)
f.to_csv(O / "official_validation.csv", index=False)
summary = {
    "checked_on": "2026-10-18",
    "fields": len(f),
    "status_counts": f.status.value_counts().to_dict(),
    "sources": f.source.nunique(),
    "IPL_teams_compared": sorted(expected_points),
    "scope": "Primary-source sample across all ten IPL teams and all five archive competitions, plus complete all-ten-team league P/W/L/NR/points comparisons. This is not an official record check of every player or match. Missing T20I coverage is retained as a failure to match full-career references; no runs are invented to fill it.",
    "mismatches": f[f.status != "MATCH"].to_dict("records"),
}
(O / "official_validation_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
