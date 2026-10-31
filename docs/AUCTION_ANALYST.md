# Auction Analyst — Phase 3

Auction Trends uses the same private DeepSeek key and model setting as Player Scout and Matchup Analyst. No additional secret or package is required.

1. Choose an auction year or All Time.
2. Review the dashboard's top recorded buys, franchise totals and category distributions.
3. Inspect “Evidence sent to the Auction Analyst.”
4. Click “Generate Auction Report.” One uncached click makes one bounded request.

The evidence packet uses the same selected records and Pandas calculations as the dashboard. It contains sample counts, top ten individual source records, all observed franchise totals, available role/origin distributions, amount shares and fact IDs. All Time includes the supplied row with no year; individual-year selections exclude it. Unusable amounts are excluded and counted explicitly. Empty categories are retained as Not recorded so totals reconcile. Genuine zero totals produce unavailable percentage shares.

Amounts remain unverified source units. The file does not document currency or transaction types, so the agent cannot certify winning bids, official purse spending, retentions or transfers. There is no inflation adjustment, current-price feed or basis for asserting bargains, overpayment, recommended bids or future value. Top buys rank individual records, not distinct players or lifetime earnings. All Time is a pooled view, not a measured time trend. Role and origin breakdowns describe the same money and must not be added together.

The agent shares the existing SDK client, timeouts, Markdown-fence JSON parsing, fifteen-entry section limits, citation checks, sanitized provider errors and raw completion debugging. Its evidence is bounded to eighty facts and the shared payload size cap; the full current All Time packet fits those bounds. Required source limitations remain visible independently of the model response.

Auction reports have a separate browser-session cache. Changing the year, evidence, model or prompt version invalidates the displayed report. A selection without usable amounts cannot request a report. Failures retain the statistical dashboard. Output validation checks structure and references, not whether every qualitative interpretation is supported; review conclusions independently.

Run focused provider and UI regressions:

```text
python -m unittest discover -s tests -p test_scout_agent.py -v
python -m unittest discover -s tests -p test_matchup_agent.py -v
python -m unittest discover -s tests -p test_auction_agent.py -v
```

These tests mock provider responses. Validate live report quality separately using the privately configured dev app.
