import os
import yaml
import folium
import streamlit as st
import numpy as np
import pandas as pd
import seaborn as sns

from yaml import Loader
from pympler import asizeof
from folium.features import DivIcon
from st_files_connection import FilesConnection


# read in data params
DATA_PARAMETERS = yaml.load(open("params.yaml", 'r'), Loader=Loader)

# set as "prod" in the hosted environment
ENVIRONMENT = os.environ.get("ENVIRONMENT", "prod")


@st.cache_data(show_spinner=False, ttl=24*60*60, max_entries=1)
def read_in_data(params: dict = DATA_PARAMETERS) -> tuple:
    """
    Function to read in different data depending on tolerance requests.
    Reads from local if not on streamlit server, otherwise from google sheets.
    """
    if ENVIRONMENT == 'dev':
        junctions = pd.read_parquet(
            f'data/junctions-tolerance=15.parquet',
            engine='pyarrow',
            columns=params['junction_app_columns']
        )
        collisions = pd.read_parquet(
            f'data/collisions-tolerance=15.parquet',
            engine='pyarrow',
            columns=params['collision_app_columns']
        )
    else:
        conn = st.connection('gcs', type=FilesConnection)
        junctions = conn.read(
            "lcc-app-data/2019-2023/junctions-tolerance=15.parquet",
            input_format="parquet",
            engine='pyarrow',
            columns=params['junction_app_columns']
        )
        collisions = conn.read(
            "lcc-app-data/2019-2023/collisions-tolerance=15.parquet",
            input_format="parquet",
            engine='pyarrow',
            columns=params['collision_app_columns']
        )

    try:
        junction_notes = pd.read_csv(st.secrets["junction_notes"])
    except FileNotFoundError:
        junction_notes = pd.DataFrame(columns=["junction_cluster_id", "notes"])

    return junctions, collisions, junction_notes


@st.cache_data(show_spinner=False, ttl=3*60, max_entries=5)
def combine_junctions_and_collisions(
    junctions: pd.DataFrame,
    collisions: pd.DataFrame,
    notes: pd.DataFrame,
    casualty_type: str,
    boroughs: str
    ) -> pd.DataFrame:
    """
    Combines the junction and collision datasets, as well as filters by years chosen in app.
    """
    if casualty_type == 'cyclist':
        collisions = collisions[collisions['is_cyclist_collision']]
    elif casualty_type == 'pedestrian':
        collisions = collisions[collisions['is_pedestrian_collision']]

    junction_collisions = (
        junctions
        .merge(
            collisions,
            how='inner',  # inner as we don't care about junctions with no collisions
            on=['junction_id', 'junction_index']
        )
        .merge(
            notes,
            how='left',
            on='junction_cluster_id'
        )
    )
    junction_collisions.loc[junction_collisions['notes'].isna(), 'notes'] = ''

    if 'ALL' not in boroughs:
        junction_collisions = junction_collisions[junction_collisions['borough'].isin(boroughs)]

    junction_collisions['danger_metric'] = junction_collisions.apply(
        lambda row: get_danger_metric(
            row, casualty_type
        ), axis=1
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


def get_danger_metric(
    row: pd.DataFrame,
    casualty_type: str,
    weight_fatal: float = DATA_PARAMETERS['weight_fatal'],
    weight_serious: float = DATA_PARAMETERS['weight_serious'],
    weight_slight: float = DATA_PARAMETERS['weight_slight'],
):
    '''
    Upweights more severe collisions for junction comparison.
    Only take worst severity, so if multiple casualties involved we have to ignore less severe.
    '''
    fatal = row[f'fatal_{casualty_type}_casualties']
    serious = row[f'serious_{casualty_type}_casualties']
    slight = row[f'slight_{casualty_type}_casualties']

    danger_metric = None
    if fatal > 0:
        danger_metric = weight_fatal
    elif serious > 0:
        danger_metric = weight_serious
    elif slight > 0:
        danger_metric = weight_slight
    
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


@st.cache_data(show_spinner=False, ttl=3*60, max_entries=5)
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


@st.cache_data(show_spinner=False, ttl=3*60, max_entries=5)
def get_low_level_junction_data(junction_collisions: pd.DataFrame, chosen_point: list) -> pd.DataFrame:
    """
    Given a chosen junction get the low level collision data for that junction
    """
    low_junction_collisions = junction_collisions[
        (junction_collisions['latitude_cluster'] == chosen_point[0]) &
        (junction_collisions['longitude_cluster'] == chosen_point[1])
    ]
    return low_junction_collisions


@st.cache_data(show_spinner=False, ttl=3*60, max_entries=5)
def get_map_bounds(top_dangerous_junctions: pd.DataFrame) -> list:
    """
    Slight hack to make sure the high map center updates when required, but not otherwise
    """
    sw = top_dangerous_junctions[['latitude_cluster', 'longitude_cluster']].min().values.tolist()
    ne = top_dangerous_junctions[['latitude_cluster', 'longitude_cluster']].max().values.tolist()

    return [sw, ne]


@st.cache_data(show_spinner=False, ttl=3*60, max_entries=5)
def get_most_dangerous_junction_location(first_row_dangerous_junctions: pd.DataFrame) -> list:
    """
    Slight hack to make sure the low level map only updates when the first row of data changes
    """
    location = first_row_dangerous_junctions[['latitude_cluster', 'longitude_cluster']].values[0]
    return location


def create_base_map(initial_location: list, initial_zoom: int) -> folium.Map:
    """
    Create a base map object to add points to later on.
    """
    m = folium.Map(
        tiles='cartodbpositron',
        location=initial_location,
        zoom_start=initial_zoom
    )

    borough_geo = "london_boroughs.geojson"
    folium.Choropleth(
        geo_data=borough_geo,
        line_color='#5DADE2', 
        fill_opacity=0, 
        line_opacity=.5,
        overlay=False,
    ).add_to(m)

    return m


def get_high_level_fg(dangerous_junctions: pd.DataFrame, map_data: pd.DataFrame, n_junctions: int) -> folium.FeatureGroup:
    """
    Function to generate feature groups to add to high level map
    """
    fg = folium.FeatureGroup(name="Junctions")

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
        fg.add_child(
            folium.CircleMarker(
                location=[lat, lon],
                radius=10,
                color=pal[rank - 1],
                fill_color=pal[rank - 1],
                fill_opacity=1,
                z_index_offset=1000 + (100 - rank)
            )
        )

        if rank < 10:
            i = 3
        else:
            i = 8
        fg.add_child(folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(iframe),
            icon=DivIcon(
                icon_size=(30,30),
                icon_anchor=(i,11),
                html=f'<div style="font-size: 10pt; font-family: monospace; color: white">%s</div>' % str(rank),
            ),
            z_index_offset=1000 + (100 - rank)
        ))

    return fg


def get_low_level_fg(
    dangerous_junctions: pd.DataFrame, junction_collisions: pd.DataFrame,
    n_junctions: int, casualty_type: str) -> folium.FeatureGroup:
    """
    Function to generate feature groups to add to low level map
    """
    fg = folium.FeatureGroup(name="Collisions")

    pal = get_html_colors(n_junctions)

    cols = ['junction_cluster_id', 'latitude_cluster', 'longitude_cluster', 'junction_rank']
    for id, lat, lon, junction_rank in dangerous_junctions[cols].values:

        # filter lower level data to cluster
        id_collisions = junction_collisions[junction_collisions['junction_cluster_id'] == id]

        cols = ['latitude', 'longitude', f'max_{casualty_type}_severity', 'collision_label']
        for collision_lat, collision_lon, severity, label in id_collisions[cols].dropna().values:
            # draw lines between central point and collisions
            fg.add_child(
                folium.PolyLine(
                    locations=[[[collision_lat, collision_lon], [lat, lon]]],
                    weight=.8,
                    color='grey'
                )
            )

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
                fg.add_child(
                    folium.CircleMarker(
                        location=[collision_lat, collision_lon],
                        popup=folium.Popup(iframe),
                        fill=True,
                        color='#D35400',
                        fill_color='#D35400',
                        fill_opacity=1,
                        radius=3
                    )
                )
            elif severity == 'serious':
                fg.add_child(
                    folium.CircleMarker(
                        location=[collision_lat, collision_lon],
                        popup=folium.Popup(iframe),
                        fill=True,
                        color='#F39C12',
                        fill_color='#F39C12',
                        fill_opacity=1,
                        radius=3
                    )
                )
            elif severity == 'slight':
                fg.add_child(
                    folium.CircleMarker(
                        location=[collision_lat, collision_lon],
                        popup=folium.Popup(iframe),
                        fill=True,
                        color='#F7E855',
                        fill_color='#F7E855',
                        fill_opacity=1,
                        radius=3
                    )
                )

        rank = int(junction_rank)
        fg.add_child(
            folium.CircleMarker(
                location=[lat, lon],
                radius=10,    
                fill_opacity=1
            )
        )

        fg.add_child(
            folium.CircleMarker(
                location=[lat, lon],
                radius=10,    
                color=pal[rank - 1],
                fill_color=pal[rank - 1],
                fill_opacity=1
            )
        )

        if rank < 10:
            i = 3
        else:
            i = 8
        fg.add_child(
            folium.map.Marker(
                location=[lat, lon],
                icon=DivIcon(
                    icon_size=(30,30),
                    icon_anchor=(i,11),
                    html=f'<div style="font-size: 10pt; font-family: monospace; color: white">%s</div>' % str(rank)
                )
            )
        )

    return fg


def get_highest_memory_objects(locals: dict) -> list:
    """
    To help identify memory bloat, returns list of any objects >= 1mb in size.
    """
    highest_mem_objects = {}
    for key in list(locals.keys()):
        if key != 'asizeof':
            # if type(locals[key]) == pl.dataframe.frame.DataFrame:
            #     size_mb = locals[key].estimated_size("mb")
            if str(type(locals[key])) == pd.core.frame.DataFrame:
                size_mb = locals[key].memory_usage(index=True).sum() / 1024 / 1024
            else:
                size_mb = asizeof.asizeof(locals[key]) / 1024 / 1024
            if size_mb >= 1:
                highest_mem_objects[key] = size_mb

    return highest_mem_objects
