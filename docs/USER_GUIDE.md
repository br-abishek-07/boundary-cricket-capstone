# Using Boundary

Choose a franchise, Light or Dark appearance and an exclusive evidence cutoff in the sidebar. Dark mode is the default. Changes rerun the analysis; no API request occurs until you explicitly select DeepSeek and prepare a brief.

1. **Scouting:** choose league, discipline, phase, start date and minimum sample. Inspect raw balls and score assumptions. ALL keeps competitions separate. Compare up to three IDs. Intervals describe the observed rate; they are not future performance bounds.
2. **Player dossier:** search a name, archive alias or registry ID, then confirm identity. The dossier follows the active competition, dates and phase. Historical auction results require manual matching and are not current valuations.
3. **Squad scenarios:** inspect the evidence coverage first. Exclude unavailable players, lock selections and set supported spin/pace requirements. The solver allocates 36 PP, 60 middle and 24 death balls, at most 24 per player. If no supported solution exists it abstains. Written overrides are assumptions, never verified new evidence.
4. **Budget:** turn on XI budget and edit every player cost. Placeholder prices are explicitly assumptions; the budget applies to the XI, not a complete auction squad. Capability assumptions let you test one justified player override at a time.
5. **Decision desk:** choose a research task. Local evidence uses the same tools without API cost; DeepSeek chooses retrieved facts and approved next actions. Inspect the active filters and trace. Numerical facts are rendered locally. Ambiguous or missing evidence produces an insufficiency response. Save or download the brief.
6. **Match research:** select two different teams, venue and chasing side. The model failed its stronger baseline gate, so the baseline is primary. Current-snapshot estimates are blocked for earlier cutoffs. Squad edits are not prediction features.
7. **Journal:** records belong to this browser session and team. Export before closing. Switching teams or starting a fresh session hides those records. This is session scoping, not authenticated account access.
8. **Evaluation:** read actual release results and source records. Reviewer ratings start as Not assessed and do not become authenticated expert evaluations.

Hosting secrets supply the shared DeepSeek credential; Settings can use your own in-memory session key. A scoped connection test checks connectivity only. Provider limits are six requests per session and thirty per installation per UTC day; a brief can make up to three requests. Local evidence remains usable when the provider is unavailable.

The supplied 2026 squad is only partially verified. Known sourced trade events apply on dates strictly before the cutoff. Historical squad reconstruction before 2026 is rejected. Confirm availability, eligibility, bowling-style references and acquisition status before any practical decision.
