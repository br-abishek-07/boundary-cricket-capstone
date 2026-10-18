# Data and asset provenance

The supplied Cricsheet archives and their exact hashes, included counts and date ranges are recorded in data/audit.json. Source: https://cricsheet.org/. Consult the current source license and attribution terms before any new redistribution. This repository already contains the supplied processed archive evidence.

The release includes 6,392 eligible men's matches and 141,377 player-match records. IPL includes matches through 2026-05-31. BBL ends 2026-01-25; Hundred 2026-08-16; T20I 2026-10-06; SMAT 2024-12-15. These are snapshot endpoints, not completeness claims.

The player registry links supplied Cricsheet IDs, archive aliases and supplied squad names. Selected display corrections cite their review sources in data/player_registry.json. This is a local release registry, not the complete external Cricsheet register. Reference bowling styles are curated planning assumptions from data/attack_types.json. Unknown remains explicit.

The supplied 2026 squad file is adjusted only by sourced dated events in data/squad_events.json. Complete current registration, replacement and availability are not verified. The historical 2013–2022 auction CSV is a manual lookup; currency and transaction types require verification. It is not a live market-price feed.

Asset source URLs and credits are in assets/sources.json. League and team marks identify the educational subjects. No endorsement is implied.

See USER_GUIDE.md for delivery conventions, phase rules, score formulas, legal scheduling constraints, baseline gating, model/study limitations, rebuild commands and exports.
