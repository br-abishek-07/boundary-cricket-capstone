# Matchup Analyst — Phase 3

The Team Matchups workspace uses the same private DeepSeek configuration as Player Scout. No additional API key is required. SDK loading remains lazy, so statistical workspaces operate without the optional provider client.

1. Select a competition, two different teams and a venue.
2. Inspect the head-to-head metrics and recent encounters.
3. Open “Inspect evidence sent to the Matchup Analyst.”
4. Click “Generate Matchup Report.” One uncached click makes one bounded provider request.

The packet contains overall results, up to five recent dated encounters, selected-venue results, win percentages, source fingerprints and explicit limitations. Recent outcome labels have their own fact IDs. Venue percentages divide team wins by all encounters between that pair at the exact selected venue label, including encounters without a recorded winner. An unobserved venue produces unavailable percentages, not a fabricated zero-percent rate.

No recorded winner does not certify a tie or no-result. Missing margins remain unavailable. Source naming variants are kept separate. The model receives no current lineup, fitness, pitch or weather evidence. Historical rates do not establish a causal venue advantage or forecast future outcomes.

The specialist returns observations, tentative interpretations, limitations and review actions in the same checked JSON structure as Player Scout. Both agents share the API client, code-fence preprocessing, strict schema and fact-reference checks, raw completion debugging, key redaction and sanitized provider errors. Numerical and categorical facts are displayed from Python's evidence packet. Qualitative interpretations still need human review.

Reports are saved separately from Player Scout in the current browser session. Changing teams, competition, venue, source evidence, model or prompt version invalidates the displayed report. Repeating the same request reuses its saved report. Pairs with no observed encounters cannot request a report. Failed requests retain the statistical dashboard.

Run the focused regressions from the repository root:

```text
python -m unittest discover -s tests -p test_scout_agent.py -v
python -m unittest discover -s tests -p test_matchup_agent.py -v
```

Provider fixtures validate request/response handling and UI behaviour. They do not certify live DeepSeek connectivity or tactical quality. Test live generation separately in the privately configured dev deployment.
