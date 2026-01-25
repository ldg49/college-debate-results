"""
Debate Database - Public Demo
A Streamlit app for exploring college policy debate statistics.
"""

import streamlit as st
import pandas as pd
import psycopg2

# Page config
st.set_page_config(
    page_title="Debate Database",
    page_icon="🎤",
    layout="wide"
)

# Database config - uses Streamlit secrets in production
if hasattr(st, 'secrets') and 'database' in st.secrets:
    DB_CONFIG = {
        'host': st.secrets.database.host,
        'port': st.secrets.database.port,
        'database': st.secrets.database.database,
        'user': st.secrets.database.user,
        'password': st.secrets.database.password
    }
else:
    # Local development fallback
    DB_CONFIG = {
        'host': '134.199.206.247',
        'port': 5432,
        'database': 'debating_db',
        'user': 'debating_user',
        'password': 'lincoln_123'
    }


def run_query(query, params=None):
    """Run a query and return results as a DataFrame."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        columns = [desc[0] for desc in cur.description]
        data = cur.fetchall()
        return pd.DataFrame(data, columns=columns)
    finally:
        conn.close()


@st.cache_data(ttl=300)
def cached_query(query, params=None):
    """Cached version of run_query - results cached for 5 minutes."""
    return run_query(query, tuple(params) if params else None)


st.title("College Policy Debate Database")

# Clear any cached data to ensure fresh queries
st.cache_data.clear()

# Sidebar navigation
page = st.sidebar.radio(
    "Navigate",
    ["Home", "Debater Lookup", "Search Teams", "Leaderboards", "Tournament Lookup"]
)

# ============== HOME PAGE ==============
if page == "Home":
    st.markdown("""
    Welcome to the College Policy Debate Database. This database tracks results
    from varsity policy debate tournaments across the country.

    **What you can do:**
    - **Debater Lookup** - Look up any debater's career record with season-by-season and round-by-round detail
    - **Search Teams** - Find team performance at specific tournaments
    - **Leaderboards** - See top debaters by wins, win percentage, and speaker points
    - **Tournament Lookup** - Browse results from specific tournaments
    """)

    st.subheader("Database Overview")
    col1, col2, col3, col4 = st.columns(4)

    stats = run_query("""
        SELECT
            (SELECT COUNT(*) FROM tournament WHERE is_active IS NOT FALSE) as tournaments,
            (SELECT COUNT(DISTINCT debater_id) FROM debater WHERE is_active IS NOT FALSE) as debaters,
            (SELECT COUNT(*) FROM round_result WHERE is_active IS NOT FALSE) as debates,
            (SELECT COUNT(*) FROM team WHERE is_active IS NOT FALSE) as teams
    """)

    col1.metric("Tournaments", f"{stats['tournaments'].iloc[0]:,}")
    col2.metric("Debaters", f"{stats['debaters'].iloc[0]:,}")
    col3.metric("Debates", f"{stats['debates'].iloc[0]:,}")
    col4.metric("Team Entries", f"{stats['teams'].iloc[0]:,}")


# ============== DEBATER LOOKUP ==============
elif page == "Debater Lookup":
    st.header("Debater Lookup")

    # Load all debaters for dropdown (cached)
    @st.cache_data(ttl=60)
    def get_all_debaters():
        return run_query("""
            SELECT debater_code, first_name, last_name, total_wins, total_losses,
                   win_percentage, avg_speaker_points, tournaments_attended
            FROM debater_career_stats
            WHERE total_wins + total_losses > 0
            ORDER BY last_name, first_name
        """)

    all_debaters = get_all_debaters()

    # Create dropdown options: "Last, First" format for easy typing
    debater_options = ["Select a debater (type to search)..."] + [
        f"{row['last_name']}, {row['first_name']}"
        for _, row in all_debaters.iterrows()
    ]

    selected = st.selectbox("Select Debater", debater_options)

    if selected != "Select a debater (type to search)...":
        idx = debater_options.index(selected) - 1
        debater_code = all_debaters.iloc[idx]['debater_code']
        debater_name = f"{all_debaters.iloc[idx]['first_name']} {all_debaters.iloc[idx]['last_name']}"
        career = all_debaters.iloc[idx]

        st.markdown("---")

        # ===== CAREER SUMMARY (compact) =====
        st.subheader(f"{debater_name}")
        st.markdown(f"**Record:** {career['total_wins']}-{career['total_losses']} ({career['win_percentage']}%) | **Avg Pts:** {career['avg_speaker_points'] or 'N/A'} | **Tournaments:** {career['tournaments_attended']}")

        # ===== FILTERS =====
        @st.cache_data(ttl=60)
        def get_debater_seasons(code):
            return run_query("""
                SELECT DISTINCT t.season
                FROM debater d
                JOIN team_debater td ON d.id = td.debater_id
                JOIN team tm ON td.team_id = tm.id
                JOIN round_result rr ON (rr.aff_team_id = tm.id OR rr.neg_team_id = tm.id) AND rr.is_active IS NOT FALSE
                JOIN round r ON rr.round_id = r.id AND r.is_active IS NOT FALSE
                JOIN tournament t ON r.tournament_id = t.id AND tm.tournament_id = t.id
                WHERE d.debater_id = %s AND d.is_active IS NOT FALSE
                ORDER BY t.season DESC
            """, (code,))

        @st.cache_data(ttl=60)
        def get_debater_tournaments(code):
            return run_query("""
                SELECT DISTINCT t.name, t.season, t.start_date
                FROM debater d
                JOIN team_debater td ON d.id = td.debater_id
                JOIN team tm ON td.team_id = tm.id
                JOIN tournament t ON tm.tournament_id = t.id
                WHERE d.debater_id = %s AND d.is_active IS NOT FALSE
                ORDER BY t.start_date ASC
            """, (code,))

        seasons = get_debater_seasons(debater_code)
        tournaments = get_debater_tournaments(debater_code)

        col1, col2, col3 = st.columns(3)
        with col1:
            season_options = ["All Seasons"] + [s['season'] for s in seasons.to_dict('records')]
            selected_season = st.selectbox("Season", season_options, key="season_filter")
        with col2:
            tourn_list = tournaments.to_dict('records')
            # Format as "Tournament Name (season)" for dropdown display
            tourn_options = []
            tourn_mapping = {}  # Maps display name -> (name, season)
            for t in tourn_list:
                display_name = f"{t['name']} ({t['season']})"
                tourn_options.append(display_name)
                tourn_mapping[display_name] = (t['name'], t['season'])
            selected_tourns = st.multiselect("Tournaments", tourn_options, key="tourn_filter", placeholder="All Tournaments")
        with col3:
            result_options = ["All Results", "Wins Only", "Losses Only"]
            selected_result = st.selectbox("Result", result_options, key="result_filter")

        # ===== ALL ROUNDS TABLE =====
        @st.cache_data(ttl=60)
        def get_all_rounds(code):
            return run_query("""
                SELECT
                    t.season as "Season",
                    t.name as "Tournament",
                    r.round_number as "Rd",
                    -- Aff team: school abbreviation
                    SPLIT_PART(aff_tm.team_name, ' ', 1) as "Aff",
                    -- Aff debater 1
                    (SELECT d2.last_name FROM team_debater td2
                     JOIN debater d2 ON td2.debater_id = d2.id
                     WHERE td2.team_id = rr.aff_team_id
                     ORDER BY d2.last_name LIMIT 1) as "A1",
                    -- Aff debater 1 points (match by last_name)
                    (SELECT rdp.points FROM round_debater_point rdp
                     JOIN debater d2 ON rdp.debater_id = d2.id
                     WHERE rdp.round_result_id = rr.id AND d2.last_name = (
                         SELECT d3.last_name FROM team_debater td3
                         JOIN debater d3 ON td3.debater_id = d3.id
                         WHERE td3.team_id = rr.aff_team_id
                         ORDER BY d3.last_name LIMIT 1
                     ) LIMIT 1) as "P1",
                    -- Aff debater 2
                    (SELECT d2.last_name FROM team_debater td2
                     JOIN debater d2 ON td2.debater_id = d2.id
                     WHERE td2.team_id = rr.aff_team_id
                     ORDER BY d2.last_name LIMIT 1 OFFSET 1) as "A2",
                    -- Aff debater 2 points (match by last_name)
                    (SELECT rdp.points FROM round_debater_point rdp
                     JOIN debater d2 ON rdp.debater_id = d2.id
                     WHERE rdp.round_result_id = rr.id AND d2.last_name = (
                         SELECT d3.last_name FROM team_debater td3
                         JOIN debater d3 ON td3.debater_id = d3.id
                         WHERE td3.team_id = rr.aff_team_id
                         ORDER BY d3.last_name LIMIT 1 OFFSET 1
                     ) LIMIT 1) as "P2",
                    -- Neg team: school abbreviation
                    SPLIT_PART(neg_tm.team_name, ' ', 1) as "Neg",
                    -- Neg debater 1
                    (SELECT d2.last_name FROM team_debater td2
                     JOIN debater d2 ON td2.debater_id = d2.id
                     WHERE td2.team_id = rr.neg_team_id
                     ORDER BY d2.last_name LIMIT 1) as "N1",
                    -- Neg debater 1 points (match by last_name)
                    (SELECT rdp.points FROM round_debater_point rdp
                     JOIN debater d2 ON rdp.debater_id = d2.id
                     WHERE rdp.round_result_id = rr.id AND d2.last_name = (
                         SELECT d3.last_name FROM team_debater td3
                         JOIN debater d3 ON td3.debater_id = d3.id
                         WHERE td3.team_id = rr.neg_team_id
                         ORDER BY d3.last_name LIMIT 1
                     ) LIMIT 1) as "P3",
                    -- Neg debater 2
                    (SELECT d2.last_name FROM team_debater td2
                     JOIN debater d2 ON td2.debater_id = d2.id
                     WHERE td2.team_id = rr.neg_team_id
                     ORDER BY d2.last_name LIMIT 1 OFFSET 1) as "N2",
                    -- Neg debater 2 points (match by last_name)
                    (SELECT rdp.points FROM round_debater_point rdp
                     JOIN debater d2 ON rdp.debater_id = d2.id
                     WHERE rdp.round_result_id = rr.id AND d2.last_name = (
                         SELECT d3.last_name FROM team_debater td3
                         JOIN debater d3 ON td3.debater_id = d3.id
                         WHERE td3.team_id = rr.neg_team_id
                         ORDER BY d3.last_name LIMIT 1 OFFSET 1
                     ) LIMIT 1) as "P4",
                    -- Judge
                    (SELECT string_agg(j.name, ', ')
                     FROM round_judges_vote rjv
                     JOIN judge j ON rjv.judge_id = j.id
                     WHERE rjv.round_result_id = rr.id) as "Judge",
                    -- Decision (which side won)
                    CASE
                        WHEN rr.winner = 1 THEN 'AFF'
                        WHEN rr.winner = 2 THEN 'NEG'
                        WHEN rr.winner = -1 THEN 'BYE'
                        ELSE ''
                    END as "Dec",
                    -- Result for the searched debater
                    CASE
                        WHEN rr.winner = -1 THEN 'BYE'
                        WHEN (rr.aff_team_id = tm.id AND rr.winner = 1) OR (rr.neg_team_id = tm.id AND rr.winner = 2) THEN 'W'
                        ELSE 'L'
                    END as "W/L",
                    t.start_date as sort_date
                FROM debater d
                JOIN team_debater td ON d.id = td.debater_id
                JOIN team tm ON td.team_id = tm.id
                JOIN round_result rr ON (rr.aff_team_id = tm.id OR rr.neg_team_id = tm.id) AND rr.is_active IS NOT FALSE
                JOIN round r ON rr.round_id = r.id AND r.is_active IS NOT FALSE
                JOIN tournament t ON r.tournament_id = t.id AND tm.tournament_id = t.id
                LEFT JOIN team aff_tm ON rr.aff_team_id = aff_tm.id
                LEFT JOIN team neg_tm ON rr.neg_team_id = neg_tm.id
                WHERE d.debater_id = %s AND d.is_active IS NOT FALSE
                GROUP BY t.season, t.name, t.start_date, r.round_number, r.round_type, rr.aff_team_id, rr.neg_team_id,
                         tm.id, rr.id, rr.winner, aff_tm.team_name, neg_tm.team_name
                ORDER BY t.start_date ASC,
                         CASE WHEN r.round_type = 'elim' THEN 1 ELSE 0 END ASC,
                         CASE
                             WHEN r.round_type = 'prelim' THEN
                                 CASE WHEN REGEXP_REPLACE(r.round_number, '[^0-9]', '', 'g') = '' THEN 0
                                      ELSE CAST(REGEXP_REPLACE(r.round_number, '[^0-9]', '', 'g') AS INTEGER)
                                 END
                             WHEN LOWER(r.round_number) LIKE '%%runoff%%' THEN 1
                             WHEN LOWER(r.round_number) LIKE '%%triple%%' THEN 2
                             WHEN LOWER(r.round_number) LIKE '%%double%%' THEN 3
                             WHEN LOWER(r.round_number) LIKE '%%octa%%' OR LOWER(r.round_number) LIKE '%%octo%%' OR LOWER(r.round_number) = 'octos' THEN 4
                             WHEN LOWER(r.round_number) LIKE '%%quarter%%' OR LOWER(r.round_number) = 'quarters' THEN 5
                             WHEN LOWER(r.round_number) LIKE '%%semi%%' OR LOWER(r.round_number) = 'semis' THEN 6
                             WHEN LOWER(r.round_number) LIKE '%%final%%' THEN 7
                             ELSE 0
                         END ASC
            """, (code,))

        all_rounds = get_all_rounds(debater_code)

        # Apply filters
        filtered = all_rounds.copy()
        if selected_season != "All Seasons":
            filtered = filtered[filtered['Season'] == selected_season]
        if selected_tourns:  # If any tournaments selected in multi-select
            # Filter by both tournament name AND season using the mapping
            selected_pairs = [tourn_mapping[t] for t in selected_tourns]
            mask = filtered.apply(lambda row: (row['Tournament'], row['Season']) in selected_pairs, axis=1)
            filtered = filtered[mask]
        if selected_result == "Wins Only":
            filtered = filtered[filtered['W/L'] == 'W']
        elif selected_result == "Losses Only":
            filtered = filtered[filtered['W/L'] == 'L']

        # Drop the sort column before display
        display_df = filtered.drop(columns=['sort_date'])

        # Replace None with dash for points columns
        for col in ['P1', 'P2', 'P3', 'P4']:
            display_df[col] = display_df[col].fillna('-')

        st.markdown(f"**Showing {len(display_df)} rounds**")
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=600)


# ============== SEARCH TEAMS ==============
elif page == "Search Teams":
    st.header("Search Teams")

    col1, col2 = st.columns(2)
    with col1:
        team_search = st.text_input("Team Name", placeholder="e.g., Kansas or Harvard AK")
    with col2:
        year_filter = st.selectbox("Year (optional)", ["All Years"] + list(range(2026, 2011, -1)))

    if team_search:
        if year_filter != "All Years":
            query = """
                SELECT team_name as "Team", tournament_name as "Tournament",
                       tournament_year as "Year", prelim_record as "Prelim Record",
                       avg_speaker_points as "Avg Pts", elim_wins as "Elim W", elim_losses as "Elim L"
                FROM team_tournament_stats
                WHERE LOWER(team_name) LIKE LOWER(%s) AND tournament_year = %s
                ORDER BY tournament_year DESC, prelim_wins DESC LIMIT 200
            """
            params = (f"%{team_search}%", year_filter)
        else:
            query = """
                SELECT team_name as "Team", tournament_name as "Tournament",
                       tournament_year as "Year", prelim_record as "Prelim Record",
                       avg_speaker_points as "Avg Pts", elim_wins as "Elim W", elim_losses as "Elim L"
                FROM team_tournament_stats
                WHERE LOWER(team_name) LIKE LOWER(%s)
                ORDER BY tournament_year DESC, prelim_wins DESC LIMIT 200
            """
            params = (f"%{team_search}%",)

        results = run_query(query, params)

        if len(results) > 0:
            st.success(f"Found {len(results)} result(s)")
            st.dataframe(results, use_container_width=True, hide_index=True)
        else:
            st.warning("No teams found matching that search.")


# ============== LEADERBOARDS ==============
elif page == "Leaderboards":
    st.header("Leaderboards")

    leaderboard_type = st.selectbox(
        "Select Leaderboard",
        ["Most Career Wins", "Highest Win Percentage (50+ wins)",
         "Highest Win Percentage (100+ wins)", "Best Average Speaker Points (50+ rounds)",
         "Most Tournaments Attended", "Most Elim Wins"]
    )

    if leaderboard_type == "Most Career Wins":
        results = run_query("""
            SELECT debater_code as "Code", first_name as "First", last_name as "Last",
                   total_wins as "Wins", total_losses as "Losses", win_percentage as "Win %",
                   tournaments_attended as "Tourneys"
            FROM debater_career_stats WHERE total_wins > 0
            ORDER BY total_wins DESC LIMIT 50
        """)

    elif leaderboard_type == "Highest Win Percentage (50+ wins)":
        results = run_query("""
            SELECT debater_code as "Code", first_name as "First", last_name as "Last",
                   total_wins as "Wins", total_losses as "Losses", win_percentage as "Win %",
                   tournaments_attended as "Tourneys"
            FROM debater_career_stats WHERE total_wins >= 50
            ORDER BY win_percentage DESC NULLS LAST LIMIT 50
        """)

    elif leaderboard_type == "Highest Win Percentage (100+ wins)":
        results = run_query("""
            SELECT debater_code as "Code", first_name as "First", last_name as "Last",
                   total_wins as "Wins", total_losses as "Losses", win_percentage as "Win %",
                   tournaments_attended as "Tourneys"
            FROM debater_career_stats WHERE total_wins >= 100
            ORDER BY win_percentage DESC NULLS LAST LIMIT 50
        """)

    elif leaderboard_type == "Best Average Speaker Points (50+ rounds)":
        results = run_query("""
            SELECT debater_code as "Code", first_name as "First", last_name as "Last",
                   avg_speaker_points as "Avg Pts", prelim_rounds_with_points as "Rounds",
                   total_wins as "Wins", win_percentage as "Win %"
            FROM debater_career_stats WHERE prelim_rounds_with_points >= 50
            ORDER BY avg_speaker_points DESC NULLS LAST LIMIT 50
        """)

    elif leaderboard_type == "Most Tournaments Attended":
        results = run_query("""
            SELECT debater_code as "Code", first_name as "First", last_name as "Last",
                   tournaments_attended as "Tourneys", total_wins as "Wins",
                   total_losses as "Losses", win_percentage as "Win %"
            FROM debater_career_stats WHERE tournaments_attended > 0
            ORDER BY tournaments_attended DESC LIMIT 50
        """)

    elif leaderboard_type == "Most Elim Wins":
        results = run_query("""
            SELECT debater_code as "Code", first_name as "First", last_name as "Last",
                   elim_wins as "Elim W", elim_losses as "Elim L",
                   total_wins as "Total W", win_percentage as "Win %"
            FROM debater_career_stats WHERE elim_wins > 0
            ORDER BY elim_wins DESC LIMIT 50
        """)

    st.dataframe(results, use_container_width=True, hide_index=True)


# ============== TOURNAMENT LOOKUP ==============
elif page == "Tournament Lookup":
    st.header("Tournament Lookup")

    # Search and filter controls
    col1, col2 = st.columns(2)
    with col1:
        search_term = st.text_input("Search tournaments", placeholder="e.g., NDT, Wake Forest, Kentucky")
    with col2:
        seasons = run_query("""
            SELECT DISTINCT season FROM tournament
            WHERE is_active IS NOT FALSE AND season IS NOT NULL
            ORDER BY season DESC
        """)
        season_list = ["All Seasons"] + [s['season'] for s in seasons.to_dict('records')]
        selected_season = st.selectbox("Season", season_list, key="tourn_season_filter")

    # Build query based on filters - order by date ascending (chronological)
    if search_term and selected_season != "All Seasons":
        tournaments = run_query("""
            SELECT id, name, season, start_date FROM tournament
            WHERE is_active IS NOT FALSE AND LOWER(name) LIKE LOWER(%s) AND season = %s
            ORDER BY start_date ASC NULLS LAST
        """, (f"%{search_term}%", selected_season))
    elif search_term:
        tournaments = run_query("""
            SELECT id, name, season, start_date FROM tournament
            WHERE is_active IS NOT FALSE AND LOWER(name) LIKE LOWER(%s)
            ORDER BY start_date ASC NULLS LAST
        """, (f"%{search_term}%",))
    elif selected_season != "All Seasons":
        tournaments = run_query("""
            SELECT id, name, season, start_date FROM tournament
            WHERE is_active IS NOT FALSE AND season = %s
            ORDER BY start_date ASC NULLS LAST
        """, (selected_season,))
    else:
        tournaments = run_query("""
            SELECT id, name, season, start_date FROM tournament
            WHERE is_active IS NOT FALSE ORDER BY start_date DESC NULLS LAST LIMIT 100
        """)

    if len(tournaments) > 0:
        tournament_options = ["Select a tournament..."] + [
            f"{row['name']} ({row['season']})" for _, row in tournaments.iterrows()
        ]

        selected = st.selectbox("Tournament", tournament_options)

        if selected != "Select a tournament...":
            idx = tournament_options.index(selected) - 1
            tournament_id = int(tournaments.iloc[idx]['id'])

            st.subheader(f"Results: {selected}")

            # Create tabs
            tab1, tab2, tab3, tab4 = st.tabs(["Standings", "Elim Results", "By Round", "Team Lookup"])

            # ===== TAB 1: STANDINGS =====
            with tab1:
                standings = run_query("""
                    SELECT
                        t.team_name as "Team",
                        (SELECT string_agg(TRIM(COALESCE(d.first_name, '') || ' ' || COALESCE(d.last_name, '')), ', ' ORDER BY d.last_name)
                         FROM team_debater td JOIN debater d ON td.debater_id = d.id
                         WHERE td.team_id = t.id) as "Debaters",
                        (SELECT COUNT(*) FROM round_result rr2
                         JOIN round r2 ON rr2.round_id = r2.id
                         WHERE ((rr2.aff_team_id = t.id AND rr2.winner = 1) OR
                                (rr2.neg_team_id = t.id AND rr2.winner = 2))
                           AND r2.round_type = 'prelim' AND rr2.is_active IS NOT FALSE)
                        || '-' ||
                        (SELECT COUNT(*) FROM round_result rr2
                         JOIN round r2 ON rr2.round_id = r2.id
                         WHERE ((rr2.aff_team_id = t.id AND rr2.winner = 2) OR
                                (rr2.neg_team_id = t.id AND rr2.winner = 1))
                           AND r2.round_type = 'prelim' AND rr2.is_active IS NOT FALSE) as "Record"
                    FROM team t
                    WHERE t.tournament_id = %s AND t.is_active IS NOT FALSE
                    ORDER BY (SELECT COUNT(*) FROM round_result rr2
                         JOIN round r2 ON rr2.round_id = r2.id
                         WHERE ((rr2.aff_team_id = t.id AND rr2.winner = 1) OR
                                (rr2.neg_team_id = t.id AND rr2.winner = 2))
                           AND r2.round_type = 'prelim' AND rr2.is_active IS NOT FALSE) DESC,
                         t.team_name ASC
                """, (tournament_id,))

                if len(standings) > 0:
                    # Initialize session state
                    if 'selected_standing_team' not in st.session_state:
                        st.session_state.selected_standing_team = None

                    selected_team_name = st.session_state.selected_standing_team

                    # Show team results FIRST (above standings) if a team is selected
                    if selected_team_name:
                        team_info = run_query("""
                            SELECT id FROM team WHERE team_name = %s AND tournament_id = %s
                        """, (selected_team_name, tournament_id))

                        if len(team_info) > 0:
                            team_id = int(team_info.iloc[0]['id'])

                            # Header with close button
                            header_col, close_col = st.columns([4, 1])
                            header_col.markdown(f"#### {selected_team_name} - Round by Round")
                            if close_col.button("✕ Close", key="close_results"):
                                st.session_state.selected_standing_team = None
                                st.rerun()

                            team_rounds = run_query("""
                                SELECT
                                    r.round_number as "Rd",
                                    CASE WHEN rr.aff_team_id = %s THEN 'Aff' ELSE 'Neg' END as "Side",
                                    CASE WHEN rr.aff_team_id = %s THEN neg_tm.team_name ELSE aff_tm.team_name END as "Opponent",
                                    (SELECT string_agg(
                                         CASE WHEN rjv.vote != rr.winner THEN j.name || '*' ELSE j.name END,
                                         ', ')
                                     FROM round_judges_vote rjv JOIN judge j ON rjv.judge_id = j.id
                                     WHERE rjv.round_result_id = rr.id) as "Judge",
                                    CASE
                                        WHEN rr.winner = -1 THEN 'BYE'
                                        WHEN (rr.aff_team_id = %s AND rr.winner = 1) OR (rr.neg_team_id = %s AND rr.winner = 2) THEN
                                            CASE WHEN r.round_type = 'elim' AND rr.ballot_count IS NOT NULL AND rr.ballot_count != ''
                                                 THEN 'W (' || rr.ballot_count || ')'
                                                 ELSE 'W'
                                            END
                                        ELSE
                                            CASE WHEN r.round_type = 'elim' AND rr.ballot_count IS NOT NULL AND rr.ballot_count != ''
                                                 THEN 'L (' || rr.ballot_count || ')'
                                                 ELSE 'L'
                                            END
                                    END as "Result"
                                FROM round_result rr
                                JOIN round r ON rr.round_id = r.id
                                JOIN team aff_tm ON rr.aff_team_id = aff_tm.id
                                JOIN team neg_tm ON rr.neg_team_id = neg_tm.id
                                WHERE (rr.aff_team_id = %s OR rr.neg_team_id = %s)
                                    AND r.tournament_id = %s
                                    AND rr.is_active IS NOT FALSE
                                ORDER BY CASE WHEN r.round_type = 'prelim' THEN 0 ELSE 1 END,
                                         CASE WHEN REGEXP_REPLACE(r.round_number, '[^0-9]', '', 'g') = '' THEN 0
                                              ELSE CAST(REGEXP_REPLACE(r.round_number, '[^0-9]', '', 'g') AS INTEGER) END
                            """, (team_id, team_id, team_id, team_id, team_id, team_id, tournament_id))

                            if len(team_rounds) > 0:
                                # Auto-size height based on rows
                                row_height = 35
                                table_height = (len(team_rounds) + 1) * row_height + 10
                                st.dataframe(
                                    team_rounds,
                                    hide_index=True,
                                    use_container_width=True,
                                    height=table_height,
                                    column_config={
                                        "Rd": st.column_config.TextColumn(width="small"),
                                        "Side": st.column_config.TextColumn(width="small"),
                                        "Opponent": st.column_config.TextColumn(width="medium"),
                                        "Judge": st.column_config.TextColumn(width="large"),
                                        "Result": st.column_config.TextColumn(width="small")
                                    }
                                )

                        st.markdown("---")

                    # Standings with Full Results buttons
                    st.markdown("#### Standings")
                    left_section, _ = st.columns([3, 1])
                    with left_section:
                        with st.container(height=500):
                            for idx, row in standings.iterrows():
                                c1, c2, c3, c4 = st.columns([1.2, 2, 0.5, 0.8], gap="small")
                                c1.write(row['Team'])
                                c2.write(row['Debaters'] or "")
                                c3.write(row['Record'])
                                if c4.button("Full Results", key=f"btn_{idx}"):
                                    st.session_state.selected_standing_team = row['Team']
                                    st.rerun()
                else:
                    st.info("No standings available.")

            # ===== TAB 2: ELIM RESULTS =====
            with tab2:
                elim_results = run_query("""
                    SELECT
                        CASE
                            WHEN LOWER(r.round_number) LIKE '%%double%%' THEN 'Doubles'
                            WHEN LOWER(r.round_number) LIKE '%%triple%%' THEN 'Triples'
                            WHEN LOWER(r.round_number) LIKE '%%octa%%' OR LOWER(r.round_number) LIKE '%%octo%%' THEN 'Octas'
                            WHEN LOWER(r.round_number) LIKE '%%quarter%%' THEN 'Quarters'
                            WHEN LOWER(r.round_number) LIKE '%%semi%%' THEN 'Semis'
                            WHEN LOWER(r.round_number) LIKE '%%final%%' AND LOWER(r.round_number) NOT LIKE '%%semi%%' THEN 'Finals'
                            WHEN LOWER(r.round_number) LIKE '%%runoff%%' THEN 'Runoff'
                            ELSE r.round_number
                        END as "Rd",
                        aff_tm.team_name as "Aff",
                        COALESCE(neg_tm.team_name, 'BYE') as "Neg",
                        (SELECT string_agg(
                             CASE WHEN rjv.vote != rr.winner THEN j.name || '*' ELSE j.name END,
                             ', ')
                         FROM round_judges_vote rjv JOIN judge j ON rjv.judge_id = j.id
                         WHERE rjv.round_result_id = rr.id) as "Judges",
                        CASE WHEN rr.result_type = 'bye' THEN 'BYE'
                             WHEN rr.result_type = 'closeout' THEN 'CLOSEOUT'
                             WHEN rr.result_type = 'forfeit' THEN 'FORFEIT'
                             WHEN rr.winner = 1 THEN 'AFF ' || COALESCE(rr.ballot_count, '')
                             WHEN rr.winner = 2 THEN 'NEG ' || COALESCE(rr.ballot_count, '')
                             WHEN rr.winner = -1 THEN COALESCE(rr.ballot_count, '')
                        END as "Decision"
                    FROM round_result rr
                    JOIN round r ON rr.round_id = r.id
                    JOIN team aff_tm ON rr.aff_team_id = aff_tm.id
                    LEFT JOIN team neg_tm ON rr.neg_team_id = neg_tm.id
                    WHERE r.tournament_id = %s AND r.round_type = 'elim' AND rr.is_active IS NOT FALSE
                    ORDER BY CASE
                        WHEN LOWER(r.round_number) LIKE '%%runoff%%' THEN 1
                        WHEN LOWER(r.round_number) LIKE '%%triple%%' THEN 2
                        WHEN LOWER(r.round_number) LIKE '%%double%%' THEN 3
                        WHEN LOWER(r.round_number) LIKE '%%octa%%' OR LOWER(r.round_number) LIKE '%%octo%%' THEN 4
                        WHEN LOWER(r.round_number) LIKE '%%quarter%%' THEN 5
                        WHEN LOWER(r.round_number) LIKE '%%semi%%' THEN 6
                        WHEN LOWER(r.round_number) LIKE '%%final%%' THEN 7
                        ELSE 0
                    END DESC, aff_tm.team_name
                """, (tournament_id,))

                if len(elim_results) > 0:
                    left_col, _ = st.columns([4, 1])
                    with left_col:
                        st.dataframe(
                            elim_results,
                            use_container_width=True,
                            hide_index=True,
                            height=500,
                            column_config={
                                "Rd": st.column_config.TextColumn(width=80),
                                "Aff": st.column_config.TextColumn(width=120),
                                "Neg": st.column_config.TextColumn(width=120),
                                "Judges": st.column_config.TextColumn(width=200),
                                "Decision": st.column_config.TextColumn(width=80)
                            }
                        )
                else:
                    st.info("No elim results available.")

            # ===== TAB 3: BY ROUND =====
            with tab3:
                # Get available rounds
                rounds = run_query("""
                    SELECT DISTINCT round_number, round_type,
                        CASE WHEN round_type = 'prelim' THEN 0 ELSE 1 END as type_order,
                        CASE WHEN REGEXP_REPLACE(round_number, '[^0-9]', '', 'g') = '' THEN 0
                             ELSE CAST(REGEXP_REPLACE(round_number, '[^0-9]', '', 'g') AS INTEGER) END as num_order
                    FROM round WHERE tournament_id = %s
                    ORDER BY type_order, num_order
                """, (tournament_id,))

                if len(rounds) > 0:
                    round_options = rounds['round_number'].tolist()
                    selected_round = st.selectbox("Select Round", round_options, key="round_select")

                    round_results = run_query("""
                        SELECT
                            aff_tm.team_name as "Aff",
                            (SELECT string_agg(d.last_name || ' (' || COALESCE(rdp.points::text, '-') || ')', ', ' ORDER BY d.last_name)
                             FROM team_debater td
                             JOIN debater d ON td.debater_id = d.id
                             LEFT JOIN round_debater_point rdp ON rdp.round_result_id = rr.id AND rdp.debater_id = d.id
                             WHERE td.team_id = rr.aff_team_id) as "Aff Debaters",
                            neg_tm.team_name as "Neg",
                            (SELECT string_agg(d.last_name || ' (' || COALESCE(rdp.points::text, '-') || ')', ', ' ORDER BY d.last_name)
                             FROM team_debater td
                             JOIN debater d ON td.debater_id = d.id
                             LEFT JOIN round_debater_point rdp ON rdp.round_result_id = rr.id AND rdp.debater_id = d.id
                             WHERE td.team_id = rr.neg_team_id) as "Neg Debaters",
                            (SELECT string_agg(
                                 CASE WHEN rjv.vote != rr.winner THEN j.name || '*' ELSE j.name END,
                                 ', ')
                             FROM round_judges_vote rjv JOIN judge j ON rjv.judge_id = j.id
                             WHERE rjv.round_result_id = rr.id) as "Judge",
                            CASE WHEN rr.winner = 1 THEN 'AFF'
                                 WHEN rr.winner = 2 THEN 'NEG'
                                 WHEN rr.winner = -1 THEN 'BYE'
                            END as "Dec"
                        FROM round_result rr
                        JOIN round r ON rr.round_id = r.id
                        JOIN team aff_tm ON rr.aff_team_id = aff_tm.id
                        JOIN team neg_tm ON rr.neg_team_id = neg_tm.id
                        WHERE r.tournament_id = %s AND r.round_number = %s AND rr.is_active IS NOT FALSE
                        ORDER BY aff_tm.team_name
                    """, (tournament_id, selected_round))

                    if len(round_results) > 0:
                        st.dataframe(round_results, use_container_width=True, hide_index=True)
                    else:
                        st.info("No results for this round.")
                else:
                    st.info("No rounds available.")

            # ===== TAB 4: TEAM LOOKUP =====
            with tab4:
                # Get teams at this tournament
                teams = run_query("""
                    SELECT id, team_name FROM team
                    WHERE tournament_id = %s AND is_active IS NOT FALSE
                    ORDER BY team_name
                """, (tournament_id,))

                if len(teams) > 0:
                    team_options = teams['team_name'].tolist()
                    selected_team = st.selectbox("Select Team", team_options, key="team_select")

                    team_id = int(teams[teams['team_name'] == selected_team]['id'].iloc[0])

                    team_rounds = run_query("""
                        SELECT
                            r.round_number as "Rd",
                            CASE WHEN rr.aff_team_id = %s THEN 'Aff' ELSE 'Neg' END as "Side",
                            CASE WHEN rr.aff_team_id = %s THEN neg_tm.team_name ELSE aff_tm.team_name END as "Opponent",
                            (SELECT string_agg(
                                 CASE WHEN rjv.vote != rr.winner THEN j.name || '*' ELSE j.name END,
                                 ', ')
                             FROM round_judges_vote rjv JOIN judge j ON rjv.judge_id = j.id
                             WHERE rjv.round_result_id = rr.id) as "Judge",
                            CASE
                                WHEN rr.winner = -1 THEN 'BYE'
                                WHEN (rr.aff_team_id = %s AND rr.winner = 1) OR (rr.neg_team_id = %s AND rr.winner = 2) THEN 'W'
                                ELSE 'L'
                            END as "Result"
                        FROM round_result rr
                        JOIN round r ON rr.round_id = r.id
                        JOIN team aff_tm ON rr.aff_team_id = aff_tm.id
                        JOIN team neg_tm ON rr.neg_team_id = neg_tm.id
                        WHERE (rr.aff_team_id = %s OR rr.neg_team_id = %s)
                            AND r.tournament_id = %s
                            AND rr.is_active IS NOT FALSE
                        ORDER BY CASE WHEN r.round_type = 'prelim' THEN 0 ELSE 1 END,
                                 CASE WHEN REGEXP_REPLACE(r.round_number, '[^0-9]', '', 'g') = '' THEN 0
                                      ELSE CAST(REGEXP_REPLACE(r.round_number, '[^0-9]', '', 'g') AS INTEGER) END
                    """, (team_id, team_id, team_id, team_id, team_id, team_id, tournament_id))

                    if len(team_rounds) > 0:
                        # Show team summary
                        wins = len(team_rounds[team_rounds['Result'] == 'W'])
                        losses = len(team_rounds[team_rounds['Result'] == 'L'])
                        st.markdown(f"**Record: {wins}-{losses}**")
                        st.dataframe(team_rounds, use_container_width=True, hide_index=True)
                    else:
                        st.info("No results for this team.")
                else:
                    st.info("No teams found.")
    else:
        st.info("No tournaments found. Try a different search term or season.")


# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("*College Policy Debate Database*")
