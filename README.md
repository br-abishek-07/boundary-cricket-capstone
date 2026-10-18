# CreaseIQ — franchise research studio

**The name:** Crease refers to the markings on a cricket pitch. IQ stands for intelligence. CreaseIQ turns cricket evidence into informed decisions, with the analyst in control.

An IPL analyst capstone with traceable scouting comparisons, player dossiers, a legal twenty-over XI planner, optional DeepSeek fact selection, research baselines and private session journals.

## Run

Use Python 3.11+ (3.12 recommended).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Start on Home. Load the RCB death-bowling example or MI unavailable-bowler scenario. Local evidence requires no API key. For optional DeepSeek selection, copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` and add your own private key. On Streamlit Cloud, use hosting Secrets. Never commit a real credential.

## Understand and reproduce

Read [the step-by-step project guide](docs/USER_GUIDE.md). PDF, Word and a safe complete source ZIP are also downloadable from Home and Project guide inside the app. [Data sources](docs/DATA_SOURCES.md) explain provenance. Run `python -m unittest discover -s tests -v` for offline checks.

The supplied archives include 6,392 men's matches. IPL ends on 31 May 2026; other source endpoints vary. This is frozen historical coverage, not a live feed. Squad verification is partial. Descriptive scores are not valuations or future-performance guarantees. The research forecast fails its stronger-baseline gate, so the app serves the historical baseline.

The engine fixes the task and filters before calculation. DeepSeek can select only retrieved fact IDs and approved actions. Complete XI/player facts cannot be omitted. Briefs become stale when context or sources change. Export packs preserve assumptions, dates, version and source fingerprints.

For deployment, select repository branch `main`, entry file `app.py`, Python 3.12 and private hosting secrets. Confirm the hosted rebuild and live provider connection separately from local tests. Educational project; no IPL or franchise endorsement.

Read [the accuracy audit](docs/ACCURACY_AUDIT.md) for exhaustive archive checks, all-team scenarios and sampled official-source comparisons. Player dossier defaults to a labeled archive overview; phase totals and incomplete career coverage are explicit. Selected dated 2026 unavailability notices block XI selection, while missing replacement metadata remains visible.


## Public app and capstone submission

- [Open CreaseIQ](https://creaseiq.streamlit.app/)
- [Download the complete capstone submission ZIP](https://github.com/br-abishek-07/creaseiq-cricket-capstone/raw/refs/heads/main/submission/CreaseIQ_Capstone_Submission.zip)
- [Browse the presentation, report and supporting files](https://github.com/br-abishek-07/creaseiq-cricket-capstone/tree/main/submission)

The submission is prepared for B.R. Abishek, AI Driven Data Science. It includes editable presentation/report files, PDF copies, runnable source, the user guide, evidence, abstract and demo/viva notes. Open `submission/START_HERE.md` for the file map. Private keys and runtime records are excluded.
