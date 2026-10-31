# Player Scout — Phase 3

The dev branch adds one DeepSeek specialist to Player Profile. Pandas continues to calculate all statistics. Generating a report sends only the visible player's evidence packet to DeepSeek, including selected competition, date coverage, calculated facts, a recent sample and limitations.

## Enable it

1. Install the updated `requirements.txt`.
2. In the dev Streamlit app, open Settings → Secrets. Locally, use `.streamlit/secrets.toml`.
3. Set your private credentials there:

```toml
DEEPSEEK_API_KEY = "your-private-key"
DEEPSEEK_MODEL = "deepseek-flash"
```

The model setting is optional. Never commit the actual key. Existing analytics work without credentials.

4. Open Player Profile and select a player and competition.
5. Inspect “Evidence sent to the scout,” then click “Generate Scouting Report.”

## What happens

- The packet uses the complete selected loaded sample for aggregates and a maximum of ten recent dated records for detail. Its source fingerprint covers the complete selected loaded records, rather than the original archive ZIP.
- The client uses `https://api.deepseek.com`, a forty-five-second timeout, no automatic retries, non-thinking mode and a bounded output request. One uncached click makes one API call. API charges depend on current DeepSeek pricing.
- The response must contain JSON observations, tentative interpretations, limitations and review actions. Findings must cite known fact IDs. Unknown fields, missing citations, duplicate JSON keys, numerical prose, blank responses and truncated responses are rejected.
- Python renders cited numerical facts. The model supplies qualitative prose. Required source limitations remain visible even if omitted by the model.
- A successful report is saved only in the current browser session. Repeated generation for the same context reuses that report. Player, competition, evidence, model and prompt-version changes invalidate the saved report display. Failed requests preserve the analytical dashboard.
- Output validation checks structure and evidence references. It does not prove that every qualitative statement is supported, establish tactical benefit or guarantee factual accuracy. Independent analyst review remains necessary.

## Validation and limits

Provider fixtures test valid/invalid JSON, references, timeouts, authentication and other failure paths. UI checks cover report generation, cached reuse, stale results, missing credentials and the existing workspaces. These checks do not certify live API connectivity or model report quality; verify those using your privately configured dev deployment.

Run the focused checks from the repository root:

```text
python -m unittest discover -s tests -p test_scout_agent.py -v
```

DeepSeek references:

- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/guides/json_mode/
- https://api-docs.deepseek.com/guides/thinking_mode/

## If the hosted app reports a missing OpenAI module

The `openai` package is listed in the root `requirements.txt`. Changes to that file trigger Streamlit's dependency installation process. Check the dev deployment's build logs for installation errors, then reboot the dev app if it still shows an old error. The app imports the optional SDK only after a scouting request, so statistics and navigation remain available while that dependency is unavailable. A missing key is a separate configuration issue handled through Streamlit Secrets.

## Debugging report formatting

The parser accepts a single enclosing Markdown code fence, optionally labelled `json`, as well as plain JSON. It preserves backticks inside JSON string values. Extra prose and invalid report structures remain rejected.

When JSON parsing or schema validation fails, the dev UI shows the original completion text in an error panel. A configured API key is redacted if it appears in that text. Provider transport error bodies are not printed. The normal validation error identifies an incorrectly typed section or an exceeded list limit. Debug output is not saved as a successful scouting report.
