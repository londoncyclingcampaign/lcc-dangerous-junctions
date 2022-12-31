import os
import folium
import streamlit as st
import numpy as np
import pandas as pd

from scipy.stats import linregress
from folium.plugins import BeautifyIcon, HeatMap
from streamlit_folium import st_folium, folium_static


@st.experimental_memo
def read_in_data(tolerance):
    if os.getenv('HOME') == '/Users/Dan':
        junctions = pd.read_csv(f'data/junctions-tolerance={tolerance}.csv')
        collisions = pd.read_csv(f'data/collisions-tolerance={tolerance}.csv')
    else:
        junctions = pd.read_csv(st.secrets[f"junctions_{tolerance}"])
        collisions = pd.read_csv(st.secrets[f"collisions_{tolerance}"])
    map_annotations = pd.read_csv(st.secrets["map_annotations"])

    return junctions, collisions, map_annotations


def combine_junctions_and_collisions(junctions, collisions, min_year, max_year, boroughs):
    junction_collisions = (
        junctions
        .merge(
            collisions[
                (collisions['year'] >= min_year) &
                (collisions['year'] <= max_year) &
                (collisions['borough'].isin(boroughs))
            ],
            how='left',
            on=['junction_id', 'junction_index']
        )
    )

    return junction_collisions


def get_all_year_df(junction_collisions):
    all_years = junction_collisions[['year']].dropna().drop_duplicates()
    all_clusters = junction_collisions[['junction_cluster_id']].dropna().drop_duplicates()
    all_years['key'] = 0
    all_clusters['key'] = 0

    all_years = all_years.merge(all_clusters, how='outer', on='key').drop(columns='key')
    return all_years


def calculate_metric_trajectories(junction_collisions, dangerous_junctions):

    dangerous_junction_cluster_ids = dangerous_junctions['junction_cluster_id'].unique()

    filtered_junction_collisions = junction_collisions[
        junction_collisions['junction_cluster_id'].isin(dangerous_junction_cluster_ids)
    ]

    all_years_mapping = get_all_year_df(filtered_junction_collisions)

    yearly_stats = (
        filtered_junction_collisions
        .groupby(['junction_cluster_id', 'year'])['danger_metric']
        .sum()
        .reset_index()
    )

    yearly_stats = (
        all_years_mapping
        .merge(
            yearly_stats,
            how='left',
            on=['year', 'junction_cluster_id']
        )
        .fillna(0)
        .sort_values(by=['junction_cluster_id', 'year'])
    )

    yearly_stats['rolling_danger_metric'] = (
        yearly_stats
        .groupby(['junction_cluster_id'])['danger_metric']
        .transform(lambda s: s.rolling(3, min_periods=3).mean())
    )

    trajectories = (
        yearly_stats
        .groupby(['junction_cluster_id'])
        .apply(lambda x: linregress(x['year'], x['danger_metric'])[0])
        .reset_index(name='danger_metric_trajectory')
    )

    dangerous_junctions = dangerous_junctions.merge(
        trajectories,
        how='left',
        on='junction_cluster_id'
    )
    return dangerous_junctions


def create_junction_labels(row):
    cluster_id = int(row['junction_cluster_id'])
    rank = int(row['junction_rank'])
    recency_metric = np.round(row['recency_danger_metric'], 2)
    trajectory = np.round(row['danger_metric_trajectory'], 2)
    n_fatal = int(row['fatal_cyclist_casualties'])
    n_serious = int(row['serious_cyclist_casualties'])

    if trajectory > 0:
        trajectory_colour = 'red'
    elif trajectory < 0:
        trajectory_colour = 'green'
    else:
        trajectory_colour = 'black'

    label = f"""
        <h3>Cluster: {cluster_id}</h3>
        Dangerous Junction Rank: <b>{rank}</b> <br>
        Recency Danger Metric: <b>{recency_metric}</b> <br>
        Danger Metric Trajectory: <b style="color:{trajectory_colour};">{trajectory}</b> <br>
        <hr>
        Fatal casualties: <b>{n_fatal}</b> <br>
        Serious casualties: <b>{n_serious}</b>
    """
    return label


def calculate_dangerous_junctions(junction_collisions, n_junctions):
    agg_cols = [
        'recency_danger_metric',
        'fatal_cyclist_casualties',
        'serious_cyclist_casualties',
    ]
    dangerous_junctions = (
        junction_collisions
        .groupby(['junction_cluster_id', 'latitude_cluster', 'longitude_cluster'])[agg_cols]
        .sum()
        .reset_index()
        .sort_values(by=['recency_danger_metric', 'fatal_cyclist_casualties'], ascending=[False, False])
        .head(n_junctions)
        .reset_index()
    )

    dangerous_junctions['junction_rank'] = dangerous_junctions.index + 1

    dangerous_junctions = calculate_metric_trajectories(junction_collisions, dangerous_junctions)

    dangerous_junctions['label'] = dangerous_junctions.apply(create_junction_labels, axis=1)

    return dangerous_junctions


def high_level_map(dangerous_junctions, map_data, annotations):

#     m = folium.Map(
#         tiles='https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}{r}.png',
#         attr='&copy; <a href="https://stadiamaps.com/">Stadia Maps</a>, &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors'
#     )
    m = folium.Map()

    map_data = map_data[
        map_data['junction_cluster_id'].isin(dangerous_junctions['junction_cluster_id'])
    ]

    # add annotation layer
    cols = ['latitude', 'longitude', 'map_label', 'label_icon', 'colour']
    for lat, lon, label, icon, colour in annotations[cols].values:
        iframe = folium.IFrame(
            html='''
                <style>
                body {
                  font-family: Tahoma, sans-serif;
                  font-size: 12px;
                }
                </style>
            ''' + label,
            width=200,
            height=50
        )
        marker = folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(iframe)
        ).add_to(m)
        BeautifyIcon(
            icon=icon,
            icon_size=[15, 15],
            # icon_anchor=[0, 10],
            icon_shape='circle',
            background_color='transparent',
            border_color='transparent'
        ).add_to(marker)

    # add junction markers
    cols = ['junction_cluster_id', 'latitude_cluster', 'longitude_cluster', 'label']
    # map_points = map_data[cols].drop_duplicates().values

    for cluster_id, lat, lon, label in dangerous_junctions[cols].values:
        iframe = folium.IFrame(
            html='''
                <style>
                body {
                  font-family: Tahoma, sans-serif;
                  font-size: 12px;
                }
                </style>
            ''' + label,
            width=200,
            height=160
        )
        marker = folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(iframe)
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

    # adjust map bounds

    sw = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].min().values.tolist()
    ne = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].max().values.tolist()
    m.fit_bounds([sw, ne])

    return m


def low_level_map(map_data, chosen_point):

#     m = folium.Map(
#         tiles='https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}{r}.png',
#         attr='&copy; <a href="https://stadiamaps.com/">Stadia Maps</a>, &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors'
#     )
    m = folium.Map()

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

        collision_coords = id_collisions[['latitude', 'longitude', 'max_cyclist_severity']].dropna().values

        for collision_lat, collision_lon, severity in collision_coords:
            if severity == 'fatal':
                folium.CircleMarker(
                    location=[collision_lat, collision_lon],
                    fill=True,
                    color='#D35400',
                    fill_color='#D35400',
                    radius=8
                ).add_to(m)
            elif severity == 'serious':
                folium.CircleMarker(
                    location=[collision_lat, collision_lon],
                    fill=True,
                    color='#F39C12',
                    fill_color='#F39C12',
                    radius=8
                ).add_to(m)

            # draw lines between central point and collisions
            lines = folium.PolyLine(locations=[[[collision_lat, collision_lon], [lat, lon]]], weight=1.5, color='grey')
            m.add_child(lines)

    sw = map_data[['latitude', 'longitude']].min().values.tolist()
    ne = map_data[['latitude', 'longitude']].max().values.tolist()
    m.fit_bounds([sw, ne])

    return m


# =========================================================================== #

st.set_page_config(layout="wide")
st.markdown('# LCC - Dangerous Junctions')

tolerance = st.radio(
    label='Set tolerance for combining junctions in metres (to be removed)',
    options=[25, 28, 30]
)

junctions, collisions, annotations = read_in_data(tolerance)

col1, col2, col3, col4, col5 = st.columns([4, 1, 4, 1, 4])

with col1:
    n_junctions = st.slider(
        label='Number of dangerous junctions to show',
        min_value=0,
        max_value=100,  # not sure we'd ever need to view more then 100?
        value=20
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
        collisions['borough'].dropna().unique()
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

    low_map = low_level_map(low_junction_collisions, chosen_point)
    st_folium(low_map, width=600, height=600)


st.markdown('''
    ### Collisions data

    Individual collision data for chosen junction above.
''')
output_cols = [
    'junction_id',
    'junction_cluster_id',
    'id',
    'date',
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


# OPTIONAL HEATMAP
# st.markdown('''
#     ---

#     ### Heatmap
# ''')

# heatmap_points = collisions[['latitude', 'longitude', 'danger_metric']].dropna().values.tolist()

# heatmap = folium.Map(
#     [collisions['latitude'].mean(), collisions['longitude'].mean()],
#     zoom_start=11,
#     tiles='https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}{r}.png',
#     attr='&copy; <a href="https://stadiamaps.com/">Stadia Maps</a>, &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors'
# )

# HeatMap(heatmap_points, max_opacity=1, radius=20, blur=10).add_to(heatmap)

# st_folium(heatmap, width=1200, height=600)
