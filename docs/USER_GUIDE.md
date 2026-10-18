# Boundary user guide

## Launch and connection
Extract the private integrated bundle. Use start.sh or start.bat, or install requirements and run `streamlit run app.py`. Open the local URL shown in the terminal. The private server key is configured in this bundle; Settings lets you check the connection or override it for a session. Live analysis needs outbound HTTPS access to api.deepseek.com and an active funded API account. Demonstration mode and all numerical tools run without API access.

## Demonstration route (approximately 8 minutes)
1. Decision desk: explain the question-to-tool-to-brief workflow. Choose Saved demonstration if network access is unavailable; clearly label it as a saved example.
2. Scouting: select IPL, Bowling, Death, 120 minimum balls. Compare two candidates. Discuss score, sample weight and the lack of future-performance guarantees.
3. Dossier: inspect a player by registry ID, their seasons, match records and bootstrap interval. Explain that rate uncertainty and a predictive interval are different.
4. Squad: exclude a first-choice player; lock a replacement; apply custom scenario prices and a budget. Show both a feasible solution and a budget too small for 11 players.
5. Match research: show research probabilities and 2024–2026 holdouts. Quote uncertainty and the constant-probability Brier baseline.
6. Journal: save a scenario or live brief and export it. A saved demo is not a live AI result.
7. Evaluation: show actual automated checks, source hashes, SWOT and the qualitative review form. Do not claim expert validation until reviewers submit real assessments.

## Useful analyst questions
- Find IPL death-bowling candidates with at least 120 relevant balls and compare the evidence.
- Compare a named player's batting and bowling samples. What cannot be concluded?
- Rebuild the selected franchise XI excluding a player, without claiming the exclusion is a verified injury.
- Explain why current auction prices cannot be inferred from the supplied historical file.
- Compare pre/post-toss research forecasts for two franchise codes and explain model limitations.

## Cutoff and interpretation
The sidebar uses an exclusive match-date cutoff. All scouting records are match-level, so later matches are excluded. The squad snapshot remains fixed and is not historically reconstructed. Current model snapshots cannot be used to answer earlier live as-of prediction requests; use the holdout CSV instead.

Sample weight is n/(n+120), not probability of success. Scores are comparative heuristics. Combined-league rankings do not adjust opposition or format strength. Bootstrap intervals summarize observed pooled rates under an independent-match assumption. Auction fields are source values with unverified units and transaction type. Budget costs are explicit scenario assumptions.

## Operating safely within a small budget
Prefer local workspaces for exploration. Submit a narrow analyst question once; repeated identical requests use cache. Inspect token usage in the trace. The application limits local-installation requests to thirty per UTC day. It does not replace provider billing controls. Never paste the private key into a question, report or screenshot. Public hosting should restrict access or stay in demonstration mode until deployment controls are configured.

## Troubleshooting
- Missing dependencies: install with the same Python interpreter used to launch Streamlit.
- Missing secret after deployment: add DEEPSEEK_API_KEY in hosting secrets, not source files.
- HTTP 401: verify the key/account with the provider. The app suppresses response bodies to avoid leaking sensitive details.
- HTTP 403/network unavailable: check destination policy or hosting outbound access; do not assume the key is invalid.
- Infeasible XI: review exclusions, locked selections, role counts and scenario budget.
- Empty shortlist: widen the time window, reduce the sample threshold or check cutoff.
- Lost journal after redeploy: import is not implemented; retain exported JSON for your records and presentation.
