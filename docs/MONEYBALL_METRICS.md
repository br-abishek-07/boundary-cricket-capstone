# Moneyball metrics: how to use and reproduce them

These features extend the Research Coordinator. Pandas calculates the numbers;
DeepSeek receives a small evidence packet and writes a cited interpretation.
No API request is made while you browse the tables.

## 1. Files and setup

The dev branch includes the required sources. Delivery, wicket and roster CSVs
are stored as `.csv.gz` to reduce download size. This is lossless compression:
no rows or fields were removed from the distributed files.

For a local replacement, put the following files in `data/` or `creaseiq/data/`:

- `ipl_deliveries_clean_2008_2026.csv`
- `ipl_wickets_clean_2008_2026.csv`
- `ipl_match_rosters.csv`
- `ipl_auction_clean_2013_2026.csv`
- `ipl_auction_player_links.csv`

The first three come from the uploaded `IPL_Cricsheet_Clean_Accurate_Data_2008_2026.zip`.
Auction prices and their identity crosswalk come from the uploaded
`IPL_Clean_Real_Datasets_2008_2026.zip`.
The canonical delivery schema uses `over_number_zero_based` and
`is_ball_faced_by_batter`. The other upload's delivery CSV has a different schema;
do not replace the canonical file with it without explicitly adapting the mapping.

You can also leave the canonical files inside a subfolder named
`IPL_CRICSHEET_VERIFIED_CLEAN_2008_2026` under either data root. An extracted CSV
is preferred over a bundled gzip copy. Within the same format, the configured
`DATA_DIR` takes precedence. Avoid leaving multiple conflicting copies.

Install the repository requirements, then run `streamlit run app.py` from the
repository root. Configure `DEEPSEEK_API_KEY` in Streamlit secrets for reports.
Statistics work without the key. New source files are loaded only when a relevant
workspace needs them. A missing source disables its new metrics, not the dashboard.

## 2. Player Profile

Select a player and the IPL competition. The three delivery-based rows show:

| Phase | Zero-based over numbers |
| --- | --- |
| Powerplay | 0 through 5 |
| Middle | 6 through 15 |
| Death | 16 through 19 |

These are the project's requested fixed bands. They are not the usual alternative
phase convention, nor a reconstruction of rain-adjusted powerplay rules.

- Strike rate = 100 × batter runs / balls faced.
- Batter dot percentage = 100 × balls faced with zero batter runs / balls faced.
- The supplied ball-faced flag excludes wides and includes source-counted no-balls.
- Byes and leg-byes can be batter dots even when the team scores extras.
- Super overs are excluded. With no balls faced, rates are N/A in the table and
  `null` in JSON. The player is matched by Cricsheet ID, not by name.

The phase table always uses the separate IPL archive. When the career scope is
“All supplied competitions”, its career totals may cover other leagues while the
phase table remains explicitly IPL-only. Selecting a non-IPL competition makes
these IPL phase metrics unavailable for that report.

Open **Inspect evidence sent to the scout** to see the phase values, ball counts,
source fingerprint and fact IDs. **Generate Scouting Report** sends this packet.

## 3. Auction Trends

The original auction charts still use `auction.csv` and its unverified amount
units. The separate **Moneyball** section uses cleaned sale records with explicit
native currencies. Do not add or compare amounts across these two sources.

Choose **Moneyball sale season** independently of the legacy chart year:

- **All Time:** use each matched player's latest supplied sale.
- **A season:** consider sold transactions in that season only.

For each accepted sale, match the player to performance in the **same IPL season**:

- Cost per run = native sale price / that season's IPL batter runs.
- Cost per wicket = native sale price / that season's IPL bowler-credited wickets.

This is a retrospective price/output description. It uses performance after the
sale and must not be treated as a pre-auction forecast or causal measure of value.
All observed IPL teams in the season contribute to the denominator; output is not
restricted to the purchasing franchise. Runs and wickets are separate views of
the same price; their cost ratios must not be added.

INR and USD remain separate native currencies. No exchange rate or inflation
adjustment is assumed. A zero denominator gives N/A, not zero cost or infinity.
A player absent from the season's supplied rosters has unknown performance.
A roster member without batting or bowling events has zero observed output; a
roster entry alone does not prove an active playing appearance.

## 4. Identity and evidence rules

The price crosswalk is accepted only when `join_method=exact_alias`,
`join_usable=1`, `review_needed=0`, and transaction season/team agree.
Heuristic initial/surname links and ambiguous links are excluded. Multiple sales
for the same ID in its latest season are withheld instead of choosing arbitrarily.
A later uncertain sale with the same normalized source name prevents falling back
to that name's older exact match. An older alias sale for an already matched ID
is superseded by that ID's latest sale. These filters are deliberately conservative;
source aliases themselves are not independent identity certification.

Bowler wickets come from the separate dismissal-event credit flag, joined to
its delivery. Run outs and other uncredited dismissals are not bowler wickets.
Missing event keys, duplicates and invalid numerical values cause the affected
calculation to be withheld rather than silently counted.

The complete table can be downloaded from the app. To keep context small, the
Auction Analyst receives up to four high-price examples, alternating native
currency groups. This is a sample, not a market-wide ranking. Its scope and
exclusion counts are included. Existing limits remain: at most 30 player facts,
80 auction facts and 24,000 UTF-8 bytes per packet. New facts have unique IDs.
The report cache fingerprint changes when source evidence, scope or prompts change.

## 5. Data scope and checks

The supplied canonical archive contains 295,732 delivery events across 1,243
match IDs, dated 18 April 2008 through 31 May 2026. It includes partial games and
super overs, which ordinary performance calculations exclude. The cleaned auction
CSV contains 1,381 sold transactions labelled with IPL seasons 2013–2026; season
labels need not equal auction-event calendar years.

The supplied “verified” name is a package label, not a claim of official
certification. Automated tests reconcile source events and derived values; they do
not independently verify every event or sale against official scorecards.

Run the focused tests from the repository root:

```bash
python -m unittest discover -s tests -p 'test_moneyball.py' -v
python -m unittest discover -s tests -p 'test_*agent*.py' -v
python -m unittest discover -s tests -p 'test_home_overview.py' -v
```

The new tests cover every supplied batter's phase totals, all sale-season scopes,
no-ball/wide semantics, missing phases, zero wickets, rejected identity links,
source-file cache invalidation, bounded JSON packets and optional-source failures.
Agent tests mock the provider; they make no paid API calls.

## 6. Files and attribution

`data_loader.py` caches projected CSV reads by path, size and nanosecond modification
time. Replacing a file normally refreshes its cache automatically. If a replacement
deliberately preserves both size and timestamp, clear Streamlit's data cache or reboot.
The loader reads only needed delivery columns into memory. `moneyball.py` contains
pure Pandas calculations; `app.py` handles selection, presentation and packet assembly.
`agents.py` retains the shared JSON parser, citation checks and response limits.

Data acknowledgement: **Cricsheet** — https://cricsheet.org/ . The source licence is
included in `data/CRICSHEET_SOURCE_LICENSE.txt` (Open Data Commons Attribution).
The price data are the user's supplied historical sold-player records, not a live
market-price feed. `data/moneyball_source_manifest.json` records the input filenames,
row counts and raw/compressed SHA-256 hashes for the redistributed files.
