# CreaseIQ — capstone submission

**B.R. Abishek · AI Driven Data Science**  
Prepared 18 October 2026 · Application v3.1.0.

This is a complete technical submission package for the corrected released application. It uses a custom CreaseIQ editorial design, real local screenshots and editable diagrams. The deck has 44 slides: 34 main slides and ten technical appendix slides. Speaker notes are embedded in the PPTX and supplied separately. The project report has 27 pages, the abstract one page, and the demo/viva guide six pages. The user guide is the released step-by-step explanation.

## Files to submit

| Package folder | Files | Why it is included |
| --- | --- | --- |
| 01_Presentation | PPTX, PDF, speaker notes | Editable viva presentation, portable reading copy and complete explanations. |
| 02_Project_Report | Report DOCX and PDF | Problem, objectives, requirements, architecture, data, agent logic, formulas, optimization, evaluation, UX, deployment, SWOT and references. |
| 03_Source_Code | Frozen source ZIP | Runnable code, processed data, requirements, tests, assets, guide and reproducible tools. |
| 04_User_Guide | Guide PDF and DOCX | Simple-English setup, use, DeepSeek configuration, methods and reproduction. |
| 05_Validation | Evidence ZIP | Completed tests, audits, official comparisons, model/role studies and examples. |
| 06_Demo_and_Viva | Guide PDF and DOCX | Suggested presentation route, two live demos, examiner questions and submission checklist. |
| 07_Abstract | Abstract PDF and DOCX | One-page overview for a separate abstract upload. |
| Root | START_HERE.md, manifest, hashes, validation | File map, provenance and integrity verification. |

For a portal asking for only the main deliverables, submit the presentation, final report PDF and frozen source ZIP. Include the user guide and validation evidence as supporting material. Use the institution's actual submission rules for file formats, size limits, declarations and certificates.

## Before final submission

1. Confirm the author is **B.R. Abishek** and project area **AI Driven Data Science**.
2. Add actual register number, institution/department, guide and academic year if the college requires them. They were not supplied and have not been invented.
3. Obtain any prescribed signed certificate, declaration or approval form using the correct institutional process. No signature, approval or declaration of unaided authorship is fabricated here. Follow the course rules for assistance and contribution statements.
4. Open the PPTX and PDF. Use speaker notes for the detailed explanation; use appendix slides for the viva.
5. Extract the source ZIP into a clean folder and run the local application. Check required demo links separately before the review.
6. Keep a local demonstration ready. If a video is required, record the two workflows in the demo guide; no demonstration video is fabricated.
7. Keep credentials private. Actual API keys and private runtime journals are excluded from this package.

## Run the frozen source

The inner source ZIP extracts into `creaseiq/`. Open a terminal in that folder, where `app.py` is located.

```text
python -m venv .venv
```

Windows: `.venv\Scripts\activate`  
macOS/Linux: `source .venv/bin/activate`

```text
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Use tested Python 3.12 or a compatible Python 3.11+. Local evidence needs no API key. Processed data is bundled; the large five raw archives are needed only for exact raw reconciliation. To enable DeepSeek, follow the private Secrets steps in the guide. Never insert a real key into a report, slide or public source file.

Run the core tests with `python -m unittest discover -s tests -v`. See the report appendix for expanded workflows, all dossiers, official checkpoints and raw verification.

## Demonstration route

Start with Home → Load RCB example → Local evidence → Prepare brief → evidence trace/export. Then Home → Load MI scenario → Squad & auction scenarios → Over-by-over plan → counterfactual or impossible budget. Show the Kohli archive/phase distinction and the failed forecast baseline gate. The demo guide gives the exact steps and direct viva answers.

## Claim boundaries

Recorded results are 71 automated passes, 58 local browser checks and zero raw-ingestion mismatches across 3,393,048 comparisons. The official sample has 188 matches, five coverage gaps and one unresolved conflict out of 194 numeric fields. These do not certify complete careers, current rosters, live provider quality, a hosted rebuild or professional tactical advantage. Do not turn the counts into a single “AI accuracy” percentage.

The project uses historical source evidence and explicit assumptions. DeepSeek optionally selects existing fact IDs; the server performs calculations. The current forecast is the accepted historical baseline because the research model failed its stronger-baseline gate.

## Links and version

- Repository: https://github.com/br-abishek-07/creaseiq-cricket-capstone
- Frozen application: https://github.com/br-abishek-07/creaseiq-cricket-capstone/tree/1100cace6b820c278135189f8925d4d1e423b375
- Hosted application: https://creaseiq.streamlit.app/
- Detailed accuracy audit: https://github.com/br-abishek-07/creaseiq-cricket-capstone/blob/1100cace6b820c278135189f8925d4d1e423b375/docs/ACCURACY_AUDIT.md

The hosted link is a convenience, not proof of live-service validation. Source/data/asset credits are preserved in the frozen source and evidence ZIP. This independent educational project does not imply league or franchise endorsement.

## Integrity

`SHA256SUMS.txt` identifies the submitted files. `submission_manifest.json` records their sizes, hashes, intended paths and the exact application commit. `SUBMISSION_VALIDATION.json` records document/package checks; it is separate from the application's test results.
