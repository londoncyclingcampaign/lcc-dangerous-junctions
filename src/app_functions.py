import os
import yaml
import folium
import streamlit as st
import numpy as np
import pandas as pd
import polars as pl
import seaborn as sns

from yaml import Loader
from folium.features import DivIcon
from fsspec import filesystem


# read in data params
DATA_PARAMETERS = yaml.load(open("params.yaml", 'r'), Loader=Loader)

# set as "prod" in the hosted environment
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")


@st.cache_data(show_spinner=False, ttl=24*3600)
def read_in_data(tolerance: int, params: dict = DATA_PARAMETERS) -> tuple:
    """
    Function to read in different data depending on tolerance requests.
    Reads from local if not on streamlit server, otherwise from google sheets.
    """
    if ENVIRONMENT == 'dev':
        junctions = pl.read_parquet(
            f'data/junctions-tolerance={tolerance}.parquet',
            columns=params['junction_app_columns']
        )
        collisions = pl.read_parquet(
            f'data/collisions-tolerance={tolerance}.parquet',
            columns=params['collision_app_columns']
        )
    else:
        fs = filesystem('gcs', token=st.secrets.connections.gcs.to_dict())
        with fs.open("gs://lcc-app-data/junctions-tolerance=15.parquet", "rb") as f:
            junctions = pl.read_parquet(
                f, columns=params['junction_app_columns']
            )
        with fs.open("gs://lcc-app-data/ollisions-tolerance=15.parquet", "rb") as f:
            collisions = pl.read_parquet(
                f, columns=params['collisions_app_columns']
            )

    try:
        junction_notes = pl.read_csv(st.secrets["junction_notes"])
    except FileNotFoundError:
        junction_notes = pl.DataFrame(columns=["junction_cluster_id", "notes"])

    return junctions, collisions, junction_notes


@st.cache_data(show_spinner=False, ttl=3*60)
def combine_junctions_and_collisions(
    junctions: pd.DataFrame,
    collisions: pd.DataFrame,
    notes: pd.DataFrame,
    casualty_type: str,
    boroughs: str,
    ) -> pd.DataFrame:
    """
    Combines the junction and collision datasets, as well as filters by years chosen in app.
    """
    if casualty_type == 'cyclist':
        collisions = collisions.filter(is_cyclist_collision=True)
    elif casualty_type == 'pedestrian':
        collisions = collisions.filter(is_pedestrian_collision=True)

    junction_collisions = (
        junctions
        .with_columns(pl.col('junction_index').cast(pl.Float64))
        .join(
            collisions,
            how='inner',  # inner as we don't care about junctions with no collisions
            on=['junction_id', 'junction_index']
        )
        .join(
            notes,
            how='left',
            on='junction_cluster_id'
        )
        .with_columns('notes')
        .fill_null('')
    )

    if 'ALL' not in boroughs:
        junction_collisions = junction_collisions.filter(pl.col('borough').is_in(boroughs))

    junction_collisions['danger_metric'] = junction_collisions.apply(
        lambda row: get_danger_metric(row, casualty_type), axis=1
    )
    junction_collisions['recency_danger_metric'] = (
        junction_collisions['danger_metric'] * junction_collisions['recency_weight']
    )

    # add stats19 link column
    junction_collisions['stats19_link'] = junction_collisions['collision_index'].apply(
        lambda x: f'https://www.cyclestreets.net/collisions/reports/{x}/'
    )
    junction_collisions['collision_label'] = junction_collisions.apply(
        lambda row: create_collision_labels(row, casualty_type), axis=1
    )

    return junction_collisions


def get_danger_metric(row, casualty_type, params=DATA_PARAMETERS):
    '''
    Upweights more severe collisions for junction comparison.
    Only take worst severity, so if multiple casualties involved we have to ignore less severe.
    '''
    fatal = row[f'fatal_{casualty_type}_casualties']
    serious = row[f'serious_{casualty_type}_casualties']
    slight = row[f'slight_{casualty_type}_casualties']

    danger_metric = None
    if fatal > 0:
        danger_metric = params['weight_fatal']
    elif serious > 0:
        danger_metric = params['weight_serious']
    elif slight > 0:
        danger_metric = params['weight_slight']
    
    return danger_metric


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
        .groupby('junction_cluster_id')['danger_metric']
        .apply(list)
        .reset_index(name='yearly_danger_metrics')
    )

    dangerous_junctions = dangerous_junctions.merge(
        yearly_stats,
        how='left',
        on='junction_cluster_id'
    )
    return dangerous_junctions


def create_collision_labels(row: pd.DataFrame, casualty_type: str) -> str:
    """
    Takes a row of data from a dataframe and extracts info for collision map labels
    """
    collision_index = row['collision_index']
    date = row['date']
    danger_metric = np.round(row['recency_danger_metric'], 2)
    n_fatal = int(row[f'fatal_{casualty_type}_casualties'])
    n_serious = int(row[f'serious_{casualty_type}_casualties'])
    n_slight = int(row[f'slight_{casualty_type}_casualties'])
    severity = row[f'max_{casualty_type}_severity']
    link = row['stats19_link']

    label = f"""
        <h3>{collision_index}</h3>
        Date: <b>{date}</b> <br>
        Collision danger metric: <b>{danger_metric}</b> <br>
        Max {casualty_type} severity: <b>{severity}</b> <br>
        <a href="{link}" target="_blank">Stats19 report</a>
        <hr>
        Fatal {casualty_type} casualties: <b>{n_fatal}</b> <br>
        Serious {casualty_type} casualties: <b>{n_serious}</b> <br>
        Slight {casualty_type} casualties: <b>{n_slight}</b>
    """
    return label


def create_junction_labels(row: pd.DataFrame, casualty_type: str) -> str:
    """
    Takes a row of data from a dataframe and extracts info for junction map labels
    """
    junction_name = row['junction_cluster_name']
    rank = int(row['junction_rank'])
    recency_metric = np.round(row['recency_danger_metric'], 2)
    n_fatal = int(row[f'fatal_{casualty_type}_casualties'])
    n_serious = int(row[f'serious_{casualty_type}_casualties'])
    n_slight = int(row[f'slight_{casualty_type}_casualties'])
    notes = row['notes']

    label = f"""
        <h3>{junction_name}</h3>
        Dangerous Junction Rank: <b>{rank}</b> <br>
        Danger Metric: <b>{recency_metric}</b> <br>
        <hr>
        Fatal {casualty_type} casualties: <b>{n_fatal}</b> <br>
        Serious {casualty_type} casualties: <b>{n_serious}</b> <br>
        Slight {casualty_type} casualties: <b>{n_slight}</b>
        <hr>
        {notes}
    """
    return label


@st.cache_data(show_spinner=False, ttl=3*60)
def calculate_dangerous_junctions(
    junction_collisions: pd.DataFrame,
    n_junctions: int,
    casualty_type: str
) -> pd.DataFrame:
    """
    Calculate most dangerous junctions in data and return n worst.
    """
    grp_cols = [
        'junction_cluster_id', 'junction_cluster_name',
        'latitude_cluster', 'longitude_cluster', 'notes'
    ]
    agg_cols = [
        'recency_danger_metric',
        f'fatal_{casualty_type}_casualties',
        f'serious_{casualty_type}_casualties',
        f'slight_{casualty_type}_casualties',
    ]

    dangerous_junctions = (
        junction_collisions
        .groupby(grp_cols)[agg_cols]
        .sum()
        .reset_index()
        .sort_values(by=['recency_danger_metric', f'fatal_{casualty_type}_casualties'], ascending=[False, False])
        .head(n_junctions)
        .reset_index()
    )

    dangerous_junctions['junction_rank'] = dangerous_junctions.index + 1

    dangerous_junctions = calculate_metric_trajectories(junction_collisions, dangerous_junctions)

    dangerous_junctions['label'] = dangerous_junctions.apply(
        lambda row: create_junction_labels(row, casualty_type),
        axis=1
    )

    return dangerous_junctions


def get_html_colors(n: int) -> list:
    """
    Function to get n html colour codes along a continuous gradient
    """
    p = sns.color_palette("gist_heat", n + 5)  # + 5 to force the palette to ignore the lighter colours at end
    p.as_hex()
    
    p = [[int(i * 255) for i in c] for c in p[:]]
    html_p = ["#{0:02x}{1:02x}{2:02x}".format(c[0], c[1], c[2]) for c in p[:]]
    
    return html_p


@st.cache_data(show_spinner=False, ttl=3*60)
def get_low_level_junction_data(junction_collisions: pd.DataFrame, chosen_point: list) -> pd.DataFrame:
    """
    Given a chosen junction get the low level collision data for that junction
    """
    low_junction_collisions = junction_collisions[
        (junction_collisions['latitude_cluster'] == chosen_point[0]) &
        (junction_collisions['longitude_cluster'] == chosen_point[1])
    ]
    return low_junction_collisions


def high_level_map(dangerous_junctions: pd.DataFrame, map_data: pd.DataFrame, n_junctions: int) -> folium.Map:
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
            height=300
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
    initial_location: list, n_junctions: int, casualty_type: str) -> folium.Map:
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

        cols = ['latitude', 'longitude', f'max_{casualty_type}_severity', 'collision_label']
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
                width=200,
                height=180
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

