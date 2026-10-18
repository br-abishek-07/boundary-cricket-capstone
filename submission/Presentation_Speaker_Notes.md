# CreaseIQ presentation speaker notes

B.R. Abishek · AI Driven Data Science · v3.1.0

## Slide 01 — CREASEIQ

Introduce yourself as B.R. Abishek. CreaseIQ is an independent educational franchise research studio. Crease refers to the markings on a cricket pitch; IQ stands for intelligence. The name means cricket evidence supporting informed decisions, with the analyst in control. Its users are analysts and scouts who need a clear route from a cricket decision to inspectable evidence. This presentation explains application version 3.1.0. It uses the released source and documented local acceptance results. Do not describe it as an official IPL product, an autonomous team manager, or a proven match-winning system.

## Slide 02 — Start with a decision, not a dashboard.

Explain the concrete operational problem. A coach asks for death-bowling options, but a list of career wickets does not describe death-over evidence, availability or the missing overs in a proposed XI. CreaseIQ keeps those distinctions visible. The scope is historical research and scenario rehearsal. It does not replace current registration checks, video review, coaches or the analyst’s judgment.

## Slide 03 — Four contributions, one inspectable workflow.

The contribution is the integration, not a claim that a language model invented better cricket statistics. The evidence engine performs calculations, the optimization engine checks a complete plan, and the optional model selects from already validated facts. Exports make the decision reproducible. No new foundation model was trained or fine-tuned for this project.

## Slide 04 — What an analyst can actually ask.

Map the four research tasks to real analyst questions. The franchise desk supplies the selected team context. Scouting considers observed evidence rather than confirmed acquisition availability. XI planning uses the supplied dated 2026 research pool. Player evidence requires a confirmed identity. Match research exposes a gated historical baseline. Keep the language “research option” distinct from a recommendation that a player can actually be signed or selected today.

## Slide 05 — Ten workspaces; a single research loop.

Walk through the navigation once rather than reading every page in detail. Home provides orientation and examples. Decision desk orchestrates checked briefs. Scouting ranks and compares. Squad scenarios solve legal schedules. Player dossier inspects records. Match research exposes the baseline and evaluation. Journal stores scoped decisions. Evaluation contains audits and review tasks. Project guide supports reproduction. Settings handles optional provider credentials and allowances.

## Slide 06 — Five archives. Coverage is a first-class feature.

All counts refer to eligible men’s matches in the supplied snapshot. There are 6,392 matches, 141,377 player-match rows and 6,618 archive identities. IPL extends through 31 May 2026, but SMAT ends in December 2024. A latest date is not proof that every match in the interval is present. The app does not update automatically. The historical auction CSV is a separate 2013–2022 manual lookup and is not a current price feed.

## Slide 07 — From deliveries to dated player evidence.

Describe match_data.py. Delivery records are aggregated by player and match, including phase components. Batter balls exclude wides under the source convention. Legal bowling balls exclude wides and no-balls. Bowler runs exclude byes and leg byes. Bowler wickets exclude run-outs and other non-bowler dismissal types. Powerplay uses supplied metadata with a documented fallback; Death is an analytical final fifth. The raw verifier is independent of the ingestion and analytics modules.

## Slide 08 — The calculation engine owns the facts.

Explain the layers in the diagram. Streamlit owns controls and presentation. The task-context checker compares the question with confirmed controls. Deterministic tools retrieve and calculate match, roster and model evidence. Validation checks identities, scope and schedule completeness. DeepSeek is optional and only selects existing fact IDs and approved next actions. Rendering is deterministic. SQLite stores scoped journal/cache/request counts; CSV and ZIP exports carry provenance. There is no vector database, LangChain dependency or unrestricted execution agent.

## Slide 09 — Question → evidence → check → human review.

The agent is an application-controlled research workflow. The analyst chooses Scouting, XI planning, Player evidence or Match research. The server validates competition, discipline, phase, dates, selected players, exclusions, franchise, matchup and budget where relevant. One deterministic tool runs for the task. Optional DeepSeek selection happens only after the tool has returned facts. The final brief is bound to the full context and source fingerprints; a changed context makes the previous brief stale.

## Slide 10 — A narrow model role is a deliberate design choice.

DeepSeek uses deepseek-chat, temperature zero and a constrained JSON response. Temperature zero is not a guarantee of identical external responses. Unknown IDs, model prose, incomplete responses and tool-call attempts are rejected. A complete XI cannot omit player facts and a player task cannot omit requested identities. Invalid or unavailable selection falls back to the supported local facts. No live model quality claim is made by the fixture tests. Keys remain in private hosting Secrets or a temporary password field, never the source package.

## Slide 11 — Orientation before analysis.

Use the actual local application screenshot to show the home page’s purpose. Loading an example sets structured controls and does not itself spend provider calls. The first recommended run uses Local evidence. Explain the evidence base before interpreting a player’s metric. The page provides entry points rather than a generic decorative dashboard.

## Slide 12 — Prepare a brief with its evidence attached.

A brief contains factual records rendered by the server, their sources, full context and approved next actions. Open the evidence trace during the demo. If a question requests under-25 eligibility, a different competition or an unconfirmed exclusion, the app asks for clarification rather than making an unsupported inference. A source or control change hides the old result until it is recomputed. “Evidence checked” means supported provenance and task agreement, not certified tactical usefulness.

## Slide 13 — Read the raw rate beside the score.

Scouting calculates transparent descriptive scores. Recent records receive more weight, with a 365-day half-life; a 120-ball prior shrinks small samples toward the scope average. The minimum sample uses batting balls or legal bowling balls as appropriate. A bowling score trades off economy and wicket-taking, so rank is not the same as sorting economy. ALL keeps competitions separate and does not translate league strength. Current availability and tactical fit require external review. The score weights have not been proven optimal.

## Slide 14 — A scope is part of every statistic.

Use Kohli to teach the difference between an archive total and a filtered sample. In the 18 October 2023 to before 18 October 2026 window, the archive has 114 Death-phase IPL runs and 2,073 all-phase runs. The all-supplied-IPL overview has 9,336 runs through 31 May 2026. The season totals 741, 657 and 675 match the RCB pages in the official comparison file. Do not call the 9,336 an independently certified complete career figure. It is labeled as the supplied archive. The minimum-ball scouting filter does not hide dossier records.

## Slide 15 — Names help search. IDs identify people.

The local registry preserves raw aliases but is not a complete external full-name register. Some players need initials or a source alias in the search. The selected India Rohit ID is 740742ef; this is not the only person with that display name. Current roster events are applied only after their published dates, with a strict exclusive cutoff. Do not imply that a roster cutoff creates a historical career record or that the latest source date certifies completeness.

## Slide 16 — Selection and the twenty overs are solved together.

SciPy’s mixed-integer optimization selects players and assigns every over jointly. Default planning uses IPL evidence from the previous three years, even when scouting controls show another competition. Selection maximizes the sum of explicit utilities; a second solve holds that XI fixed and improves the schedule using phase scores. Each successful plan receives an independent schedule validation. A legal feasible optimum under these assumptions is not a proven best tactical XI. Costs, curated styles and capability assumptions remain explicit.

## Slide 17 — A real scenario: MI without Jasprit Bumrah.

This schedule is calculated from the released 2026 research pool with Jasprit Bumrah explicitly excluded, one spin and two pace minimums, the default three-year IPL evidence and no price budget. The selected five bowlers each cover four overs in this example. The diagram shows all twenty overs, their phase and no consecutive overs for one bowler. It is a reproducible research scenario, not a claim of current match-day availability. Equivalent optimal schedules can differ; keep the manifest to reproduce the assumptions.

## Slide 18 — Make assumptions visible before solving.

Budget values are analyst assumptions, and the initial one-crore entries are placeholders. Every relevant available player needs a price when a budget is active. Capability overrides need a written reason and legal whole-over caps; unobserved players also need a finite utility assumption. They cannot remove a documented 2026 availability block. If a constraint set is impossible, the app returns an explanation instead of inventing a complete plan. Historical auction lookup stays manual because currencies, transaction types and identities need review.

## Slide 19 — A model must beat a credible baseline.

The model uses team Elo and exponential recent-result form. Post-toss features add chasing status and prior venue chase outcomes. Training is before 2023, validation is 2023 and testing is 2024 onward. All matches on a date are predicted before that date’s results update ratings. The current research model failed its stronger-baseline gate, so the displayed estimate is a training-derived baseline. Selecting a different XI does not change it, because player lineups are not model inputs.

## Slide 20 — Time order prevents future results leaking backward.

The model fit uses 946 eligible training matches before 2023. Validation has 73 matches, and the held-out test contains 215 from 2024 onward. Ratings update only after each match date. The training chase-rate baseline uses training history, not test outcomes. The model’s fixed regularization and constants were not tuned using the validation or test results. Nevertheless, the dataset is limited and repeated seasons and teams are dependent, so a single test score does not prove a durable future advantage.

## Slide 21 — The baseline remains the displayed estimate.

Read the exact Brier values. The research post-toss model scores 0.256489 on validation versus the baseline’s 0.257440, but on held-out test it scores 0.248577 versus the baseline’s better 0.247619. The gate requires improvement in both periods and therefore fails. Lower Brier is better. Both have about 54.88 percent threshold accuracy in the test; this shows why accuracy alone is inadequate. The pre-toss displayed 50 percent is a no-validated-edge baseline, not evidence that actual team strengths are identical.

## Slide 22 — Keep the reasoning, not just the answer.

Session/franchise scoping is tested, but it is not authenticated durable multi-user team access. Another fresh visitor cannot read this session’s records. Export work before closing or redeploying. Decision packs contain manifest.json and the data needed for the task; XI packs include schedule.csv, alternatives and checks. The context fingerprint changes when the question, scope, assumptions, version or calculation sources change. Source hashes identify an input version; they do not prove source truth.

## Slide 23 — A working studio, with clear visual hierarchy.

Describe the actual design choices rather than aesthetic adjectives. The selected desk has franchise colors and a bundled identification mark. Light and Dark modes use readable surfaces and a restrained hierarchy. Reduce motion and system reduced-motion preferences are respected. Tables remain stable; the sidebar preserves context; filtered totals and unsupported cases use explicit labels. The application has local desktop/mobile browser checks, not a completed accessibility certification or user study. Team logos identify the subjects of an educational project and do not imply endorsement.

## Slide 24 — The application explains how to reproduce it.

The user guide explains installation, data coverage, deterministic tools, formulas, legal schedule rules, model gating and deployment. The source download excludes actual credentials, runtime databases, environments and caches. Local mode has no API charge. Optional DeepSeek calls are limited to six per browser session per UTC day across desks and thirty per installation. A brief uses at most two calls. These are small-demo controls rather than authenticated user accounts or a hard currency cap. Live provider quality was not certified here.

## Slide 25 — Separate functional passes from source completeness.

There are 71 current automated tests and 58 local Chromium checks. The raw archive verifier independently recalculated 3,393,048 numeric fields from 1,455,366 deliveries with zero ingestion mismatches. The expanded audit tested 144 scouting settings, ninety team scenarios and 257 forced-player requests. All 257 dossier displays matched stored input totals or explicitly reported missing identities. These are different test units and must not be added into one artificial accuracy percentage. Local fixture and browser checks do not certify the hosted rebuild or external model quality.

## Slide 26 — Official comparisons reveal real coverage limits.

The sample contains 194 numeric fields from fifteen primary pages, spanning all ten IPL teams and five archive competitions. It produced 188 matches, five T20I coverage gaps and one unresolved conflict. Kohli has 3,963 T20I archive runs versus the ICC’s 4,188. India Rohit has 4,027 versus 4,231. SMAT 2024/25 has only eight supplied matches. Kamboj conceded 56 in the archive but an IPL article says 57; the final primary bowling card still needs review. Every discrepancy remains in the downloadable comparison file. This is not official verification of every player.

## Slide 27 — A supplied pool is not a certified current squad.

The supplied pool contains 257 rows and can include outgoing players and replacements together. Fourteen selected dated primary-source notices are applied. Seven documented incoming replacements lack verified planning metadata: Akash Madhwal, Emanjot Chahal, Krish Bhagat, Mahipal Lomror, Ruchit Ahir, George Linde and Richard Gleeson. The app names them instead of inventing country, keeper or eligibility metadata. Remaining registrations, availability, NOCs and reinstatements require review. A legal research plan does not certify current match eligibility.

## Slide 28 — RCB: shortlist death-bowling evidence.

Use this as the first demo. Start on Home and load the RCB example without a provider call. Confirm the exclusive cutoff. Prepare a Local evidence brief, open its trace and read raw metrics rather than just the first rank. A high-ranked player is not necessarily available to RCB; signing status is outside the observed-performance ranking. Save and download the pack. If the hosted service is unavailable, run the supplied source locally. Do not claim that a screenshot proves live DeepSeek intelligence.

## Slide 29 — MI: remove Bumrah and account for every over.

Explain why this is a stronger demo than displaying a static best XI. The scenario removes an important bowler and tests whether the rest of the research pool can still support a complete schedule. Read the assumption table and current-status warnings. The example’s supported result has twenty overs with no consecutive overs by one bowler. Then show an explicitly impossible condition and its explanation. Finish by exporting the plan and manifest. No recruitment or current-fitness claim follows from the solve.

## Slide 30 — A low-cost capstone, with optional API use.

Normal use needs the source ZIP, Python 3.11 or newer compatible Python, the listed packages and Streamlit. Python 3.12 is the tested recommendation. The source includes processed data, so the large raw archives are not required to run the app. Deploy main with app.py on Streamlit Community Cloud and add a private key only if using DeepSeek selection. Hosting may be free within current host limits; provider charges depend on actual current pricing and usage. No new paid dataset is needed to reproduce this release. Complete/live data and production team access would be separate work.

## Slide 31 — A credible capstone has visible trade-offs.

Strengths are traceable calculations, complete schedule constraints and reproducible exports. Weaknesses are frozen incomplete sources, partial roster metadata and heuristic scoring without proven tactical advantage. Opportunities include a dated verified registry, scout/video review and measured role/venue studies. Threats include stale availability, scope misinterpretation, provider instability and misuse of public demo allowances. Frame future work as research priorities, not features secretly completed in this release.

## Slide 32 — What remains before professional team adoption.

Prioritize evidence integrity before more decoration or model complexity. The app has twenty review tasks but zero authenticated professional reviews. Forecast superiority is unproven. A real deployment also needs reviewed source rights, access control, durable backups, operational monitoring and ongoing dated data updates. Full Impact Player and competition-rule certification are outside the current twenty-over model. These limits should appear in the submitted report so the claims match the evidence.

## Slide 33 — The deliverable is a reproducible decision process.

Conclude with the three substantive contributions: bounded evidence workflow, joint legal selection/scheduling and a reproducible decision record. The product supports understanding and testing rather than asserting a predictive edge. Point to the submitted report, source and evidence pack for details. Be ready to distinguish source consistency, complete official coverage, functional reliability and tactical usefulness; they are separate claims.

## Slide 34 — Questions, demonstration and reproducibility.

The repository and app URLs are included as clickable links. The frozen submitted application is version 3.1.0 at commit 1100cace6b820c278135189f8925d4d1e423b375. The hosted URL is provided for convenience; local tests do not certify the hosted rebuild. The package includes a source ZIP, user guide, current audit/evidence and demo instructions. Invite questions about the model gate, legal schedule, scope labels and data completeness.

## Slide 35 — Batting combines pace and dismissal risk.

Let R, B and D be recency-weighted runs, balls and dismissals. Let r0 and d0 be the weighted scope runs-per-ball and dismissal-per-ball baselines. The smoothed rates are (R+120r0)/(B+120) and (D+120d0)/(B+120). Score is 100 times the first rate’s difference from r0, minus 18 times 100 times the second rate’s difference from d0. Baselines are calculated separately by competition. This is a declared heuristic, not expected runs or proven optimal talent value.

## Slide 36 — Bowling combines control and wicket-taking.

Let C, L and W be recency-weighted conceded runs, legal balls and bowler-credited wickets. Let c0 and w0 be the weighted scope conceded-per-ball and wicket-per-ball baselines. Smoothed rates use a 120-ball prior. Score is 6(c0-c_smoothed) + 72(w_smoothed-w0). The wicket coefficient is 12 times the six-ball normalization. Recency weight is 2 raised to negative age-in-days divided by 365. Raw runs, balls and wickets remain unweighted in the display. A leader can have a worse raw economy because wicket rate, recency and smoothing affect the score.

## Slide 37 — An evidence weight is not a probability of success.

Sample weight is effective weighted relevant balls divided by that quantity plus 120. It approaches one with more recent relevant exposure, but is not the chance that a player will succeed. Observed-rate intervals resample relevant matches 500 times with a fixed seed; at least five relevant matches are needed. They describe the sampled observed mean under an independent-match assumption. Venue shifts, correlated matches and future tactical roles are not fully represented. Do not call these future-performance confidence scores.

## Slide 38 — The solver’s constraints are explicit.

Use binary x_i for a selected player and y_io for player i bowling over o. The main constraints select eleven players; assign exactly one bowler to each over; link y to x; limit every bowler to four overs and phase capacities; and prevent y_i,o + y_i,o+1 from exceeding one. Add keeper, overseas, role-minimum, lock, exclusion and optional budget constraints. Stage one maximizes the sum of utility times selection. Stage two fixes the selected XI and improves the phase-specific bowling schedule. Independent validation is separate from the solver’s constraint matrix.

## Slide 39 — The schema keeps evidence and assumptions apart.

match_players.csv.gz is the analytical player-match grain keyed by match ID and player ID, with totals and phase components. matches.csv.gz stores dates, competition, teams, venue, toss and result. player_registry.json stores names, preserved aliases and reviewed metadata. squads.csv and dated event/status files are planning inputs. Prediction artifacts and audit outputs remain separate. Unregistered planning IDs cannot be joined to an unrelated player. Frozen source hashes identify the version used in each exported decision.

## Slide 40 — A small stack with clear responsibilities.

The UI is app.py. creaseiq_runtime.py loads a coherent content-fingerprinted creaseiq_core package and invalidates data caches when code changes. analytics.py performs ranking and mixed-integer scheduling. agent.py validates context and optional model selection. prediction.py implements the chronological model and baseline serving. evidence.py fingerprints exports. storage.py handles scoped SQLite state and atomic limits. branding.py and downloads.py support design and safe source downloads. Pandas, NumPy, SciPy, Altair and Streamlit are the runtime dependencies.

## Slide 41 — Reject unsupported claims; preserve checked evidence.

Data and user text are treated as untrusted input. The model is not given code execution or a permission to alter player prices. Secret fields are masked and credentials are excluded from exports. The exact-task fingerprint prevents stale or mismatched briefs from being saved as current results. The public session design is deliberately limited; it does not provide authenticated authorization, durable cross-device teams or a hard financial spending cap. Logs and live provider behavior still require operational review in a real deployment.

## Slide 42 — The evidence can be rerun.

The source ZIP contains the full local test suite and processed data. The expanded workflow and dossier checks write detailed CSV/JSON evidence. Raw reconciliation needs the same five source archives identified by their SHA-256 values. The official checkpoint command recalculates values transcribed from linked primary pages reviewed on 18 October 2026; it does not fetch current official records. Preserve the frozen commit and manifests when reproducing results. The submission evidence logs contain the completed local results, not new claims of hosted or live-provider performance.

## Slide 43 — Trace the methods and the source claims.

Use the exact released source for formulas, rules and implementation. Use Cricsheet for the archive source and preserve the supplied hashes. Official_validation.csv links every primary numeric checkpoint, including ICC, IPL, RCB, Cricket Australia, BCCI and The Hundred. The guide and audit explain the limits of each comparison. Package and provider documentation are supporting references for technologies, not evidence of project performance. Team mark credits are preserved in assets/sources.json. No source-rights certification or league endorsement is implied.

## Slide 44 — What to hand in.

Submit the presentation in PPTX and PDF, the editable report and final PDF, the frozen source ZIP, guide, test evidence and demo/viva guide according to the institution’s portal. START_HERE.md maps every file. The abstract is included separately. Add institution-required signed declaration, supervisor certificate, approval form, contribution statement or prescribed front matter only with the proper information and signatures. No such approvals, signatures, student register number or academic integrity claims have been fabricated. Check the repository and hosted demo before the actual review.