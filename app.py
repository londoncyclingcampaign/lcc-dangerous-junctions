import streamlit as st

from src.app_functions import *
from streamlit_folium import st_folium


st.set_page_config(layout='wide')
st.markdown('# LCC - Dangerous Junctions')

st.sidebar.markdown('## Map Options')

form = st.sidebar.form(key='my_form')

junctions, collisions, annotations = read_in_data(tolerance=15)

n_junctions = form.slider(
    label='Number of dangerous junctions to show',
    min_value=0,
    max_value=100,  # not sure we'd ever need to view more then 100?
    value=20
)

available_boroughs = sorted(
    list(
        collisions['borough'].dropna().unique()
    )
)

boroughs = form.multiselect(
    label='Filter by borough',
    options=['ALL'] + available_boroughs,
    default='ALL'
)


submit = form.form_submit_button(label='Recalculate Junctions')

if len(boroughs) == 0:
    st.warning('Please select at least one borough and recalculate', icon='⚠️')
else:
    junction_collisions = combine_junctions_and_collisions(
        junctions,
        collisions,
        boroughs
    )
    dangerous_junctions = calculate_dangerous_junctions(
        junction_collisions,
        n_junctions
    )

    if 'ALL' not in boroughs:
        filtered_annotations = annotations[annotations['borough'].isin(boroughs)]
    else:
        filtered_annotations = annotations

    # set default to worst junction...
    if 'chosen_point' not in st.session_state:
        st.session_state['chosen_point'] = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].values[0]
    elif boroughs != st.session_state['previous_boroughs']:
        st.session_state['chosen_point'] = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].values[0]

    st.session_state['previous_boroughs'] = boroughs

    col1, col2 = st.columns([6, 6])
    with col1:
        st.markdown('''
            ### Most dangerous junctions

            Identified junctions in purple.
        ''')

        high_map = high_level_map(dangerous_junctions, junction_collisions, filtered_annotations, n_junctions)
        map_click = st_folium(
            high_map,
            returned_objects=['last_object_clicked'],
            use_container_width=True,
            height=600
        )

        if map_click['last_object_clicked']:
            if len(annotations[
                    (annotations['latitude'] == map_click['last_object_clicked']['lat']) &
                    (annotations['longitude'] == map_click['last_object_clicked']['lng'])
            ]) == 0:
                st.session_state['chosen_point'] = [
                    map_click['last_object_clicked']['lat'],
                    map_click['last_object_clicked']['lng']
                ]

    with col2:
        st.markdown('''
            ### Investigate Junction

            Select a point on the left map and drill down into it here.
        ''')
        low_map = low_level_map(
            dangerous_junctions, junction_collisions, st.session_state['chosen_point'], n_junctions
        )
        st_folium(
            low_map,
            center=st.session_state['chosen_point'],
            zoom=18,
            returned_objects=[],
            use_container_width=True,
            height=600
        )

st.markdown('''
    ### Collisions data

    Individual collision data for chosen junction above.
''')

st.dataframe(
    data=get_table(get_low_level_junction_data(junction_collisions, st.session_state['chosen_point'])),
    hide_index=True,
    column_order=[
        'collision_index',
        'date',
        'location',
        'junction_detail',
        'max_cyclist_severity',
        'danger_metric',
        'recency_danger_metric'
    ],
    column_config={
        'collision_index': st.column_config.NumberColumn(
            'Collision Index',
            help='Collision index from stats19 data',
            step=1,
            format='%i',
        ),
        'date': st.column_config.DateColumn(
            'Date',
            help='Date of collision',
            format='DD/MM/YYYY',
        ),
        'location': st.column_config.TextColumn(
            'Location',
            help='Location of collision'
        ),
        'junction_detail': st.column_config.TextColumn(
            'Junction Type',
            help='Type of junction collision occured at'
        ),
        'max_cyclist_severity': st.column_config.TextColumn(
            'Max Cyclist Severity',
            help='Maximum injury severity of cyclist in collision'
        ),
        'danger_metric': st.column_config.NumberColumn(
            'Collision Metric',
            help='Danger metric value based on the number of each casualty severity type',
            format='%.2f',
        ),
        'recency_danger_metric': st.column_config.NumberColumn(
            'Recency Collision Metric',
            help='Collision danger metric scaled by how recent the collision was',
            format='%.2f',
        )
    }
)
