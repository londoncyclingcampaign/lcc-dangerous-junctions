import streamlit as st

from src.app_functions import *
from streamlit_folium import st_folium


st.set_page_config(layout="wide")
st.markdown('# LCC - Dangerous Junctions')

st.sidebar.markdown('## Map Options')

form = st.sidebar.form(key='my_form')

tolerance = form.radio(
    label='Set tolerance for combining junctions in metres (to be removed)',
    options=[18, 20, 22],
    index=1
)
junctions, collisions, annotations = read_in_data(tolerance)

n_junctions = form.slider(
    label='Number of dangerous junctions to show',
    min_value=0,
    max_value=100,  # not sure we'd ever need to view more then 100?
    value=20
)

min_year, max_year = form.slider(
    label='Select date period',
    min_value=2011,
    max_value=2021,
    value=(2011, 2021)
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
    st.warning('Please select at least one borough and recalculate', icon="⚠️")
else:
    junction_collisions = combine_junctions_and_collisions(junctions, collisions, min_year, max_year, boroughs)
    dangerous_junctions = calculate_dangerous_junctions(junction_collisions, n_junctions)

    if 'ALL' not in boroughs:
        filtered_annotations = annotations[
            annotations['borough'].isin(boroughs)
        ]
    else:
        filtered_annotations = annotations

    # set default to worst junction...
    chosen_point = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].values[0]

    col1, col2 = st.columns([6, 6])
    with col1:
        st.markdown('''
            ### Most dangerous junctions

            Identified junctions in purple.
        ''')
        high_map = high_level_map(dangerous_junctions, junction_collisions, filtered_annotations, n_junctions)
        map_click = st_folium(high_map, returned_objects=["last_object_clicked"], width=600, height=600)

        if map_click['last_object_clicked']:
            # hacky way to test what kind of point clicked..
            if len(annotations[
                    (annotations['latitude'] == map_click['last_object_clicked']['lat']) &
                    (annotations['longitude'] == map_click['last_object_clicked']['lng'])
                ]) == 0:
                chosen_point = [
                    map_click['last_object_clicked']['lat'],
                    map_click['last_object_clicked']['lng']
                ]
    with col2:
        st.markdown('''
            ### Investigate Junction

            Select a point on the left map and drill down into it here.
        ''')

        low_junction_collisions = junction_collisions[
            (junction_collisions['latitude_cluster'] == chosen_point[0]) &
            (junction_collisions['longitude_cluster'] == chosen_point[1])
        ]
        junction_rank = dangerous_junctions[
            (dangerous_junctions['latitude_cluster'] == chosen_point[0]) &
            (dangerous_junctions['longitude_cluster'] == chosen_point[1])
        ]['junction_rank'].values.tolist()[0]

        low_map = low_level_map(low_junction_collisions, junction_rank, n_junctions)
        st_folium(low_map, width=600, height=600)

    st.markdown('''
        ### Collisions data

        Individual collision data for chosen junction above.
    ''')
    output_cols = [
        'collision_index',
        'junction_id',
        'junction_cluster_id',
        'date',
        'location',
        'max_cyclist_severity',
        'fatal_cyclist_casualties',
        'serious_cyclist_casualties',
        'danger_metric',
        'recency_danger_metric'
    ]
    st.dataframe(
        low_junction_collisions[output_cols]
        .dropna(subset=['collision_index'])
        .sort_values(by='date', ascending=False)
    )
