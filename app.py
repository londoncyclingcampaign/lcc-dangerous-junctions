import folium
import geopandas
import streamlit as st
import numpy as np
import pandas as pd
import pydeck as pdk

from folium.plugins import BeautifyIcon
from streamlit_folium import st_folium, folium_static


# TODO: Prevent maps re-rendering when the other is changed


@st.cache
def read_in_data(tolerance):
    junctions = pd.read_csv(f'data/junctions-tolerance={tolerance}.csv')
    collisions = pd.read_csv(f'data/collisions-tolerance={tolerance}.csv')
    map_annotations = pd.read_csv('data/map-annotations.csv')

    return junctions, collisions, map_annotations


def combine_junctions_and_collisions(junctions, collisions, min_year, max_year, boroughs):
    junction_collisions = (
        junctions
        .merge(
            collisions[
                (collisions['accident_year'] >= min_year) &
                (collisions['accident_year'] <= max_year) &
                (collisions['local_authority_district'].isin(boroughs))
            ],
            how='left',
            on=['junction_id', 'junction_index']
        )
    )

    return junction_collisions


def calculate_dangerous_junctions(junction_collisions, n_junctions):
    agg_cols = [
        'recency_danger_metric',
        'fatal_cyclist_casualties',
        'serious_cyclist_casualties'
    ]

    dangerous_junctions = (
        junction_collisions
        .groupby(['junction_cluster_id', 'latitude_cluster', 'longitude_cluster'])[agg_cols]
        .sum()
        .reset_index()
        .sort_values(by='recency_danger_metric', ascending=False)
        .head(n_junctions)
    )

    dangerous_junctions['label'] = dangerous_junctions.apply(
        lambda row: f"""
        Recency Danger Metric: {np.round(row['recency_danger_metric'], 2)} <br>
        Serious casualties: {row['serious_cyclist_casualties']} <br>
        Fatal casualties: {row['fatal_cyclist_casualties']}
        """,
        axis=1
    )
    return dangerous_junctions


def high_level_map(dangerous_junctions, map_data, annotations):

    m = folium.Map(
        tiles='https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}{r}.png',
        attr='&copy; <a href="https://stadiamaps.com/">Stadia Maps</a>, &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors'
    )

    map_data = map_data[
        map_data['junction_cluster_id'].isin(dangerous_junctions['junction_cluster_id'])
    ]

    cols = ['junction_cluster_id', 'latitude_cluster', 'longitude_cluster']

    map_points = map_data[cols].drop_duplicates().values
    for cluster_id, lat, lon in map_points:
        marker = folium.Marker(
            location=[lat, lon]
        ).add_to(m)

        BeautifyIcon(
            icon='exclamation',
            icon_size=[20, 20],
            icon_anchor=[10, 10],
            icon_shape='circle',
            background_color='#9B59B6',
            border_color='#9B59B6',
            font_color='white'
        ).add_to(marker)

    # add annotation layer

    cols = ['latitude', 'longitude', 'map_label', 'label_icon', 'colour']
    for lat, lon, label, icon, colour in annotations[cols].values:
        iframe = folium.IFrame(label)
        popup = folium.Popup(iframe, min_width=240, max_width=240)
        marker = folium.Marker(
            location=[lat, lon],
            popup=popup
        ).add_to(m)
        BeautifyIcon(
            icon=icon,
            icon_size=[20, 20],
            icon_anchor=[10, 10],
            icon_shape='circle',
            background_color=colour,
            border_color=colour,
            font_color='white'
        ).add_to(marker)

    # adjust map bounds

    sw = map_data[['latitude_cluster', 'longitude_cluster']].min().values.tolist()
    ne = map_data[['latitude_cluster', 'longitude_cluster']].max().values.tolist()
    m.fit_bounds([sw, ne])

    return m


def low_level_map(map_data, chosen_point):

    m = folium.Map(
        tiles='https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}{r}.png',
        attr='&copy; <a href="https://stadiamaps.com/">Stadia Maps</a>, &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors'
    )

    cols = ['junction_cluster_id', 'latitude_cluster', 'longitude_cluster']
    map_points = map_data[cols].drop_duplicates().values
    for cluster_id, lat, lon in map_points:
        marker = folium.Marker(
            location=[lat, lon],
        ).add_to(m)
        BeautifyIcon(
            icon='exclamation',
            icon_size=[20, 20],
            icon_anchor=[10, 10],
            icon_shape='circle',
            background_color='#9B59B6',
            border_color='#9B59B6',
            font_color='white'
        ).add_to(marker)

        # filter lower level data to cluster
        id_collisions = map_data[map_data['junction_cluster_id'] == cluster_id]

        collision_coords = id_collisions[['latitude', 'longitude']].dropna().values

        # draw lines between central point and collisions
        lines = folium.PolyLine(locations=[[coord, [lat, lon]] for coord in collision_coords], weight=3, color='grey')
        m.add_child(lines)

        for collision_lat, collision_lon in collision_coords:
            folium.CircleMarker(
                location=[collision_lat, collision_lon],
                fill=True,
                color='#E74C3C',
                fill_color='#E74C3C',
                radius=5
            ).add_to(m)

    sw = map_data[['latitude', 'longitude']].min().values.tolist()
    ne = map_data[['latitude', 'longitude']].max().values.tolist()
    m.fit_bounds([sw, ne])

    return m


# =========================================================================== #

st.set_page_config(layout="wide")
st.markdown('# LCC - Dangerous Junctions')

tolerance = st.radio(
    label='Set tolerance (feature to be removed)',
    options=[28, 30, 32, 35, 40]
)

junctions, collisions, annotations = read_in_data(tolerance)

col1, col2, col3, col4, col5 = st.columns([4, 1, 4, 1, 4])

with col1:
    n_junctions = st.slider(
        label='Number of dangerous junctions to show',
        min_value=0,
        max_value=100,  # not sure we'd ever need to view more then 100?
        value=20,
    )

with col3:
    min_year, max_year = st.slider(
        label='Select date period',
        min_value=2011,
        max_value=2021,
        value=(2011, 2021)
    )

available_boroughs = sorted(
    list(
        collisions['local_authority_district'].dropna().unique()
    )
)

with col5:
    boroughs = st.multiselect(
        label='Filter by borough',
        options=['All'] + available_boroughs,
        default=['All']
    )
    if "All" in boroughs:
        boroughs = available_boroughs


junction_collisions = combine_junctions_and_collisions(junctions, collisions, min_year, max_year, boroughs)
dangerous_junctions = calculate_dangerous_junctions(junction_collisions, n_junctions)

filtered_annotations = annotations[
    annotations['borough'].isin(boroughs)
]


# set default to worst junction...
chosen_point = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].values[0]

col1, col2 = st.columns([6, 6])
with col1:
    st.markdown('''
        ### Most dangerous junctions

        Identified junctions in purple.
    ''')
    high_map = high_level_map(dangerous_junctions, junction_collisions, filtered_annotations)
    map_click = st_folium(high_map, returned_objects=["last_object_clicked"], width=800, height=600)

    if map_click['last_object_clicked']:
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

    low_map = low_level_map(low_junction_collisions, chosen_point)
    st_folium(low_map, width=800, height=600)


st.markdown('''
    ### Collisions data

    Individual collision data for chosen junction above.
''')
output_cols = [
    'junction_id',
    'id',
    'date',
    'police_force',
    'max_cyclist_severity',
    'fatal_cyclist_casualties',
    'serious_cyclist_casualties',
    'slight_cyclist_casualties',
    'danger_metric',
    'recency_danger_metric'
]
st.dataframe(
    low_junction_collisions[output_cols]
    .dropna(subset=['id'])
    .sort_values(by='date', ascending=False)
)

