import streamlit as st

from src.app_functions import *
from streamlit_folium import st_folium


st.set_page_config(layout="wide")
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
    st.warning('Please select at least one borough and recalculate', icon="⚠️")
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

    if 'last_object_clicked' not in st.session_state:
        st.session_state['last_object_clicked'] = None

    if 'zoom' not in st.session_state:
        st.session_state['zoom'] = 8

    st.markdown('''
        ### Most dangerous junctions

        Identified junctions in purple.
    ''')


    map = base_map(dangerous_junctions)

    fg = add_junctions_to_map(dangerous_junctions, n_junctions)

    center = None
    if st.session_state['last_object_clicked']:
        center = (
            st.session_state['last_object_clicked']['lat'],
            st.session_state['last_object_clicked']['lng']
        )

    map_click = st_folium(
        map,
        feature_group_to_add=fg,
        returned_objects=['last_object_clicked', 'zoom'],
        center=center,
        width=1200,
        height=600,
        zoom=st.session_state['zoom']
    )

    if map_click['last_object_clicked']:
        if (map_click['last_object_clicked'] != st.session_state['last_object_clicked']):
            st.session_state['last_object_clicked'] = map_click['last_object_clicked']

            # can't get this to work after initial zoom!
            # if st.session_state['zoom'] == 8:
            #     st.session_state['zoom'] = 15
            # else:
            #     st.session_state['zoom'] += .00000000001

            st.experimental_rerun()


    # with col2:
    #     st.markdown('''
    #         ### Investigate Junction

    #         Select a point on the left map and drill down into it here.
    #     ''')
        # low_map = low_level_map(
        #     dangerous_junctions, junction_collisions, st.session_state["chosen_point"], n_junctions
        # )
        # st_folium(
        #     low_map,
        #     center=st.session_state["chosen_point"],
        #     zoom=18,
        #     returned_objects=[],
        #     width=600,
        #     height=600
        # )

# st.markdown('''
#     ### Collisions data

#     Individual collision data for chosen junction above.
# ''')

# st.dataframe(get_table(get_low_level_junction_data(junction_collisions, st.session_state['chosen_point'])))

# st.markdown('''
#     ### Dangerous Junctions Data

#     List of the most dangerous junctions, for testing purposes only.
# ''')

# st.dataframe(dangerous_junctions[[
#     'junction_cluster_id', 'junction_cluster_name', 'recency_danger_metric', 'danger_metric_trajectory',
#     'fatal_cyclist_casualties', 'serious_cyclist_casualties', 'slight_cyclist_casualties',
#     'junction_rank'
# ]])