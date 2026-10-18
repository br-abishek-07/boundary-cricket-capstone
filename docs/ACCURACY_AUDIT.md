# Boundary accuracy and practical-use audit

Version 3.0.2 · Reviewed 18 October 2026

The app is useful as an inspectable capstone research tool. It is not yet a certified franchise decision system. Calculations agree with the supplied delivery archive, but official coverage is incomplete in some competitions, current roster verification is partial, and the forecast has no demonstrated advantage over its baseline.

## 1. Why Virat Kohli showed 114 runs

The screenshot selected IPL, Death phase, and 2023-10-18 to before 2026-10-18. The dossier inherited those research filters. It showed phase runs with a generic Runs label.

| Scope | Archive runs |
| --- | ---: |
| Death phase, screenshot window | 114 |
| All phases, same window | 2,073 |
| IPL 2024, all phases | 741 |
| IPL 2025, all phases | 657 |
| IPL 2026, all phases | 675 |
| All supplied IPL records through 2026-05-31 | 9,336 |

The three season totals match the RCB primary pages linked in official_validation.csv. Recency weighting did not reduce these raw totals. The 114 is a correct phase sample, presented too ambiguously for a user expecting a career total.

The corrected dossier starts with Player overview. That view uses all phases within the chosen competition's supplied coverage. Use active research filters deliberately switches to the scoped sample and explains the all-phase total in the same date window. Labels distinguish archive runs from phase runs. Named-record appearances include matches with no relevant phase balls; a separate explanation reports relevant phase appearances. The scouting minimum-ball threshold does not hide dossier records.

## 2. What was checked completely

- All five uploaded archives: hashes match the recorded inputs.
- 6,392 included matches and 1,455,366 deliveries.
- 141,377 player-match rows; 3,393,048 independently recalculated field comparisons, zero mismatches.
- 6,618 archive player IDs: all retained in the registry, with supplied raw aliases preserved; no duplicate player-match rows or display-name mapping disagreements.
- 27,236 player/competition/season groups: 163,416 checks that phase totals sum to full totals, zero mismatches.
- 144 scouting settings across competitions, phases, disciplines and historical cutoffs: no sample-threshold, finite-rate or duplicate-group failures.

These checks demonstrate consistency with the uploaded archive. They do not establish that every official match was supplied or that the raw third-party archive is error-free. Six innings used the documented fallback for missing powerplay metadata. Death remains an analytical phase, not an official field-restriction label.

## 3. What was compared with official sources

A dated sample of 194 numeric fields from 15 primary pages covers all ten IPL teams and all five archive competitions. It includes six IPL match reports, all ten 2026 league-stage played/won/lost/no-result/points records, season leaders, the three Kohli IPL seasons, seven India T20I career checkpoints, a BBL final, Hundred season leaders and a SMAT quarterfinal.

Results: 188 matches, five coverage gaps and one conflicting figure. The comparison CSV retains every failure and source URL. Net run rate was not independently reconstructed. This is a sample of external facts, not official verification of every player or match.

| T20I player | Archive runs before 2024-07-01 | ICC reference runs | Missing from archive total |
| --- | ---: | ---: | ---: |
| Virat Kohli | 3,963 | 4,188 | 225 |
| Rohit Sharma, India identity | 4,027 | 4,231 | 204 |
| Yashasvi Jaiswal | 430 | 502 | 72 |
| Shubman Gill | 312 | 335 | 23 |
| KL Rahul | 2,134 | 2,265 | 131 |

Reference: [ICC, India's opening options after Kohli and Rohit retired](https://www.icc-cricket.com/news/india-s-big-conundrum-at-the-top-who-replaces-rohit-and-kohli-in-t20is), 30 June 2024. The other two ICC checkpoints matched. The SMAT 2024/25 sample contains only eight matches, so it must not be presented as a complete tournament.

One unresolved conflict: [IPL's GT–CSK match report](https://www.iplt20.com/news/article/tata-ipl-2026-match-66-gt-v-csk-match-report) gives Anshul Kamboj 57 conceded, while the archive gives 56. A separately retrieved [Cricbuzz bowling record](https://m.cricbuzz.com/player-match-highlights/152229/1/14598/bowling) also shows 56. The official dynamic scorecard did not expose the bowling rows to this audit. Preserve 56 with the conflict recorded; obtain the official final bowling card before deciding whether either source needs correction. Do not add a run merely to match article prose.

## 4. Identity reliability

Three different registry IDs share the display name Rohit Sharma. Automatically choosing the first result could select a different cricketer. The dossier now requires an explicit choice when several identities match and shows IDs, competitions and observed teams. A confirmed India Rohit ID is 740742ef. Different people remain separate.

The registry preserves archive aliases but is not a complete external full-name register. Some international players are searchable only by initials or a source alias; use the registry ID where needed. This remains a usability and verification gap. Unknown squad identities cannot borrow another player's totals.

## 5. All-ten-team analyst scenarios

Each team received nine cases: default plan, leading scheduled bowler excluded, stronger spin/pace minima, a priced budget, impossible budget, all players excluded, conflicting lock/exclusion, shuffled input order and too many overseas locks. Fifty of ninety requests supported a legal XI; the remaining requests were rejected with reasons. No successful plan violated the independent checks.

Every one of 257 supplied pool entries was also forced in a separate selection request. There were 214 supported requests and 43 rejections. A rejected unobserved or unavailable player is an appropriate result, not a missing test. All successful plans respected eleven distinct players, a keeper, at most four overseas players, locks, exclusions, budget, twenty overs, 120 legal balls, no consecutive overs and workload/phase caps.

| Team | Supplied pool rows | Overseas pool rows | Selected dated notices | Missing documented replacements | Supported scenario cases |
| --- | ---: | ---: | ---: | ---: | ---: |
| CSK | 26 | 9 | 2 | 1 | 5/9 |
| DC | 25 | 8 | 0 | 0 | 5/9 |
| GT | 26 | 7 | 1 | 0 | 5/9 |
| KKR | 28 | 9 | 2 | 0 | 5/9 |
| LSG | 25 | 7 | 1 | 1 | 5/9 |
| MI | 25 | 8 | 3 | 3 | 5/9 |
| PBKS | 25 | 8 | 0 | 0 | 5/9 |
| RCB | 25 | 8 | 2 | 1 | 5/9 |
| RR | 26 | 9 | 2 | 1 | 5/9 |
| SRH | 26 | 9 | 1 | 0 | 5/9 |

A pool can contain outgoing and replacement records together. These row counts are not certified registered squad sizes. Fourteen primary-source notices now block documented outgoing players after publication and existing replacements before their join date. Capability assumptions cannot undo those blocks. The pool is missing verified metadata for Akash Madhwal, Emanjot Chahal, Krish Bhagat, Mahipal Lomror, Ruchit Ahir, George Linde and Richard Gleeson. Notices and URLs are in roster_status.json. Remaining availability, NOCs, reinstatements and registrations still require review.

The model supports a 2026 research pool, including recorded dated trades. Other seasons need independently reviewed roster inputs. It does not certify every Impact Player or competition rule.

## 6. Agent behaviour and interface

Eleven adversarial requests tested an ignored exclusion, a historical season outside the window, singular middle-over wording, unsupported under-25 eligibility, a different matchup, two phases at once, a phase mismatch, wrong batting discipline, a different competition, a different XI franchise and an uncertified complete-career claim. The corrected workflow requests clarification for all eleven. Confirmed exclusions are actually removed; a correctly confirmed season, matchup or ambiguous-name ID remains usable. This is bounded request checking, not unrestricted natural-language understanding.

The regression suite exercises deterministic tools, source fingerprints, model-output rejection, provider fallback, request limits, session/franchise privacy, historical cutoffs, stale results, downloads and warm-process startup. All ten desks and all ten workspaces are exercised in Streamlit's runner. Additional dossier checks covered all 257 supplied pool entries through the real script runner, with 257 passes. Real Chromium checks cover rendered pages, exports, themes, reduced motion, mobile layout, private journal isolation and the corrected dossier/audit workflows. Exact results and tested versions are in release_checks.json and the accompanying audit CSVs.

Live hosted sessions and DeepSeek output quality were not certified in this environment. The hosted URL could not be interactively reached through the permitted tools. Tests ran the exact repository application locally; provider behaviour used controlled fixtures. A published commit is not proof of a successful Cloud rebuild.

## 7. Performance interpretation

The 144 scouting checks, 90 team requests, 257 forced-selection requests and eleven question probes completed together in about 39 seconds in the local test environment. Individual scenario timings are in audit_team_scenarios.csv. These are local functional timings, not a cloud load test or a service-level guarantee. Cached source loading and data reuse are covered by regressions. Cold hosting startup, many simultaneous users, API latency and production memory use need separate measurement.

## 8. Professional-use decision and priorities

1. Obtain missing match scorecards and review coverage per competition/season. A date endpoint is not a completeness certificate. Rebuild from corrected sources and rerun raw reconciliation; do not invent missing deliveries or overwrite archive totals with career references.
2. Complete a dated player/roster registry: verified IDs, full names, countries, keeper roles, registrations, replacements and availability. Add the seven missing replacements only after their planning metadata is checked.
3. Resolve source conflicts with final primary scorecards, keeping the discrepancy trail and source version.
4. Add reviewed scouting notes, video, actual tactical role/venue requirements and documented analyst judgments. The twenty supplied review tasks have no authenticated professional reviews yet.
5. Validate the hosted rebuild and permitted live provider calls; monitor failures, costs and latency. Add authenticated durable team access and backups before real collaborative use.
6. Retain the baseline forecast until a model beats it on untouched future periods. No validated forecasting or recruitment advantage is established.

Use the app to inspect evidence and rehearse decisions. Final recruitment, selection and availability decisions still need the analyst's verified current sources.

## 9. Reproduce the checks

Run `python -m unittest discover -s tests -v` from the project root. Run `python tools/verify_raw.py --source /path/to/raw-data` with the five exact archive inputs. Run `python tools/compare_official_checkpoints.py --output work/accuracy-audit` for the dated official numeric sample. That last command recalculates transcribed checkpoints; it does not fetch live records. Read the source URLs when refreshing the reference figures. Optional expanded checks are `python tools/check_workflows.py --output work/accuracy-audit` and `python tools/check_all_dossiers.py --output work/accuracy-audit`.

Download this report and the official comparison CSV from Evaluation & sources → Accuracy audit. The complete source ZIP contains the tests, detailed audit CSVs, evidence summaries and this report. The main project guide describes the corrected product and how to run it step by step.
