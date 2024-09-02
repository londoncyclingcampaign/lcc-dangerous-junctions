import psutil
import logging
import streamlit as st

from src.app_functions import *
from streamlit_folium import st_folium

st.set_page_config(layout='wide')

# apply css styling
with open('./css/style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

st.markdown(
    """
        <header class="css-18ni7ap ezrtsby2" tabindex="-1">
        <div class="header">
        <a href="https://lcc.org.uk/">
        <img src="https://lcc.org.uk/wp-content/themes/lcc/src/img/svgs/logo-white.svg" alt="London Cycling Campaign logo" class="logo">
        </a>
        <h1 class="title">Dangerous <br/> Junctions Tool</h1>
        </div>
        </header>
    """,
    unsafe_allow_html=True
)


logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logging.info(f'Current memory usage: {psutil.Process(os.getpid()).memory_info().rss / 1024 ** 2} MB')


junctions, collisions, notes = read_in_data(tolerance=15)
min_year = np.min(collisions['year'])
max_year = np.max(collisions['year'])

with st.expander("App settings", expanded=True):
    with st.form(key='form'):
        col1, col2, col3, col4 = st.columns([2, 4, 4, 2])
        with col1:
            casualty_type = st.radio(
                label='Select casualty type',
                options=['cyclist', 'pedestrian'],
                format_func=lambda x: f'{x}s',
                horizontal=True
            )
        with col2:
            n_junctions = st.slider(
                label='Number of dangerous junctions to show',
                min_value=1,
                max_value=100,  # not sure we'd ever need to view more then 100?
                value=20
            )
        with col3:
            available_boroughs = sorted(
                list(
                    collisions['borough'].dropna().unique()
                )
            )
            boroughs = st.multiselect(
                label='Filter by borough',
                options=['ALL'] + available_boroughs,
                default='ALL'
            )
        with col4:
            st.markdown('<br>', unsafe_allow_html=True)  # padding
            submit = st.form_submit_button(label='Recalculate Junctions', type='primary', use_container_width=True)


if len(boroughs) == 0:
    st.warning('Please select at least one borough and recalculate', icon='⚠️')
else:
    junction_collisions = combine_junctions_and_collisions(
        junctions,
        collisions,
        notes,
        casualty_type,
        boroughs
    )
    dangerous_junctions = calculate_dangerous_junctions(
        junction_collisions,
        n_junctions,
        casualty_type
    )

    # set default to worst junction...
    if (
        ('chosen_point' not in st.session_state) or
        (casualty_type != st.session_state['previous_casualty_type']) or
        (boroughs != st.session_state['previous_boroughs'])
    ):
        st.session_state['chosen_point'] = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].values[0]

    st.session_state['previous_casualty_type'] = casualty_type
    st.session_state['previous_boroughs'] = boroughs

    col1, col2 = st.columns([6, 6])
    with col1:
        if 'ALL' in boroughs:
            borough_msg = 'all boroughs'
        else:
            borough_msg = ', '.join([b.capitalize() for b in boroughs])

        st.markdown(f'''
            #### Dangerous Junctions

            Map shows the {n_junctions} most dangerous junctions in {borough_msg} from {min_year} to {max_year}.
        ''')

        high_map = create_base_map(initial_location=[51.5080, -.1281], initial_zoom=10)  # set to trafalgar sq.

        high_feature_group = get_high_level_fg(dangerous_junctions, junction_collisions, n_junctions)
        map_click = st_folium(
            high_map,
            feature_group_to_add=high_feature_group,
            returned_objects=['last_object_clicked'],
            use_container_width=True,
            height=500,
            key='high_map'
        )

        if map_click['last_object_clicked']:
            st.session_state['chosen_point'] = [
                map_click['last_object_clicked']['lat'],
                map_click['last_object_clicked']['lng']
            ]

    with col2:
        st.markdown('''
            #### Investigate Junction

            Select a point on the left map and drill down into it here.
        ''')

        initial_junction_location = get_most_dangerous_junction_location(
            dangerous_junctions.head(1)
        )
        low_map = create_base_map(initial_location=initial_junction_location, initial_zoom=18)

        low_feature_group = get_low_level_fg(
            dangerous_junctions,
            junction_collisions,
            n_junctions,
            casualty_type
        )
        st_folium(
            low_map,
            feature_group_to_add=low_feature_group,
            center=st.session_state['chosen_point'],
            returned_objects=[],
            use_container_width=True,
            height=500,
            key='low_map'
        )


st.markdown(f'''
    #### Danger Metrics
            
    Junctions ranked from most to least dangerous
''')

st.dataframe(
    dangerous_junctions[[
        'junction_rank',
        'junction_cluster_name',
        'recency_danger_metric',
        f'fatal_{casualty_type}_casualties',
        f'serious_{casualty_type}_casualties',
        f'slight_{casualty_type}_casualties',
        'yearly_danger_metrics'
    ]],
    column_config={
        'junction_rank': 'Junction rank',
        'junction_cluster_name': 'Junction name',
        'recency_danger_metric': st.column_config.NumberColumn(
            'Danger metric',
            format='%.2f',
            help='Danger metric including recency scaling'
        ),
        f'fatal_{casualty_type}_casualties': f'Fatal {casualty_type} collisions',
        f'serious_{casualty_type}_casualties': f'Serious {casualty_type} collisions',
        f'slight_{casualty_type}_casualties': f'Slight {casualty_type} collisions',
        'yearly_danger_metrics': st.column_config.LineChartColumn(
            "Yearly danger metrics (past 5 years)",
            help='Last 5 years of danger metrics (recency scaled removed)',
            y_min=0,
            y_max=10
        ),
    },
    use_container_width=True,
    hide_index=True
)

with st.expander("About this app"):
    col1, col2 = st.columns(2)

    with col1:
        st.write("""
            ##### LCC's dangerous junctions tool
                 
            Welcome to the London Cycling Campaign's Dangerous Junctions tool. The tool displays the most dangerous
            junctions in London for either cyclists or pedestrians, depending on the settings you've selected. You can
            also filter to specific boroughs or change the number of junctions displayed using the options in the panel at
            the top of the page. It's designed to assist LCC and other organisations to campaign for improvements to road networks in London, helping to make junctions safer
            for both cyclists and pedestrians.

            The 'dangerous junctions' map to the top left plots the top junctions, ranked in descending order from most to least dangerous.
            By clicking on a junction you can find more information about it. The ranking can also be viewed via
            the table below the maps, which also includes the (non recency weighted) danger metric for the last 5 years to help
            spot trends.

            Selecting a junction on the 'dangerous junctions' map updates the 'investigate junction' map to
            display the same junction, showing you the individual collisions that have been assigned
            to that junction for further interrogation. Selecting individual collisions
            displays more info and a link to access the full collision report on the CycleStreets website.

            For the best experience, view this on a desktop or other larger screen device.
                
            ##### The data
                 
            The collision data is sourced from the TfL collision extracts,
            which can be [accessed here](https://tfl.gov.uk/corporate/publications-and-reports/road-safety) and includes all
            collisions involving a cyclist or pedestrian from 2018 to 2022. The junction data is generated using the
            [OSMnx package](https://github.com/gboeing/osmnx) that relies on OpenStreetMap data.
                
            ##### Contact

            This app was made by [Daniel Hills](https://danielhills.github.io/) on behalf of the LCC. For any questions, 
            feedback or bug reports, email: [djmapping@lcc.org.uk](mailto:djmapping@lcc.org.uk)
        """)

    with col2:
        st.markdown("""
            ##### The approach
                    
            The most dangerous junctions in London are identified as follows:
            1. Generate a network of all junctions in London
            2. Consolidate the junctions to a level that make sense. For example, at Trafalgar Square
            we'd ideally want to assess the danger of the junction as a whole,
            rather than each individual pedestrian crossings and intersections that make up the junction
            3. Map each collision to its nearest junction based on coordinate data
            4. Assign each collision a 'danger metric' value based on the severity of the worst
            casualty involved (`6.8` for fatal, `1` for severe & `.06` for slight) and weight this by 
            how recent the collision was (`1` for 2022 down to `.78` for 2018)
            5. Aggregate the individual danger metrics across each junction to get an overall
            danger metric value for each junction
            6. Rank junctions from most to least dangerous based on this value
                    
            This process is done separately for both cycling and pedestrian collisions.
                
            ##### Limitations
                    
            Due to the way the collisions are assigned and aggregated the exact ranking of
            junctions may not be perfect. Junctions are not weighted by how much cycling or
            pedestrian volume they cater for, so this will also impact the ranking.
                    
            The ability to drill down into a junction and assess the individual collisions
            in combination with user domain knowledge should still make this a very useful tool
            in assessing the danger of junctions in London.
        """)

# log highest memory objects
# for key, val in get_highest_memory_objects(locals()).items():
    # logging.info(f'{key}: {val} MB')
