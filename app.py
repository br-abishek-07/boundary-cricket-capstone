"""Boundary: an evidence-first cricket research studio."""

import datetime, html, json, os, secrets, sys, tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import altair as alt
import pandas as pd
import streamlit as st
from boundary_runtime import load_release

release = load_release(ROOT)
load = release.analytics.load
scout = release.analytics.scout
roster_scores = release.analytics.roster_scores
optimize = release.analytics.optimize
player_interval = release.analytics.player_interval
resolve = release.analytics.resolve
identity_label = release.analytics.identity_label
window = release.analytics.window
select_window = release.analytics.select_window
predict = release.prediction.predict
prepare = release.agent.prepare
task_context = release.agent.task_context
provider = release.agent.provider
VERSION = release.evidence.VERSION
safe = release.evidence.safe
context_key = release.evidence.context_key
manifest = release.evidence.manifest
export_frame = release.evidence.export_frame
decision_pack = release.evidence.decision_pack
storage, branding, downloads = release.storage, release.branding, release.downloads

st.set_page_config(
    page_title="Boundary · Franchise research", page_icon="🏏", layout="wide"
)


@st.cache_resource(max_entries=1)
def data(signature):
    return load()


@st.cache_data(show_spinner=False, max_entries=2)
def source_download(signature):
    return downloads.source_zip()


signature = (release.release_fingerprint,) + tuple(
    (ROOT / "data" / f).stat().st_mtime_ns
    for f in [
        "match_players.csv.gz",
        "squads.csv",
        "squad_events.json",
        "player_registry.json",
    ]
)
p, s, a = data(signature)
audit = json.loads((ROOT / "data/audit.json").read_text())
model = json.loads((ROOT / "data/prediction_model.json").read_text())
report = json.loads((ROOT / "data/prediction_report.json").read_text())
PAGES = [
    "Home",
    "Decision desk",
    "Scouting & comparison",
    "Squad & auction scenarios",
    "Player dossier",
    "Match research",
    "Decision journal",
    "Evaluation & sources",
    "Project guide",
    "Settings",
]
ss = st.session_state
for k, v in {
    "private_session": secrets.token_urlsafe(32),
    "scenarios": {},
    "filters": {
        "competition": "IPL",
        "discipline": "Bowling",
        "phase": "Death",
        "min_balls": 120,
    },
    "decision_inputs": {},
    "workspace": "Home",
    "franchise": "RCB",
    "appearance": "Dark",
    "reduced_motion": False,
}.items():
    if k not in ss:
        ss[k] = v


def go(page):
    ss.workspace = page


def preset(team_code, intent, question, exclude=None):
    ss.franchise = team_code
    ss.workspace = "Decision desk"
    ss.filters = {
        "competition": "IPL",
        "discipline": "Bowling",
        "phase": "Death",
        "min_balls": 120,
        "since": window(datetime.date.today().isoformat()),
    }
    ss.decision_inputs[team_code] = {
        "intent": intent,
        "question": question,
        "mode": "Local evidence",
    }
    ss.scenarios[team_code] = {
        "excluded": exclude or [],
        "locked": [],
        "min_spin": 1,
        "min_pace": 2,
        "min_bowlers": 5,
        "min_batters": 5,
        "overrides": {},
        "costs": None,
        "budget": None,
    }
    for k in [
        "question_" + team_code,
        "intent_" + team_code,
        "mode_" + team_code,
        "exclude_" + team_code,
        "lock_" + team_code,
        "ev_comp",
        "ev_phase",
        "ev_discipline",
        "ev_min",
        "ev_since",
    ]:
        ss.pop(k, None)
    ss.pop("brief", None)


def private_key():
    if ss.get("private_key"):
        return ss.private_key
    if os.getenv("DEEPSEEK_API_KEY"):
        return os.getenv("DEEPSEEK_API_KEY")
    try:
        return st.secrets.get("DEEPSEEK_API_KEY", "")
    except FileNotFoundError:
        return ""


with st.sidebar:
    st.markdown("## BOUNDARY")
    st.caption("FRANCHISE RESEARCH STUDIO")
    st.markdown(
        f'<img src="{branding.logo("IPL")}" width="76" alt="IPL identification mark" style="background:white;padding:10px;border-radius:5px;margin-bottom:8px">',
        unsafe_allow_html=True,
    )

    def keep_theme():
        if ss.appearance is None:
            ss.appearance = ss.get("last_theme", "Dark")
        else:
            ss.last_theme = ss.appearance

    st.segmented_control(
        "Appearance", ["Light", "Dark"], key="appearance", on_change=keep_theme
    )
    st.toggle(
        "Reduce motion",
        key="reduced_motion",
        help="Disables decorative movement. Your system preference is also respected.",
    )
    team = st.selectbox("Franchise desk", list(branding.TEAMS), key="franchise")
    page = st.radio("Workspace", PAGES, key="workspace")
    today = datetime.date.today()
    cutoff = st.date_input(
        "Use matches before",
        value=today,
        min_value=datetime.date(2008, 1, 1),
        max_value=today,
        key="cutoff",
    )
    until = cutoff.isoformat()
    st.caption(
        "Exclusive cutoff: matches on this date are not included. Export private work before closing or redeploying."
    )
    if st.button("Start a fresh private session"):
        ss.private_session = secrets.token_urlsafe(32)
        ss.pop("brief", None)
        ss.pop("brief_error", None)
        st.rerun()
    st.caption("Boundary " + VERSION + " · Educational research")
style, palette = branding.css(team, ss.appearance)
st.markdown(style, unsafe_allow_html=True)
if ss.reduced_motion:
    st.markdown(
        "<style>*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}</style>",
        unsafe_allow_html=True,
    )
owner = storage.scope(ss.private_session, team)
quota_owner = storage.scope(ss.private_session, "__all_teams__")
st.markdown(
    f'<div class="folio"><span>BOUNDARY / EVIDENCE & DECISIONS</span><span>{team} · {ss.appearance.upper()} · BEFORE {until}</span></div>',
    unsafe_allow_html=True,
)
if page != "Home":
    st.markdown(branding.desk(team, until), unsafe_allow_html=True)
since = ss.filters.get("since") or window(until)
if since >= until:
    since = window(until)
context = {**ss.filters, "since": since, **ss.scenarios.get(team, {})}


def heading(title, description):
    st.markdown(
        '<div class="page-intro"><h1>'
        + html.escape(title).replace("\n", "<br>")
        + '</h1><div class="deck">'
        + html.escape(description)
        + "</div></div>",
        unsafe_allow_html=True,
    )


def table(df):
    labels = {
        "player_name": "Player",
        "player": "Player",
        "attack_type": "Style (reference)",
        "utility": "Scenario score",
        "legal_balls": "Bowling balls",
        "pp_allocated_balls": "PP balls",
        "mid_allocated_balls": "Middle balls",
        "death_allocated_balls": "Death balls",
        "strike_rate": "Strike rate",
        "score": "Descriptive score",
        "reliability": "Sample weight",
        "player_id": "Registry ID",
        "cricsheet_id": "Registry ID",
        "evidence_missing": "No observed evidence",
        "bowling_capacity": "Max overs",
        "selection_blocked": "Dated selection block",
        "status_note": "Registration / availability note",
        "pp_capacity": "PP max overs",
        "mid_capacity": "Middle max overs",
        "death_capacity": "Death max overs",
        "last_played": "Last relevant match",
    }
    st.dataframe(
        df.head(500)
        .style.format(precision=2)
        .set_properties(
            **{"background-color": palette["panel"], "color": palette["text"]}
        ),
        hide_index=True,
        width="stretch",
        column_config={k: v for k, v in labels.items() if k in df},
    )
    if len(df) > 500:
        st.caption("Showing 500 rows. Downloads include the full selection.")


def chart(df, x, y):
    c = (
        alt.Chart(df)
        .mark_bar(color=palette["accent"], cornerRadiusTopLeft=3)
        .encode(x=alt.X(x, sort=None), y=alt.Y(y), tooltip=list(df.columns))
        .properties(height=240)
        .configure(background=palette["bg"])
        .configure_axis(
            labelColor=palette["text"],
            titleColor=palette["text"],
            gridColor=palette["border"],
        )
        .configure_view(stroke=None)
    )
    st.altair_chart(c, width="stretch")


def exports(df, kind, scope=None, extras=None):
    scope = context if scope is None else scope
    c = st.columns(2)
    c[0].download_button(
        "Download CSV",
        export_frame(df, team, until, scope, kind).to_csv(index=False),
        kind + ".csv",
        "text/csv",
        key="csv_" + kind,
        on_click="ignore",
    )
    c[1].download_button(
        "Download decision pack",
        decision_pack(df, team, until, scope, kind, extras=extras),
        kind + "-decision-pack.zip",
        "application/zip",
        key="pack_" + kind,
        on_click="ignore",
    )
    st.caption(
        "The decision pack includes context, assumptions, version and SHA-256 source fingerprints."
    )


def filters():
    global context
    with st.expander("Evidence filters", expanded=page == "Scouting & comparison"):
        c = st.columns(4)
        comps = ["IPL", "BBL", "SMAT", "Hundred", "T20I", "ALL"]
        phases = ["Death", "Powerplay", "Middle", "All"]
        comp = c[0].selectbox(
            "Competition",
            comps,
            index=comps.index(context["competition"]),
            key="ev_comp",
        )
        discipline = c[1].selectbox(
            "Discipline",
            ["Bowling", "Batting"],
            index=["Bowling", "Batting"].index(context["discipline"]),
            key="ev_discipline",
        )
        phase = c[2].selectbox(
            "Phase", phases, index=phases.index(context["phase"]), key="ev_phase"
        )
        minimum = int(
            c[3].number_input(
                "Minimum phase balls",
                1,
                2000,
                int(context["min_balls"]),
                30,
                key="ev_min",
            )
        )
        if "ev_since" in ss and ss.ev_since >= cutoff:
            ss.pop("ev_since", None)
        start = st.date_input(
            "Evidence window starts",
            value=pd.Timestamp(context["since"]).date(),
            max_value=cutoff - datetime.timedelta(days=1),
            key="ev_since",
        ).isoformat()
        st.caption(
            "Scores and sample thresholds apply to this exact scope. ALL keeps competitions separate. Sample weight describes evidence volume after recency decay; it is not confidence in future success."
        )
    ss.filters = {
        "competition": comp,
        "discipline": discipline,
        "phase": phase,
        "min_balls": minimum,
        "since": start,
    }
    context = {**ss.filters, **ss.scenarios.get(team, {})}
    st.caption(
        f"Scope: {comp} · {discipline} · {phase} · {start} to before {until} · minimum {minimum} relevant balls."
    )


def matchup_controls(prefix):
    teams = list(branding.TEAMS)
    c = st.columns(2)
    first = c[0].selectbox(
        "Team A", teams, index=teams.index(team), key=prefix + "a_" + team
    )
    second = c[1].selectbox(
        "Team B", [t for t in teams if t != first], key=prefix + "b_" + team
    )
    chase = st.selectbox(
        "Chasing team", ["Unknown", first, second], key=prefix + "chase_" + team
    )
    venue = st.selectbox(
        "Canonical venue",
        sorted(model["state"]["venues"]),
        key=prefix + "venue_" + team,
    )
    return {
        "team1": first,
        "team2": second,
        "chasing": None if chase == "Unknown" else chase,
        "venue": venue,
    }


def guide_downloads():
    for name, label, mime in [
        ("Boundary_Project_Guide.pdf", "Download PDF guide", "application/pdf"),
        (
            "Boundary_Project_Guide.docx",
            "Download Word guide",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ]:
        f = ROOT / "docs" / name
        if f.exists():
            st.download_button(label, f.read_bytes(), name, mime, on_click="ignore")
    st.download_button(
        "Download complete project ZIP",
        source_download((release.release_fingerprint, downloads.source_signature())),
        "Boundary-v3-project.zip",
        "application/zip",
        on_click="ignore",
    )
    st.caption(
        "Includes application code, processed data, tests and the guide. Hosting credentials and private session records are excluded."
    )


if page == "Home":
    st.markdown(
        f'<div class="home-brand"><img src="{branding.logo(team)}" class="crest" alt="{team} logo"><span>{branding.TEAMS[team][0]} / analyst workspace</span></div>',
        unsafe_allow_html=True,
    )
    heading(
        "From a cricket question\nto a defensible decision.",
        "Boundary helps franchise analysts compare role evidence, build a supported XI and preserve the reasoning. Every brief starts with confirmed filters and ends with traceable calculations.",
    )
    c = st.columns([1, 1, 1.4])
    c[0].button(
        "Open decision desk", type="primary", on_click=go, args=("Decision desk",)
    )
    c[1].button("Read the project guide", on_click=go, args=("Project guide",))
    c[2].caption(
        "Start in Local evidence at no API cost. DeepSeek can select verified facts and review actions; calculations remain in the research engine."
    )
    st.markdown(
        '<div class="workflow">'
        + "".join(
            f'<div class="workflow-step"><span>0{i}</span><strong>{title}</strong><p>{desc}</p></div>'
            for i, (title, desc) in enumerate(
                [
                    ("Question", "Choose the decision and task."),
                    ("Confirm", "Set team, cutoff and assumptions."),
                    ("Retrieve", "Select the relevant archive evidence."),
                    ("Calculate", "Run rates, comparisons or a legal plan."),
                    ("Check", "Validate targets, scope and completeness."),
                    ("Review", "Read, export and record the decision."),
                ],
                1,
            )
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    st.subheader("Try a real analyst workflow")
    c = st.columns(2)
    with c[0]:
        st.markdown("**RCB / death-bowling comparison**")
        st.write(
            "Review IPL death-over bowling evidence from the last three years. Inspect sample size and recent exposure before shortlisting."
        )
        st.button(
            "Load RCB example",
            on_click=preset,
            args=(
                "RCB",
                "Scouting",
                "Compare death-bowling evidence for RCB. Explain what needs a human review.",
            ),
        )
    with c[1]:
        st.markdown("**MI / plan without Bumrah**")
        st.write(
            "Exclude Jasprit Bumrah, build a supported XI and check who can deliver every over. An infeasible result is useful evidence too."
        )
        st.button(
            "Load MI scenario",
            on_click=preset,
            args=(
                "MI",
                "XI planning",
                "Plan an MI XI without Jasprit Bumrah using the confirmed exclusions.",
                ["Jasprit Bumrah"],
            ),
        )
    st.caption(
        "Loading an example sets the controls. It does not call the API or prepare a result automatically."
    )
    st.divider()
    st.subheader("What data is actually available?")
    coverage = pd.DataFrame(
        [
            {
                "Competition": x["competition"],
                "Matches": x["included"],
                "First match": x["earliest"],
                "Latest match": x["latest"],
            }
            for x in audit["sources"]
        ]
    )
    table(coverage)
    st.info(
        "Yes, the supplied archives include 2026 matches. IPL runs through 31 May 2026. This is a frozen archive, not a live or complete 2026 feed. SMAT ends in December 2024. The selected cutoff can narrow it further."
    )
    c = st.columns(3)
    c[0].metric("Included matches", f"{audit['matches']:,}")
    c[1].metric("Competitions", 5)
    c[2].metric("Franchise desks", 10)
    st.caption(
        "Availability, injuries, current market prices and complete squad eligibility need independent verification. Historical scores are descriptive. The match model has no established predictive advantage."
    )
    with st.expander("Download and reproduce this project"):
        guide_downloads()

elif page == "Decision desk":
    heading(
        "Brief the decision.\nKeep the evidence attached.",
        "Choose a structured task, confirm the context, then prepare a brief. DeepSeek works within the retrieved facts. Availability and tactical judgement remain with the analyst.",
    )
    filters()
    left, right = st.columns([1.9, 1], gap="large")
    with left:
        old = ss.decision_inputs.get(team, {})
        intents = ["Scouting", "XI planning", "Player evidence", "Match research"]
        modes = ["Local evidence", "DeepSeek selection"]
        intent = st.selectbox(
            "Research task",
            intents,
            index=intents.index(old.get("intent", "Scouting")),
            key="intent_" + team,
        )
        mode = st.radio(
            "Briefing mode",
            modes,
            index=modes.index(old.get("mode", "Local evidence")),
            horizontal=True,
            key="mode_" + team,
        )
        scope = {**context, "intent": intent}
        unresolved_query = False
        if intent in ["Scouting", "Player evidence"]:
            query = st.text_input(
                "Find a player or alias (optional for scouting)",
                key="target_query_" + team,
            )
            hits = resolve(p[p.date < until], query) if query else []
            if query and not hits:
                st.warning(
                    "No matching registry identity. No statistics will be inferred."
                )
            chosen = st.multiselect(
                (
                    "Confirm comparison players"
                    if intent == "Scouting"
                    else "Confirm target player"
                ),
                hits,
                format_func=lambda x: identity_label(p, x, until),
                max_selections=3 if intent == "Scouting" else 1,
                key="target_" + intent + "_" + team,
            )
            scope["candidate_ids" if intent == "Scouting" else "target_ids"] = [
                x["player_id"] for x in chosen
            ]
            unresolved_query = bool(query and not hits) or (
                intent == "Player evidence" and not chosen
            )
            if intent == "Scouting":
                omitted = st.multiselect(
                    "Exclude comparison players",
                    hits,
                    format_func=lambda x: identity_label(p, x, until),
                    key="omit_compare_" + team,
                )
                scope["candidate_excluded_ids"] = [x["player_id"] for x in omitted]
                scope["candidate_pool"] = st.selectbox(
                    "Candidate pool",
                    [
                        "All observed players",
                        "Supplied squad pool",
                        "Outside supplied pool",
                    ],
                    key="candidate_pool_" + team,
                )
        elif intent == "Match research":
            scope["matchup"] = matchup_controls("brief_")
        else:
            st.caption(
                "XI planning uses the dated squad, exclusions, locks, budget and justified capability assumptions in Squad & auction scenarios. Scouting filters do not change its three-year IPL eligibility window."
            )
        question = st.text_area(
            "Decision question",
            value=old.get(
                "question",
                f'Compare {context["phase"].lower()} evidence for {team} using the active filters.',
            ),
            max_chars=2000,
            height=110,
            key="question_" + team,
        )
        ss.decision_inputs[team] = {
            "intent": intent,
            "mode": mode,
            "question": question,
        }
        if st.button("Prepare brief", type="primary", disabled=unresolved_query):
            ss.pop("brief", None)
            ss.pop("brief_error", None)
            try:
                with st.status("Preparing your evidence", expanded=True) as progress:
                    stage = st.empty()
                    b = prepare(
                        question,
                        p,
                        s,
                        model,
                        team,
                        until,
                        owner,
                        scope,
                        key=private_key(),
                        live=mode == "DeepSeek selection",
                        quota_owner=quota_owner,
                        on_progress=lambda text: stage.write(text),
                    )
                    ss.brief = b
                    progress.update(
                        label=(
                            "Context needs attention"
                            if b["status"] == "clarification"
                            else "Evidence checked"
                        ),
                        state="complete",
                        expanded=False,
                    )
            except (ValueError, RuntimeError) as ex:
                ss.brief_error = str(ex)
        if ss.get("brief_error"):
            st.error(ss.brief_error)
        if "brief" in ss:
            b = ss.brief
            normalized, _ = task_context(question, p, team, until, scope)
            current = context_key(question, team, until, normalized)
            if current != b.get("fingerprint"):
                st.warning(
                    "Context changed. Prepare a new brief before saving or exporting. The previous result is hidden to prevent reuse with different assumptions."
                )
            else:
                st.caption(b["mode"] + " · " + b["status"].replace("_", " "))
                st.markdown(b["text"])
                if b.get("model_selection_fallback"):
                    st.info(
                        "DeepSeek selection was unavailable or did not pass validation. This brief uses the complete checked local evidence."
                    )
                if b["status"] == "evidence_checked":
                    facts = pd.DataFrame(
                        [
                            {"fact_id": fid, **v["record"]}
                            for fid, v in b["facts"].items()
                        ]
                    )
                    extras = {"brief.md": b["text"], "checked_evidence.json": b}
                    c = st.columns(2)
                    c[0].download_button(
                        "Download brief pack",
                        decision_pack(
                            facts, team, until, b["scenario"], intent, question, extras
                        ),
                        "Boundary-brief.zip",
                        "application/zip",
                        on_click="ignore",
                    )
                    if c[1].button("Save private brief"):
                        storage.save(owner, "briefs", question[:100], safe(b))
                        st.success("Saved to this session and franchise journal.")
                with st.expander("Evidence, validation and source trace"):
                    st.json(
                        safe(
                            {
                                k: b.get(k)
                                for k in [
                                    "facts",
                                    "validation",
                                    "trace",
                                    "scenario",
                                    "manifest",
                                    "usage",
                                ]
                            }
                        )
                    )
    with right:
        st.subheader("Confirmed scenario")
        st.write("**" + branding.TEAMS[team][0] + "**")
        st.caption("Evidence before " + until)
        for label, k in [("Unavailable", "excluded"), ("Locked", "locked")]:
            st.write(label + ": " + (", ".join(context.get(k, [])) or "None"))
        if context.get("budget") is not None:
            st.write(f"Assumed XI budget: ₹{context['budget']:.2f} Cr")
        st.button(
            "Edit squad assumptions", on_click=go, args=("Squad & auction scenarios",)
        )
        st.subheader("How to read the brief")
        st.write(
            "Check the question, sample and last relevant match. Follow each fact to its source record. Treat next actions as a review checklist, then save or export the complete context."
        )
        st.caption(
            "A passed evidence check verifies provenance and task scope. It does not certify tactical quality or future performance. Unsupported age, handedness and current price requests need other evidence."
        )

elif page == "Scouting & comparison":
    heading(
        "Find the role.\nInspect the relevant sample.",
        "Use the same competition, phase and dates for a comparison. Raw rates stay visible beside a recency-weighted, sample-adjusted descriptive score.",
    )
    filters()
    r = scout(
        p,
        context["competition"],
        context["since"],
        context["min_balls"],
        context["discipline"],
        until,
        context["phase"],
    )
    search = st.text_input("Find a player or alias")
    if search:
        r = r[r.player_id.isin([x["player_id"] for x in resolve(p, search)])]
    cols = (
        ["player", "player_id"]
        + (["competition"] if context["competition"] == "ALL" else [])
        + [
            "score",
            "reliability",
            "last_played",
            "runs",
            "balls",
            "dismissals",
            "wickets",
            "legal_balls",
            "strike_rate",
            "economy",
        ]
    )
    table(r[cols])
    exports(r, "scouting")
    chosen = st.multiselect(
        "Compare up to three players",
        r.player_id.drop_duplicates().tolist(),
        default=r.player_id.drop_duplicates().head(2).tolist(),
        max_selections=3,
        format_func=lambda x: r[r.player_id == x].player.iloc[0] + " · " + x,
    )
    selected = r[r.player_id.isin(chosen)]
    if len(selected):
        table(selected[cols])
        chart(
            selected.assign(
                label=selected.player
                + (
                    " / " + selected.competition
                    if context["competition"] == "ALL"
                    else ""
                )
            ),
            "label:N",
            "score:Q",
        )
        for row in selected.itertuples():
            st.caption(
                row.player
                + " · observed-rate uncertainty: "
                + json.dumps(
                    player_interval(
                        p,
                        row.player_id,
                        context["discipline"],
                        until,
                        context["since"],
                        getattr(row, "competition", context["competition"]),
                        context["phase"],
                    )
                )
            )
    st.caption(
        "Intervals resample relevant matches. They describe observed rates, not future success. The descriptive score is not an auction valuation or an IPL-equivalent translation of other leagues."
    )

elif page == "Squad & auction scenarios":
    heading(
        "Build the XI.\nAccount for every over.",
        "A complete plan assigns one bowler to each over, respects phase evidence, prevents consecutive overs by the same bowler, and caps each bowler at four overs.",
    )
    try:
        r = roster_scores(p, s, team, until)
    except ValueError as ex:
        st.warning(str(ex))
        st.stop()
    st.warning(
        "Research pool: supplied squad records can include withdrawn players and their replacements. This is not a fully verified current registration list. Check the sourced status table and availability before using a plan."
    )
    blocked = r[r.selection_blocked]
    if len(blocked):
        st.info(
            "Excluded by dated 2026 notices: "
            + ", ".join(blocked.player_name)
            + ". Capability overrides cannot remove these sourced blocks."
        )
    review = json.loads((ROOT / "data/roster_status.json").read_text())
    missing = [
        n["replacement"]
        for n in review["notices"]
        if n["team"] == team
        and n["published_date"] < until
        and n["replacement"]
        and not n["replacement_in_supplied_pool"]
    ]
    if missing:
        st.warning(
            "The supplied pool is missing documented replacements: "
            + ", ".join(missing)
            + ". A plan cannot evaluate those players until their roster metadata is verified and added."
        )
    old = ss.scenarios.get(team, {})
    names = r.player_name.tolist()
    c = st.columns(2)
    excluded = c[0].multiselect(
        "Unavailable / exclude",
        names,
        default=[n for n in old.get("excluded", []) if n in names],
        key="exclude_" + team,
    )
    locked = c[1].multiselect(
        "Must include",
        names,
        default=[n for n in old.get("locked", []) if n in names],
        key="lock_" + team,
    )
    c = st.columns(4)
    min_spin = c[0].slider(
        "Minimum spin options", 0, 3, old.get("min_spin", 1), key="spin_" + team
    )
    min_pace = c[1].slider(
        "Minimum pace options", 0, 5, old.get("min_pace", 2), key="pace_" + team
    )
    budget_on = c[2].checkbox(
        "Apply XI budget", value=old.get("budget") is not None, key="budget_on_" + team
    )
    edit = c[3].checkbox(
        "Capability assumptions",
        value=bool(old.get("overrides")),
        key="override_on_" + team,
    )
    overrides = dict(old.get("overrides", {})) if edit else {}
    if edit:
        st.caption(
            "Reference styles and capability overrides are planning assumptions. Keep a written source or reason. A half-over cannot be scheduled; capacities must use whole overs."
        )
        with st.form("override_form_" + team):
            name = st.selectbox("Override player", names)
            c = st.columns(4)
            cap = int(c[0].number_input("Maximum overs", 0, 4, 4))
            pp = int(c[1].number_input("Powerplay cap", 0, 4, 4))
            mid = int(c[2].number_input("Middle cap", 0, 4, 4))
            death = int(c[3].number_input("Death cap", 0, 4, 4))
            attack = st.selectbox("Style assumption", ["Pace", "Spin", "Unknown"])
            utility = st.number_input("Utility for unobserved player", value=0.0)
            reason = st.text_input("Justification / source")
            if st.form_submit_button("Add or update assumption"):
                if not reason.strip():
                    st.error("A written justification is required.")
                elif max(pp, mid, death) > cap:
                    st.error("A phase cap cannot exceed the total cap.")
                else:
                    overrides[name] = {
                        "capacity": cap,
                        "pp": pp,
                        "mid": mid,
                        "death": death,
                        "attack_type": attack,
                        "utility": utility,
                        "reason": reason,
                    }
                    st.success("Assumption applied.")
        if overrides:
            table(pd.DataFrame([{"player": n, **v} for n, v in overrides.items()]))
            remove = st.selectbox("Remove an assumption", ["None"] + list(overrides))
            if st.button("Remove selected assumption") and remove != "None":
                overrides.pop(remove, None)
    costs = None
    budget = None
    if budget_on:
        budget = st.number_input(
            "XI scenario budget (₹ Cr)",
            0.0,
            500.0,
            float(old.get("budget") or 30.0),
            1.0,
            key="budget_" + team,
        )
        st.caption(
            "Every price below is an analyst assumption. Initial ₹1 Cr entries are placeholders, not current valuations."
        )
        editor = st.data_editor(
            pd.DataFrame(
                {
                    "Player": names,
                    "Cost (₹ Cr)": [
                        float((old.get("costs") or {}).get(n, 1.0)) for n in names
                    ],
                }
            ),
            hide_index=True,
            disabled=["Player"],
            column_config={
                "Cost (₹ Cr)": st.column_config.NumberColumn(
                    min_value=0.0, max_value=100.0
                )
            },
            key="cost_" + team,
        )
        costs = dict(zip(editor.Player, editor["Cost (₹ Cr)"]))
    scenario = {
        "excluded": excluded,
        "locked": locked,
        "min_spin": min_spin,
        "min_pace": min_pace,
        "min_bowlers": 5,
        "min_batters": 5,
        "costs": costs,
        "budget": budget,
        "overrides": overrides,
    }
    ss.scenarios[team] = scenario
    scope = {**context, **scenario, "intent": "XI planning"}
    result = optimize(r, **scenario)
    if result["ok"]:
        c = st.columns(4)
        c[0].metric("Selected", 11)
        c[1].metric("Overseas", str(result["overseas"]) + " / 4")
        c[2].metric("Assigned overs", 20)
        c[3].metric("Legal balls", 120)
        tabs = st.tabs(["XI & reasons", "Over-by-over plan", "Alternatives", "Checks"])
        with tabs[0]:
            table(
                result["players"][
                    [
                        "player_name",
                        "attack_type",
                        "utility",
                        "pp_allocated_balls",
                        "mid_allocated_balls",
                        "death_allocated_balls",
                        "selection_reason",
                    ]
                    + (["scenario_cost_cr"] if budget is not None else [])
                ]
            )
        with tabs[1]:
            table(result["schedule"])
            st.success(
                "Schedule checked: complete coverage, no consecutive overs, workload and phase caps respected."
            )
        with tabs[2]:
            table(result["alternatives"])
            alternative = st.selectbox(
                "Force an available alternative",
                ["None"] + result["alternatives"].player_name.tolist(),
            )
            if st.button("Compare counterfactual", disabled=alternative == "None"):
                other = optimize(
                    r, **{**scenario, "locked": list(set(locked + [alternative]))}
                )
                if other["ok"]:
                    before = set(result["players"].player_name)
                    after = set(other["players"].player_name)
                    st.write("Enters: " + ", ".join(sorted(after - before)))
                    st.write("Leaves: " + ", ".join(sorted(before - after)))
                    st.caption(
                        f"Change in descriptive scenario score: {other['utility']-result['utility']:+.2f}. This is not an expected match-win gain."
                    )
                    table(other["schedule"])
                    exports(
                        other["players"],
                        "counterfactual",
                        scope={**scope, "locked": list(set(locked + [alternative]))},
                        extras={"schedule.csv": other["schedule"]},
                    )
                else:
                    st.warning(other["reason"])
        with tabs[3]:
            table(pd.DataFrame(result["diagnostics"]))
            st.json(result["schedule_checks"])
            st.write(result["scope"])
        exports(
            result["players"],
            "xi",
            scope,
            {
                "schedule.csv": result["schedule"],
                "alternatives.csv": result["alternatives"],
                "checks.json": result["schedule_checks"],
            },
        )
        if st.button("Save private scenario"):
            storage.save(
                owner,
                "briefs",
                team + " XI and twenty-over plan",
                safe(
                    {
                        "team": team,
                        "until": until,
                        "scenario": scenario,
                        "players": result["players"],
                        "schedule": result["schedule"],
                        "manifest": manifest(team, until, scope, "XI planning"),
                    }
                ),
            )
            st.success("Saved privately.")
    else:
        st.warning(result["reason"])
        table(pd.DataFrame(result.get("diagnostics", [])))
    with st.expander("Squad evidence and eligibility assumptions"):
        table(
            r[
                [
                    "player_name",
                    "attack_type",
                    "role",
                    "balls",
                    "legal_balls",
                    "bowling_capacity",
                    "pp_capacity",
                    "mid_capacity",
                    "death_capacity",
                    "evidence_missing",
                    "selection_blocked",
                    "status_note",
                    "status_source",
                ]
            ]
        )
        st.write(
            "Default workload eligibility: 120 observed IPL legal balls in the three-year window, plus 36 powerplay / 36 middle / 24 death balls for those phases. Batting support requires 30 balls. These are research thresholds. The 2026 squad snapshot has partial dated verification. Confirm full eligibility, injuries and any Impact Player plan separately."
        )

elif page == "Player dossier":
    heading(
        "Confirm the identity.\nRead the underlying record.",
        "Choose an archive overview or a scoped research sample. Identical names require an explicit registry selection.",
    )
    view = st.radio(
        "Dossier view",
        ["Player overview", "Use active research filters"],
        horizontal=True,
        key="dossier_view_v302",
    )
    if view == "Use active research filters":
        filters()
        profile_context = dict(context)
        st.caption(
            "Both batting and bowling totals below use the chosen phase. Discipline selects the uncertainty measure. The minimum-ball threshold belongs to scouting rankings; it does not hide a dossier."
        )
    else:
        competition = st.selectbox(
            "Overview competition",
            ["IPL", "T20I", "SMAT", "BBL", "Hundred"],
            key="overview_comp",
        )
        beginning = next(
            x["earliest"] for x in audit["sources"] if x["competition"] == competition
        )
        profile_context = {
            **context,
            "competition": competition,
            "phase": "All",
            "since": beginning,
            "discipline": "Batting",
        }
        st.caption(
            f"Archive overview: {competition} · all phases · {beginning} to before {until}. Coverage is limited to supplied match records."
        )
    query = st.text_input("Player name, alias or registry ID", value="Virat Kohli")
    hits = resolve(p[p.date < until], query)
    if not hits:
        st.info(
            "No matching archive identity before this cutoff. Try a source alias or registry ID."
        )
        st.stop()
    hit = st.selectbox(
        "Confirm identity",
        hits,
        index=0 if len(hits) == 1 else None,
        placeholder="Select the intended player using the ID and observed teams",
        format_func=lambda x: identity_label(p, x, until),
        key="dossier_identity_v302_" + query.strip().lower(),
    )
    if hit is None:
        st.info(
            "This name identifies more than one player. Confirm the observed team and registry ID before viewing statistics."
        )
        st.stop()
    z = select_window(
        p,
        profile_context["competition"],
        profile_context["since"],
        until,
        profile_context["phase"],
    )
    z = z[z.player_id == hit["player_id"]]
    c = st.columns(3)
    c[0].metric(
        (
            "Runs in archive"
            if profile_context["phase"] == "All"
            else "Runs in " + profile_context["phase"] + " phase"
        ),
        int(z.runs.sum()),
    )
    c[1].metric("Bowler-credited wickets", int(z.wickets.sum()))
    c[2].metric("Matches with named record", z.match_id.nunique())
    if profile_context["phase"] != "All":
        whole = select_window(
            p, profile_context["competition"], profile_context["since"], until, "All"
        )
        whole = whole[whole.player_id == hit["player_id"]]
        active = z[z.balls.add(z.legal_balls) > 0].match_id.nunique()
        st.info(
            f"This sample contains {int(z.runs.sum()):,} {profile_context['phase'].lower()}-phase runs. All phases in the same date window contain {int(whole.runs.sum()):,} runs. {active} matches contain relevant phase balls; the named-record count includes other appearances in this window."
        )
    st.caption(
        "Archive totals can be lower than official career or season figures when matches are missing. The earliest and latest dates do not establish complete coverage."
    )
    if profile_context["competition"] in ["T20I", "SMAT", "ALL"]:
        st.warning(
            "This source has known coverage gaps. Use these numbers as an archive sample, with the selected dates and phase. Compare complete career or season totals with an official record separately."
        )
    season = z.groupby(["competition", "season"], as_index=False)[
        ["runs", "balls", "wickets", "legal_balls"]
    ].sum()
    table(season)
    if len(season):
        chart(
            season.assign(label=season.season.astype(str) + " / " + season.competition),
            "label:N",
            "runs:Q",
        )
    st.caption(
        "Observed-rate uncertainty: "
        + json.dumps(
            player_interval(
                p,
                hit["player_id"],
                profile_context["discipline"],
                until,
                profile_context["since"],
                profile_context["competition"],
                profile_context["phase"],
            )
        )
    )
    exports(z, "player-dossier", {**profile_context, "target_ids": [hit["player_id"]]})
    with st.expander("Match evidence"):
        table(
            z[
                [
                    "date",
                    "competition",
                    "team",
                    "runs",
                    "balls",
                    "wickets",
                    "legal_balls",
                ]
            ].sort_values("date", ascending=False)
        )
    with st.expander("Historical auction lookup"):
        st.caption(
            "2013–2022 source records. Units and transaction types require verification. Manual search avoids false identity joins. This is not a current valuation."
        )
        auction_query = st.text_input("Auction name", value=hit["player"])
        table(a[a.Player.str.contains(auction_query, case=False, regex=False)])

elif page == "Match research":
    heading(
        "A benchmark must\nearn its place.",
        "The research model did not beat the training-derived chase-rate baseline in validation and held-out testing. The baseline remains the displayed estimate.",
    )
    matchup = matchup_controls("research_")
    scope = {**context, "intent": "Match research", "matchup": matchup}
    if until <= model["state"]["last_date"]:
        st.info(
            "The rating snapshot is after this cutoff. Current estimates are disabled; inspect the dated holdout records below."
        )
    else:
        pr = predict(
            model,
            **{
                "t1": matchup["team1"],
                "t2": matchup["team2"],
                "venue": matchup["venue"],
                "chasing": matchup["chasing"],
            },
        )
        c = st.columns(2)
        c[0].metric("Pre-toss baseline", "50% · no validated edge")
        c[1].metric(
            matchup["team1"] + " post-toss baseline",
            f"{pr['post']:.1%}" if pr["post"] is not None else "Confirm chasing team",
        )
        st.caption(
            pr["method"]
            + ". Squad edits, injuries, weather and current pitch reports are not inputs."
        )
        exports(pd.DataFrame([safe({**matchup, **pr})]), "match-scenario", scope)
    st.subheader("Held-out comparison")
    table(pd.DataFrame(report["test"]).T.reset_index(names="Method"))
    st.json(report["gate"])
    with st.expander("Methods, calibration and season results"):
        st.json(report)
    holdout = pd.read_csv(ROOT / "data/prediction_holdout.csv")
    exports(holdout, "historical-forecasts", scope, {"model-report.json": report})

elif page == "Decision journal":
    heading(
        "Keep the reasoning.\nExport the record.",
        "Saved work is scoped to this browser session and franchise. This educational deployment does not provide authenticated, durable team accounts.",
    )
    rows = storage.records(owner)
    for row in rows:
        with st.expander(row["title"] + " · " + row["created"][:10]):
            if row["payload"].get("text"):
                st.markdown(row["payload"]["text"])
            st.json(row["payload"])
    if not rows:
        st.info("Prepare a brief or scenario, then save it to start your journal.")
    else:
        st.download_button(
            "Export private journal",
            json.dumps(rows, indent=2),
            "private-journal.json",
            "application/json",
            on_click="ignore",
        )

elif page == "Evaluation & sources":
    heading(
        "Claims you can check.\nLimits you can see.",
        "Automated checks cover rules, records and interface behaviour. Tactical usefulness requires documented human review; no expert scores are invented.",
    )
    tabs = st.tabs(
        [
            "Release checks",
            "Historical role study",
            "Human review",
            "Sources & squads",
            "SWOT",
            "Accuracy audit",
        ]
    )
    with tabs[0]:
        f = ROOT / "data/release_checks.json"
        st.json(
            json.loads(f.read_text())
            if f.exists()
            else {"status": "Acceptance checks pending"}
        )
        st.caption(
            "Provider responses are tested with controlled fixtures. Live DeepSeek quality and the hosted rebuild require an online deployment check."
        )
    with tabs[1]:
        f = ROOT / "data/scouting_benchmark.csv"
        if f.exists():
            table(pd.read_csv(f))
            st.download_button(
                "Download historical role study",
                f.read_bytes(),
                "scouting-benchmark.csv",
                "text/csv",
                on_click="ignore",
            )
            st.json(
                json.loads((ROOT / "data/scouting_benchmark_report.json").read_text())
            )
        else:
            st.info("Study results are not yet available.")
    with tabs[2]:
        f = ROOT / "data/review_tasks.json"
        tasks = json.loads(f.read_text()) if f.exists() else []
        st.write(
            "Use these team tasks to test relevance, evidence and usefulness. Ratings remain unverified reviewer feedback."
        )
        st.download_button(
            "Download team review tasks",
            json.dumps(tasks, indent=2),
            "review-tasks.json",
            "application/json",
            on_click="ignore",
        )
        with st.form("review"):
            task_id = st.selectbox(
                "Review task", ["Independent task"] + [x["id"] for x in tasks]
            )
            reviewer = st.text_input("Reviewer alias")
            task = st.text_area("Decision and evidence reviewed")
            ratings = {
                x: st.select_slider(
                    x, ["Not assessed", 1, 2, 3, 4, 5], value="Not assessed"
                )
                for x in ["Evidence support", "Role relevance", "Clarity", "Usefulness"]
            }
            notes = st.text_area("Reason for the rating and supporting evidence")
            submit = st.form_submit_button("Save private review")
            if submit:
                if not reviewer.strip() or not task.strip():
                    st.error("Identify the reviewer and the decision reviewed.")
                else:
                    storage.save(
                        owner,
                        "reviews",
                        reviewer,
                        {
                            "task_id": task_id,
                            "task": task,
                            "ratings": ratings,
                            "notes": notes,
                        },
                    )
                    st.success(
                        "Saved privately. This is not an authenticated expert rating."
                    )
        reviews = storage.records(owner, "reviews")
        if reviews:
            st.download_button(
                "Export private reviews",
                json.dumps(reviews, indent=2),
                "reviews.json",
                "application/json",
                on_click="ignore",
            )
    with tabs[3]:
        table(pd.DataFrame(audit["sources"]))
        st.json(json.loads((ROOT / "data/squad_events.json").read_text()))
        st.json(json.loads((ROOT / "data/roster_status.json").read_text()))
        st.json(json.loads((ROOT / "assets/sources.json").read_text()))
        for note in audit["notes"]:
            st.caption(note)
        st.caption(
            "The player registry preserves supplied names and aliases, with a small set of reviewed display corrections. It is not the complete external Cricsheet names register."
        )
    with tabs[4]:
        table(
            pd.DataFrame(
                {
                    "Strengths": [
                        "Traceable match records",
                        "Explicit twenty-over solver",
                        "Scoped, checked brief facts",
                    ],
                    "Weaknesses": [
                        "Heuristic score weights",
                        "Partial squad verification",
                        "No proven predictive advantage",
                    ],
                    "Opportunities": [
                        "Documented scout reviews",
                        "Richer dated availability",
                        "More temporal role tests",
                    ],
                    "Threats": [
                        "Stale roster information",
                        "Changing source coverage",
                        "Public API allowance abuse",
                    ],
                }
            )
        )

    with tabs[5]:
        st.warning(
            "Archive consistency is not complete official coverage. The primary-source sample found five T20I coverage gaps and one unresolved one-run conflict. Current squads remain partially verified."
        )
        f = ROOT / "data/official_validation.csv"
        if f.exists():
            compared = pd.read_csv(f)
            table(compared[compared.status.ne("MATCH")])
            st.caption(
                "194 numeric checkpoints from 15 primary pages: 188 matches, five coverage gaps and one conflicting figure. Includes all ten IPL teams. This sample does not certify every official player record. See the report for scope and methods."
            )
            st.download_button(
                "Download official comparison CSV",
                f.read_bytes(),
                "boundary-official-comparisons.csv",
                "text/csv",
                on_click="ignore",
            )
        f = ROOT / "docs/ACCURACY_AUDIT.md"
        if f.exists():
            st.download_button(
                "Download accuracy audit",
                f.read_bytes(),
                "Boundary_Accuracy_Audit.md",
                "text/markdown",
                on_click="ignore",
            )
            st.markdown(f.read_text())

elif page == "Project guide":
    heading(
        "Understand it.\nRun it. Reproduce it.",
        "A step-by-step guide to the final application: purpose, datasets, calculations, AI workflow, testing, deployment and practical limits.",
    )
    c = st.columns([2, 1], gap="large")
    with c[1]:
        guide_downloads()
    with c[0]:
        f = ROOT / "docs/USER_GUIDE.md"
        if f.exists():
            sections = f.read_text().split("\n## ")
            titles = [x.splitlines()[0].lstrip("# ") for x in sections]
            choice = st.selectbox(
                "Guide chapter", range(len(titles)), format_func=lambda i: titles[i]
            )
            st.markdown(sections[choice] if choice == 0 else "## " + sections[choice])
    st.caption(
        "The source ZIP includes the same processed data as this release. Raw source archives are obtained separately; archive hashes and rebuild commands are documented."
    )

else:
    heading(
        "Private credentials.\nClear operating limits.",
        "Hosting secrets stay on the server. A session override stays in memory and is excluded from exports. Local evidence works without an API key.",
    )
    st.success(
        "A hosting or session key is configured."
        if private_key()
        else "No API key configured. Local evidence is available."
    )
    new = st.text_input(
        "Use your own DeepSeek key for this session", type="password", key="key_input"
    )
    if st.button("Set session key"):
        if new.startswith("sk-") and len(new) > 12:
            ss.private_key = new
            st.success(
                "Session override stored in memory. Only the provider can validate authentication."
            )
        else:
            st.error("Enter a valid-looking provider key.")
    if st.button("Clear session override"):
        ss.pop("private_key", None)
        ss.pop("key_input", None)
        st.rerun()
    if st.button("Test my session key", disabled=not bool(ss.get("private_key"))):
        try:
            provider(
                [
                    {
                        "role": "user",
                        "content": 'Return JSON: {"selected_fact_ids":[],"next_actions":[]}',
                    }
                ],
                ss.private_key,
                quota_owner,
            )
            st.success(
                "The provider responded. This checks connectivity, not analytical quality."
            )
        except RuntimeError as ex:
            st.error(str(ex))
    st.json(storage.usage(quota_owner))
    st.caption(
        "Limits: six provider calls per browser session across teams and thirty per installation per UTC day. A brief uses at most two provider calls. These caps are not an authenticated abuse boundary. Restrict access for sensitive team use. Local hosting storage may be ephemeral."
    )
    st.markdown(
        "IPL and franchise marks identify the subjects of this independent educational project. No league or franchise endorsement is implied. See Evaluation & sources for asset credits."
    )
