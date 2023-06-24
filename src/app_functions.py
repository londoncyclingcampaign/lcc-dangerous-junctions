import os
import yaml
import folium
import streamlit as st
import numpy as np
import pandas as pd
import seaborn as sns

from yaml import Loader
from scipy.stats import linregress
from folium.features import DivIcon


# read in data params
params = yaml.load(open("params.yaml", 'r'), Loader=Loader)


@st.cache_data(show_spinner=False)
def read_in_data(tolerance: int) -> tuple:
    """
    Function to read in different data depending on tolerance requests.
    Reads from local if not on streamlit server, otherwise from google sheets.
    """
    if os.getenv('HOME') == '/Users/Dan':
        junctions = pd.read_csv(
            f'data/junctions-tolerance={tolerance}.csv',
            low_memory=False
        )
        collisions = pd.read_csv(
            f'data/collisions-tolerance={tolerance}.csv',
            low_memory=False,
            dtype={'collision_index': int}
        )
    else:
        junctions = pd.read_csv(
            st.secrets[f"junctions_{tolerance}"],
            low_memory=False
        )
        collisions = pd.read_csv(
            st.secrets[f"collisions_{tolerance}"],    
            low_memory=False,
            dtype={'collision_index': int}
        )

    map_annotations = pd.read_csv(st.secrets["map_annotations"])

    return junctions, collisions, map_annotations


@st.cache_data(show_spinner=False)
def combine_junctions_and_collisions(
    junctions: pd.DataFrame,
    collisions: pd.DataFrame,
    boroughs: str,
    ) -> pd.DataFrame:
    """
    Combines the junction and collision datasets, as well as filters by years chosen in app.
    """

    junction_collisions = (
        junctions
        .merge(
            collisions,
            how='inner',  # inner as we don't care about junctions with no collisions
            on=['junction_id', 'junction_index']
        )
    )

    if 'ALL' not in boroughs:
        junction_collisions = junction_collisions[junction_collisions['borough'].isin(boroughs)]

    junction_collisions['danger_metric'] = junction_collisions.apply(
        lambda row: get_danger_metric(row), axis=1
    )
    junction_collisions['recency_danger_metric'] = (
        junction_collisions['danger_metric'] * junction_collisions['recency_weight']
    )
    junction_collisions['collision_label'] = junction_collisions.apply(
        create_collision_labels, axis=1
    )
    return junction_collisions


def get_danger_metric(row, params=params):
    '''
    Upweights more severe collisions for junction comparison.
    '''
    fatal = row['fatal_cyclist_casualties']
    serious = row['serious_cyclist_casualties']
    slight = row['slight_cyclist_casualties']
    
    danger_meric = params['weight_fatal'] * fatal + params['weight_serious'] * serious + params['weight_slight'] * slight
          
    return danger_meric


def get_all_year_df(junction_collisions: pd.DataFrame) -> pd.DataFrame:
    """
    Function to get a dataframe containing all years and cluster combinations possible
    """
    all_years = junction_collisions[['year']].dropna().drop_duplicates()
    all_clusters = junction_collisions[['junction_cluster_id']].dropna().drop_duplicates()
    all_years['key'] = 0
    all_clusters['key'] = 0

    all_years = all_years.merge(all_clusters, how='outer', on='key').drop(columns='key')
    return all_years


def calculate_metric_trajectories(junction_collisions: pd.DataFrame, dangerous_junctions: pd.DataFrame) -> pd.DataFrame:
    """
    Function to aggregate by junction and calculate danger metric, plus work out the trajectory of the metric.
    TODO - split this function out.
    """
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


def create_collision_labels(row: pd.DataFrame) -> str:
    """
    Takes a row of data from a dataframe and extracts info for collision map labels
    """
    collision_index = row['collision_index']
    date = row['date']
    severity = row['max_cyclist_severity']
    link = f'https://www.cyclestreets.net/collisions/reports/{collision_index}/'

    label = f"""
        <h3>{collision_index}</h3>
        Date: <b>{date}</b> <br>
        Max cyclist severity: <b>{severity}</b> <br>
        <a href="{link}" target="_blank">Stats19 report</a>
    """
    return label


def create_junction_labels(row: pd.DataFrame) -> str:
    """
    Takes a row of data from a dataframe and extracts info for junction map labels
    """
    cluster_id = int(row['junction_cluster_id'])
    junction_name = row['junction_cluster_name']
    rank = int(row['junction_rank'])
    recency_metric = np.round(row['recency_danger_metric'], 2)
    trajectory = np.round(row['danger_metric_trajectory'], 2)
    n_fatal = int(row['fatal_cyclist_casualties'])
    n_serious = int(row['serious_cyclist_casualties'])
    n_slight = int(row['slight_cyclist_casualties'])

    if trajectory > 0:
        trajectory_colour = 'red'
    elif trajectory < 0:
        trajectory_colour = 'green'
    else:
        trajectory_colour = 'black'

    label = f"""
        <h3>{junction_name}<h3>
        <h3>Cluster: {cluster_id}</h3>
        Dangerous Junction Rank: <b>{rank}</b> <br>
        Recency Danger Metric: <b>{recency_metric}</b> <br>
        Danger Metric Trajectory: <b style="color:{trajectory_colour};">{trajectory}</b> <br>
        <hr>
        Fatal casualties: <b>{n_fatal}</b> <br>
        Serious casualties: <b>{n_serious}</b> <br>
        Slight casualties: <b>{n_slight}</b>
    """
    return label


@st.cache_data(show_spinner=False)
def calculate_dangerous_junctions(junction_collisions: pd.DataFrame, n_junctions: int) -> pd.DataFrame:
    """
    Calculate most dangerous junctions in data and return n worst.
    """
    agg_cols = [
        'recency_danger_metric',
        'fatal_cyclist_casualties',
        'serious_cyclist_casualties',
        'slight_cyclist_casualties'
    ]
    dangerous_junctions = (
        junction_collisions
        .groupby(['junction_cluster_id', 'junction_cluster_name', 'latitude_cluster', 'longitude_cluster'])[agg_cols]
        .sum()
        .reset_index()
        .sort_values(by=['recency_danger_metric', 'fatal_cyclist_casualties'], ascending=[False, False])
        .head(n_junctions)
        .reset_index()
    )

    dangerous_junctions['junction_rank'] = dangerous_junctions.index + 1

    dangerous_junctions = calculate_metric_trajectories(junction_collisions, dangerous_junctions)

    dangerous_junctions['label'] = dangerous_junctions.apply(
        lambda row: create_junction_labels(row),
        axis=1
    )

    return dangerous_junctions


def get_html_colors(n: int) -> list:
    """
    Function to get n html colour codes along a continuous gradient
    """
    p = sns.color_palette("flare_r", n)
    p.as_hex()
    
    p = [[int(i * 255) for i in c] for c in p[:]]
    html_p = ["#{0:02x}{1:02x}{2:02x}".format(c[0], c[1], c[2]) for c in p[:]]
    
    return html_p


@st.cache_data(show_spinner=False)
def get_low_level_junction_data(junction_collisions: pd.DataFrame, chosen_point: list) -> pd.DataFrame:
    """
    Given a chosen junction get the low level collision data for that junction
    """
    low_junction_collisions = junction_collisions[
        (junction_collisions['latitude_cluster'] == chosen_point[0]) &
        (junction_collisions['longitude_cluster'] == chosen_point[1])
    ]
    return low_junction_collisions


def high_level_map(dangerous_junctions: pd.DataFrame, map_data: pd.DataFrame, annotations: pd.DataFrame, n_junctions: int) -> folium.Map:
    """
    Function to generate the junction map

    TODO - split this out into separate functions.
    """
    m = folium.Map(tiles='cartodbpositron')

    borough_geo = "london_boroughs.geojson"
    folium.Choropleth(
        geo_data=borough_geo,
        line_color='#5DADE2', 
        fill_opacity=0, 
        line_opacity=.5,
        overlay=False,
    ).add_to(m)

    map_data = map_data[
        map_data['junction_cluster_id'].isin(dangerous_junctions['junction_cluster_id'])
    ]

    pal = get_html_colors(n_junctions)

    # add annotation layer
    cols = ['latitude', 'longitude', 'map_label', 'colour']
    for lat, lon, label, colour in annotations[cols].values:
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
            height=80
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=4,    
            color=colour,
            fill_color=colour,
            fill_opacity=1,
        ).add_to(m)
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(iframe),
            icon=DivIcon(
                icon_size=(30,30),
                icon_anchor=(3,7),
                html='<div style="font-size: 7pt; font-family: monospace; color: white">I</div>',
            ),
        ).add_to(m)

    # add junction markers
    cols = ['latitude_cluster', 'longitude_cluster', 'label', 'junction_rank']

    for lat, lon, label, rank in dangerous_junctions[cols].values[::-1]:
        iframe = folium.IFrame(
            html='''
                <style>
                body {
                  font-family: Tahoma, sans-serif;
                  font-size: 12px;
                }
                </style>
            ''' + label,
            width=250,
            height=250
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=10,
            color=pal[rank - 1],
            fill_color=pal[rank - 1],
            fill_opacity=1,
            z_index_offset=1000 + (100 - rank)
        ).add_to(m)

        if rank < 10:
            i = 3
        else:
            i = 8
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(iframe),
            icon=DivIcon(
                icon_size=(30,30),
                icon_anchor=(i,11),
                html=f'<div style="font-size: 10pt; font-family: monospace; color: white">%s</div>' % str(rank),
            ),
            z_index_offset=1000 + (100 - rank)
        ).add_to(m)

    # adjust map bounds
    sw = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].min().values.tolist()
    ne = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].max().values.tolist()
    m.fit_bounds([sw, ne])

    return m


def low_level_map(
    dangerous_junctions: pd.DataFrame, junction_collisions: pd.DataFrame,
    initial_location: list, n_junctions: int) -> folium.Map:
    """
    Function to generate the lower level collision map

    TODO - split this out into separate functions.
    """
    m = folium.Map(
        tiles='cartodbpositron',
        location=initial_location,
        zoom_start=18,
        max_zoom=20
    )

    borough_geo = "london_boroughs.geojson"
    folium.Choropleth(
        geo_data=borough_geo,
        line_color='#5DADE2', 
        fill_opacity=0, 
        line_opacity=.5,
        overlay=False,
    ).add_to(m)

    pal = get_html_colors(n_junctions)

    cols = ['junction_cluster_id', 'latitude_cluster', 'longitude_cluster', 'junction_rank']
    for id, lat, lon, junction_rank in dangerous_junctions[cols].values:

        # filter lower level data to cluster
        id_collisions = junction_collisions[junction_collisions['junction_cluster_id'] == id]

        cols = ['latitude', 'longitude', 'max_cyclist_severity', 'collision_label']
        for collision_lat, collision_lon, severity, label in id_collisions[cols].dropna().values:
            # draw lines between central point and collisions
            lines = folium.PolyLine(locations=[[[collision_lat, collision_lon], [lat, lon]]], weight=.8, color='grey')
            m.add_child(lines)

            iframe = folium.IFrame(
                html='''
                    <style>
                    body {
                    font-family: Tahoma, sans-serif;
                    font-size: 12px;
                    }
                    </style>
                ''' + label,
                width=180,
                height=100
            )

            if severity == 'fatal':
                folium.CircleMarker(
                    location=[collision_lat, collision_lon],
                    popup=folium.Popup(iframe),
                    fill=True,
                    color='#D35400',
                    fill_color='#D35400',
                    fill_opacity=1,
                    radius=3
                ).add_to(m)
            elif severity == 'serious':
                folium.CircleMarker(
                    location=[collision_lat, collision_lon],
                    popup=folium.Popup(iframe),
                    fill=True,
                    color='#F39C12',
                    fill_color='#F39C12',
                    fill_opacity=1,
                    radius=3
                ).add_to(m)
            elif severity == 'slight':
                folium.CircleMarker(
                    location=[collision_lat, collision_lon],
                    popup=folium.Popup(iframe),
                    fill=True,
                    color='#F7E855',
                    fill_color='#F7E855',
                    fill_opacity=1,
                    radius=3
                ).add_to(m)

        rank = int(junction_rank)
        folium.CircleMarker(
            location=[lat, lon],
            radius=10,    
            fill_opacity=1
        ).add_to(m)

        folium.CircleMarker(
            location=[lat, lon],
            radius=10,    
            color=pal[rank - 1],
            fill_color=pal[rank - 1],
            fill_opacity=1
        ).add_to(m)

        if rank < 10:
            i = 3
        else:
            i = 8
        folium.map.Marker(
            location=[lat, lon],
            icon=DivIcon(
                icon_size=(30,30),
                icon_anchor=(i,11),
                html=f'<div style="font-size: 10pt; font-family: monospace; color: white">%s</div>' % str(rank)
            )
        ).add_to(m)

    return m


@st.cache_data
def get_table(low_junction_collisions: pd.DataFrame) -> pd.DataFrame:
    """
    Filter cols and order for output in app
    """
    output_cols = [
        'collision_index',
        'date',
        'location',
        'junction_detail',
        'max_cyclist_severity',
        'fatal_cyclist_casualties',
        'serious_cyclist_casualties',
        'slight_cyclist_casualties',
        'danger_metric',
        'recency_danger_metric'
    ]
    table_data = (
        low_junction_collisions[output_cols]
        .dropna(subset=['collision_index'])
        .sort_values(by='date', ascending=False)
    )
    return table_data