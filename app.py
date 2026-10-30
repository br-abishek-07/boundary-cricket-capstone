"""Phase 1: cached data ingestion and Streamlit navigation."""

import streamlit as st

from data_loader import (
    load_auction,
    load_match_players,
    load_matches,
    load_player_registry,
    load_squads,
)


st.set_page_config(
    page_title="IPL Intelligence 360°",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Sidebar navigation
with st.sidebar:
    st.title("IPL Intelligence 360°")
    st.caption("Cricket research and scouting")
    selected_module = st.radio(
        "Workspace",
        options=[
            "Home/Overview",
            "Player Profile",
            "Team Matchups",
            "Auction Trends",
        ],
    )
    st.divider()
    st.caption("Phase 1 · Data ingestion and navigation")


# Initialize datasets. Cached loaders reuse their results on UI reruns.
try:
    with st.spinner("Preparing cricket datasets..."):
        matches = load_matches()
        match_players = load_match_players()
        squads = load_squads()
        auction = load_auction()
        player_registry = load_player_registry()
except (OSError, ValueError) as exc:
    st.error(f"Unable to load the project data: {exc}")
    st.info(
        "Check that all five files exist inside creaseiq/data/ "
        "or the repository's data/ folder and match the filenames "
        "in data_loader.py."
    )
    st.stop()


# Route to the selected workspace.
if selected_module == "Home/Overview":
    st.title("IPL Intelligence 360°")
    st.write(
        "A workspace for franchise scouting, player research, "
        "team comparisons and historical auction analysis."
    )
    st.success("All five datasets loaded successfully.")
    col1, col2, col3 = st.columns(3)
    col1.metric("Match records", f"{len(matches):,}")
    col2.metric("Player-match records", f"{len(match_players):,}")
    col3.metric("Registry entries", f"{len(player_registry):,}")
    st.caption(
        f"Squad records: {len(squads):,} · "
        f"Auction records: {len(auction):,}"
    )
    with st.expander("Preview the supplied match data"):
        st.dataframe(matches.head(10), width="stretch")
    st.info(
        "Use the sidebar to switch workspaces. "
        "Analytical tools will be added in Phase 2."
    )

elif selected_module == "Player Profile":
    st.title("Player Profile")
    st.write("Explore player identities and match-level evidence.")
    st.info(
        "Phase 2: player selection, profile summaries "
        "and performance comparisons."
    )
    st.caption(
        f"Available: {len(player_registry):,} registry entries and "
        f"{len(match_players):,} player-match records."
    )

elif selected_module == "Team Matchups":
    st.title("Team Matchups")
    st.write(
        "Compare teams using the supplied historical match records."
    )
    st.info(
        "Phase 2: team selection, head-to-head summaries "
        "and matchup analysis."
    )
    st.caption(f"Available: {len(matches):,} match records.")

elif selected_module == "Auction Trends":
    st.title("Auction Trends")
    st.write("Inspect the supplied historical auction records.")
    st.info(
        "Phase 2: auction exploration and trends, "
        "after reviewing the dataset's fields and units."
    )
    st.caption(f"Available: {len(auction):,} auction records.")
