# Boundary — integrated franchise analyst & scouting capstone

One application includes data provenance, scouting and comparisons, observed uncertainty, exact XI and budget scenarios, evaluated match probabilities, a DeepSeek tool-calling analyst, decision history, quantitative checks, qualitative review forms, SWOT and project documentation.

## Deploy on Streamlit Community Cloud

1. Open https://share.streamlit.io/ and create an app from this repository.
2. Repository: `br-abishek-07/boundary-cricket-capstone`; branch: `main`; main file: `app.py`.
3. Advanced settings: select Python 3.12 and add `DEEPSEEK_API_KEY = "your-provider-key"` to Secrets.
4. Deploy, then open Settings → Test provider connection.

The processed database and model are included; no file uploads are needed. For download, use GitHub Code → Download ZIP.

## Start

Python 3.11 or 3.12 is recommended. Run `start.sh` on macOS/Linux or `start.bat` on Windows. These create a local virtual environment, install dependencies, and launch Streamlit.

Or run manually:

```bash
pip install -r requirements.txt
streamlit run app.py
```

The processed database and trained research model are included. No GPU or paid dataset is required. This public repository contains no API key. On Streamlit Community Cloud, set `DEEPSEEK_API_KEY` in Advanced settings → Secrets. For local use, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and insert your own key. The real secret file is ignored by Git and is never sent as prompt text.

Live DeepSeek host access is blocked by the build environment's outbound policy, so authentication and live answer quality were not verified. On your local computer, open Settings → Test provider connection. A successful response verifies connectivity/authentication, not analytical quality.

## Workspaces

1. Decision desk: DeepSeek chooses approved scouting, dossier, XI and prediction tools, then produces a cited brief with an inspectable trace. Saved demonstration mode never calls the provider.
2. Scouting & comparison: competition, batting/bowling, phase, match-date window, minimum samples, literal search, CSV export and up to three candidate comparisons.
3. Squad & auction scenarios: exact solver, exclusions, locked players, role constraints, optional editable scenario costs and an XI budget. Prices default to explicitly labeled placeholders; they are not model valuations.
4. Player dossier: dated match records, season tables, trend chart, match-bootstrap observed-rate intervals and historical auction lookup.
5. Match research: pre/post-toss probabilities using the evaluated feature/model pipeline, holdouts, calibration, baselines, season results and uncertainty.
6. Decision journal: save and export briefs and scenarios with their evidence/settings.
7. Evaluation & SWOT: real automated results, qualitative review form, source manifest and project strategy.
8. Settings: private key status, session override, provider connection check and operational limits.

## Verify

```bash
python tests/test_core.py
python tests/test_ui.py
```

Build results: 37 offline behavioral checks and 12 Streamlit workflow checks passed; desktop/mobile browser rendering was inspected. These do not prove live DeepSeek factuality or expert tactical usefulness. No expert ratings have been invented.

## Data and reproducibility

Five uploaded Cricsheet archives yield 6,392 eligible men's matches and 141,377 named player-match records. Women’s fixtures, the voided IPL fixture 1473495 and duplicate match IDs are excluded. The source manifest records raw ZIP hashes and dates. IDs come from match registries; squad display names override aliases. Squad snapshots and old auction data need independent verification.

Raw ZIPs are not bundled. To rebuild from your uploaded archives:

```bash
python match_data.py --source /path/to/attachments --output data
python prediction.py
python tests/test_core.py
python tests/test_ui.py
```

`--source` searches recursively. Dataset fields are never executed as instructions. The integrated release uses match-level records throughout.

## Analytical methods

Scouting: sample-weighted 120-ball shrinkage toward the selected pool's rate. Batting score is shrunk runs above the pool per 100 balls; bowling is runs saved per six balls. Mixed competitions are not strength-adjusted. Phase boundaries use full-format rules, not rain-adjusted conditions. Hundred powerplay is the first 25 balls; death is the final 20 balls; economy is normalized to six balls.

XI: maximize a role-weighted descriptive utility with 11 selections, at most four overseas, at least one keeper and configurable batting/bowling options. Batting utility = score/10 for batting roles; bowling utility = bowling score for bowling roles; all-rounders count in both. Missing evidence receives -1 utility. This is a planning solver, not complete official eligibility or Impact Player certification. Budget constraints use user scenario costs only.

Uncertainty: 400 seeded match-level bootstrap resamples of observed rates; this is not an interval for future performance. Windows in scouting use actual match dates; dossier intervals explicitly use all dates before cutoff.

Predictions: regularized zero-intercept logistic models trained on IPL before 2023, validation in 2023, untouched test from 2024. Past Elo, form and venue chase history update only after each match date. Fixed settings were not tuned on test results. One feature function serves evaluation and live scenarios. Current forecasts use the latest rating snapshot; older as-of live scenarios are disabled.

Test results: post-toss accuracy 54.88% on 215 matches, Wilson 95% interval 48.20–61.39%, Brier 0.248129; constant-50% forecast Brier 0.25. This modest result does not establish a reliable predictive advantage. No lineup, weather, injury or pitch inputs are modeled. Classifying a 50% forecast breaks ties toward Team A; that baseline's observed accuracy is not the expected accuracy of a random coin flip.

## DeepSeek, storage and cost

The analyst allows at most three provider requests per brief, four tools per tool-enabled turn and 1,100 output tokens per request. A local SQLite ledger permits thirty provider requests per UTC day across sessions. Repeated identical briefs are cached against source/squad fingerprints and model weights. One deployment replica has its own ledger. Input tokens are billed too; this is an operational allowance, not a guaranteed rupee cap. Use provider billing controls and authentication before unrestricted public access. ₹300–₹1,000 is a suggested experimentation allowance, not a vendor quote.

`.runtime/` stores local decisions, reviews, cache and usage. It is excluded from delivery. Storage on free hosting can be ephemeral; export important work. This capstone is intended for a trusted single-user demo. Multiuser access control, global cross-replica accounting and a remote durable database are not implemented.

## Deliverables

- `docs/Capstone_Report.pdf` and `.docx`
- `docs/Capstone_Presentation.pptx`
- `docs/USER_GUIDE.md`, `docs/PLAN.md`, `docs/previews/`
- Actual test, UI, prediction and source reports under `data/`

Source data may have redistribution requirements: inclusion in this upload is not a grant of data rights. Review source terms before making the complete repository public.
