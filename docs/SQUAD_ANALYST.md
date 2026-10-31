# Squad Analysis and Squad Analyst

Squad Analysis adds a franchise selector, a clean table of the supplied squad rows, primary role counts, and domestic/overseas counts. It uses `franchise_id`, `team_name`, `player_name`, `role`, `is_overseas` and `is_wicketkeeper`. Editable mappings and expected primary-role labels are at the top of the workspace block.

## Source meaning

The CSV is a supplied snapshot, not a verified current registered squad. It has no snapshot date and may include outgoing players or replacements. Registration, eligibility, availability and roster completeness require current verification. Pool size is not a certification of competition compliance.

Each source row is retained as a listed entry. Repeated placeholder registry IDs do not cause different named players to be merged. Missing and repeated names are counted explicitly; distinct names are not certified unique identities.

Origin uses only `is_overseas`: zero maps to Domestic, one to Overseas, and missing or other values to Unknown. Nationality and names do not fill unknown flags. Roles retain source labels; missing labels appear as Not recorded. Configured role labels without entries show zero, which does not prove absent capability. Wicketkeeper flags overlap primary roles and are not added to role totals.

## Generate a report

1. Open Squad Analysis and select a franchise.
2. Review the snapshot, role counts and origin counts.
3. Inspect the evidence packet, then click Generate Squad Report.

The packet contains listed-player counts, role distributions, origin distributions, keeper flags, roster metadata, fact IDs, a selected-source fingerprint and mandatory limitations. The agent uses the existing private DeepSeek secret, bounded SDK request and shared JSON parser, fifteen-entry section validation, citation checks, debug output and error handling. No new key is needed.

Observations describe supplied composition. Tactical interpretations must remain tentative and cannot invent current eligibility, skill, pace/spin specialisms, batting positions, workloads, a legal XI or forecast performance. Unknown metadata and overlapping capabilities must be acknowledged. All source limitations remain visible independently of the model's summary.

The report has its own browser-session cache. Franchise, source, model and prompt-version changes invalidate the displayed report. No call is made merely by changing the franchise. Failures preserve the squad table. The agent runtime checks the new exports, and the UI also checks its full required interface to handle partially updated agent releases without losing statistics.

Run focused checks from the repository root:

```text
python -m unittest discover -s tests -p "test_*agent*.py" -v
```

Tests use mocked provider responses and supplied data. They do not certify a live cloud rebuild, live report quality or professional tactical usefulness.
