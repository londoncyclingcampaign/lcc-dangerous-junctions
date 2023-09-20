import streamlit as st

from src.app_functions import *
from streamlit_folium import st_folium


st.set_page_config(layout='wide')

# hack to remove padding at page top
st.write('<style>div.block-container{padding-top:2rem;}</style>', unsafe_allow_html=True)

col1, col2 = st.columns([10, 2])
with col1:
    st.markdown('# Dangerous Junctions App')
with col2:
    st.image('./img/LCC_logo_horizontal_red.png', width=200)


st.sidebar.markdown('### Map Options')

form = st.sidebar.form(key='my_form')

junctions, collisions, annotations, notes = read_in_data(tolerance=15)

casualty_type = form.radio(
    label='Select casualty type',
    options=['cyclist', 'pedestrian'],
    format_func=lambda x: f'{x}s'
)

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
        notes,
        casualty_type,
        boroughs
    )
    dangerous_junctions = calculate_dangerous_junctions(
        junction_collisions,
        n_junctions,
        casualty_type
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
        if 'ALL' in boroughs:
            borough_msg = 'all boroughs'
        else:
            borough_msg = ', '.join([b.capitalize() for b in boroughs])
        st.markdown(f'''
            ### Dangerous Junctions

            Map shows the {n_junctions} most dangerous junctions in {borough_msg}.
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
            height=600
        )


with st.expander("### About this app"):
    st.write("""
        This is an explanation for how the app works, notes on the data and how to find out more.
             
        TBC.
    """)
