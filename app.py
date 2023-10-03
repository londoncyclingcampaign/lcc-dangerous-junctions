import streamlit as st
import plotly.express as px

from src.app_functions import *
from streamlit_folium import st_folium

st.set_page_config(layout='wide')

st.markdown(
    """
        <header class="css-18ni7ap ezrtsby2" tabindex="-1" data-testid=""stHeader="">
        <div class="header" style="background-color:#FFFFFF;">
        <a href="https://lcc.org.uk/">
        <img src="https://lcc.org.uk/wp-content/themes/lcc/src/img/svgs/logo-white.svg" alt="London Cycling Campaign logo" class="logo" style="max-width:20%;">
        </a>
        <h1 class="title">Dangerous <br/> Junctions App</h1>
        </div>
        </header>
    """,
    unsafe_allow_html=True
)

st.markdown(
    '''
        <style>
        .header img {
        position: fixed;
        top: 0px;
        left: 0px;
        height: 6.5rem;
        z-index: 99999;
        background-color: #e30613;
        border: 1.5vw solid #e30613;
        }
        .header h1 {
        position: relative;
        text-align: center;
        vertical-align: middle;
        height: 6.5rem;
        font-size: 2em;
        }
        </style> 
    ''',
    unsafe_allow_html=True
)


# this is basically so you can scroll past the maps on mobile
st.write(
    '''
    <style>div.block-container{padding-left:1rem;}</style>
    <style>div.block-container{padding-right:1rem;}</style>
    ''',
    unsafe_allow_html=True
)


junctions, collisions, notes = read_in_data(tolerance=15)

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
                min_value=0,
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
            submit = st.form_submit_button(label='Recalculate Junctions')

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
    if 'chosen_point' not in st.session_state:
        st.session_state['chosen_point'] = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].values[0]
    elif casualty_type != st.session_state['previous_casualty_type']:
        st.session_state['chosen_point'] = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].values[0]
    elif boroughs != st.session_state['previous_boroughs']:
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

            Map shows the {n_junctions} most dangerous junctions in {borough_msg}.
        ''')

        high_map = high_level_map(dangerous_junctions, junction_collisions, n_junctions)
        map_click = st_folium(
            high_map,
            returned_objects=['last_object_clicked'],
            use_container_width=True,
            height=500
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
        low_map = low_level_map(
            dangerous_junctions,
            junction_collisions,
            st.session_state['chosen_point'],
            n_junctions,
            casualty_type
        )
        st_folium(
            low_map,
            center=st.session_state['chosen_point'],
            zoom=18,
            returned_objects=[],
            use_container_width=True,
            height=500
        )


st.markdown(f'''
    #### Danger Metrics
            
    Junctions ranked from most to least dangerous
''')
fig = px.bar(
    dangerous_junctions, 
    x="junction_rank",
    y="recency_danger_metric",
    hover_name="junction_cluster_name",
    hover_data=[
        f'fatal_{casualty_type}_casualties',
        f'serious_{casualty_type}_casualties',
        f'slight_{casualty_type}_casualties',
        'latitude_cluster',
        'longitude_cluster'
    ],
    text="recency_danger_metric",
    text_auto='.1f',
    height=340
)
fig.update_xaxes(title='Junction danger rank')
fig.update_yaxes(title='Recency danger metric')
fig.update_layout(
    hovermode="x",
    margin=dict(l=20, r=20, t=20, b=20)
)
fig.update_traces(
    marker_color='#e30613',
)
st.plotly_chart(fig, use_container_width=True, theme="streamlit")


with st.expander("About this app"):
    st.write("""
        Welcome to the London Cycling Campaign's Dangerous Junctions tool. The tool displays the most dangerous
        junctions in London for either cyclists or pedestrians, depending on the settings you've selected. You can
        also filter to specific boroughs or change the number of junctions displayed using the options in the panel at
        the top of the page.
             
        It's designed to assist LCC and other organisations to campaign and advocate for improvements to road networks
        in London, helping to make junctions safe for both cyclists and pedestrians.

        The 'dangerous junctions' map to the top left plots the top junctions, ranked in descending order from most to least dangerous.
        By clicking on a junction you can find more information about that junction, the number of casualties by severity
        type and it's overall danger metric.
             
        The ranking can also be viewed via the bar chart below the maps. The bars are interactive and many of the same stats about
        the junctions can be access from this view.

        Selecting a junction on the 'dangerous junctions' map updates the 'investigate junction' map to
        display the same junction, showing you the individual collisions that have been assigned
        to that junction for further interogation. Selecting individual collisions
        displays more info about the collision and a link to access the full collision report on the CycleStreets website.

        #### How it works
             
        The difficulty in assessing the danger of junctions is that the data doesn't record the junction a
        given collision occured at, just the coordinates. Therefore we have to map each collision to its nearest
        junction based on these coordinates, which can mean a collision is ocassionally assigned to the wrong junction.
             
        The second challenge is determining how granular the junction information should be. For example, at Trafalgar Square
        we'd ideally want to assess the danger of the junction as a whole, rather than each individual pedestrian crossing and intersection
        that makes up the junction. To solve this, we have used a consolidation algorithm within the OSMNx packages that groups
        any junctions within 15m of each other. This doesn't always each the ideal aggregation, but was the best compromise
        based on our testing.
             
        Once each collision has been mapped to a junction it's fairly straightforward to aggregate the data to rank the junctions. Each collision
        is given a 'danger metric score' based on the severity of the worst casualty involved in the collision and how recent the collision was.
             
        The weighting for each collision is as follows
        - Fatal - `6.8`
        - Serious - `1`
        - Slight - `0.06`
             
        The recency weighting is designed to downweight less recent collisions as the road layout may have changed since the collision.
        The 'recency' weight for a collision occuring 5 years ago would be X, rising to 1 for something in the latest year of data.
            
        The total danger metric score across all collisions at a junction is then the danger metric for that junction.
             
        It's important to note that due to the way the collisions are assigned and aggregated the exact ranking of
        junctions may not be perfect. The ability to drill down into a junction and view the individual collision and their
        location should allow users to assess.
             
        #### The data
             
        The collision data is sourced from the TfL collision extracts, which can be [access here]() and includes all
        collisions involving a cyclist or pedestrian from 2018 to 2022. The junction data is generated using the
        OSMNx package that relies on OpenStreetMap data.
             
        #### Contact

        For any questions, feedback or bug reports, email: <LCC_EMAIL>
    """)
