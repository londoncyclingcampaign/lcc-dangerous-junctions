import os
import yaml
import folium
import streamlit as st
import polars as pl
import seaborn as sns

from yaml import Loader
from folium.features import DivIcon
from fsspec import filesystem


# read in data params
DATA_PARAMETERS = yaml.load(open("params.yaml", 'r'), Loader=Loader)

# set as "prod" in the hosted environment
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")


@st.cache_resource(show_spinner=False, ttl=24*3600)
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


@st.cache_resource(show_spinner=False, ttl=3*60)
def combine_junctions_and_collisions(
    _junctions: pl.DataFrame,
    _collisions: pl.DataFrame,
    _notes: pl.DataFrame,
    casualty_type: str,
    boroughs: str,
    ) -> pl.DataFrame:
    """
    Combines the junction and collision datasets, as well as filters by years chosen in app.
    """
    if casualty_type == 'cyclist':
        _collisions = _collisions.filter(is_cyclist_collision=True)
    elif casualty_type == 'pedestrian':
        _collisions = _collisions.filter(is_pedestrian_collision=True)

    junction_collisions = (
        _junctions
        .with_columns(pl.col('junction_index').cast(pl.Float64))
        .join(
            _collisions,
            how='inner',  # inner as we don't care about junctions with no collisions
            on=['junction_id', 'junction_index']
        )
        .join(
            _notes,
            how='left',
            on='junction_cluster_id'
        )
        .with_columns('notes')
        .fill_null('')
    )

    if 'ALL' not in boroughs:
        junction_collisions = junction_collisions.filter(pl.col('borough').is_in(boroughs))

    junction_collisions = get_danger_metric(junction_collisions, casualty_type)

    # add stats19 link column
    junction_collisions = junction_collisions.with_columns(
        stats19_link = (
            pl
            .col('collision_index')
            .map_elements(lambda x: f"https://www.cyclestreets.net/collisions/reports/{x}/")
        )
    )
    junction_collisions = create_collision_labels(junction_collisions, casualty_type)

    return junction_collisions


def get_danger_metric(df, casualty_type, params=DATA_PARAMETERS):
    '''
    Upweights more severe collisions for junction comparison.
    Only take worst severity, so if multiple casualties involved we have to ignore less severe.
    '''
    df = (
        df
        .with_columns(
            danger_metric = (
                pl.when(
                    pl.col(f'fatal_{casualty_type}_casualties') > 0
                )
                .then(params['weight_fatal'])
                .when(pl.col(f'serious_{casualty_type}_casualties') > 0)
                .then(params['weight_serious'])
                .when(pl.col(f'slight_{casualty_type}_casualties') > 0)
                .then(params['weight_slight'])
                .otherwise(None)
            )
        )
        .with_columns(
            recency_danger_metric = (
                pl.col('danger_metric') * pl.col('recency_weight')
            )
        )
    )
    return df


def get_all_year_df(junction_collisions: pl.DataFrame) -> pl.DataFrame:
    """
    Function to get a dataframe containing all years and cluster combinations possible
    """
    all_years = junction_collisions.select('year').unique()
    all_clusters = junction_collisions.select('junction_cluster_id').unique()
    all_years = all_years.with_columns(key = 0)
    all_clusters = all_clusters.with_columns(key = 0)

    all_years = all_years.join(all_clusters, how='outer', on='key').drop('key')
    return all_years


def calculate_metric_trajectories(junction_collisions: pl.DataFrame, dangerous_junctions: pl.DataFrame) -> pl.DataFrame:
    """
    Function to aggregate by junction and calculate danger metric, plus work out the trajectory of the metric.
    TODO - split this function out.
    """
    dangerous_junction_cluster_ids = dangerous_junctions.get_column('junction_cluster_id').unique()

    junction_collisions = junction_collisions.filter(
        pl.col('junction_cluster_id').is_in(dangerous_junction_cluster_ids)
    )

    all_years_mapping = get_all_year_df(junction_collisions)

    yearly_stats = (
        junction_collisions
        .group_by(['junction_cluster_id', 'year'])
        .agg(
            pl.col('danger_metric').sum()
        )
    )

    yearly_stats = (
        all_years_mapping
        .join(
            yearly_stats,
            how='left',
            on=['year', 'junction_cluster_id']
        )
        .fill_null(0)
        .sort(by=['junction_cluster_id', 'year'])
        .group_by('junction_cluster_id')
        .agg(
            pl.col('danger_metric').explode().alias('yearly_danger_metrics')
        )
    )

    dangerous_junctions = dangerous_junctions.join(
        yearly_stats,
        how='left',
        on='junction_cluster_id'
    )
    return dangerous_junctions


def create_collision_labels(df: pl.DataFrame, casualty_type: str) -> str:
    """
    Takes a row of data from a dataframe and extracts info for collision map labels
    """
    label_format = ("""
            <h3>{0}</h3>
            Date: <b>{0}</b> <br>
            Collision danger metric: <b>{0}</b> <br>
            Max {1} severity: <b>{0}</b> <br>
            <a href="{0}" target="_blank">Stats19 report</a>
            <hr>
            Fatal {1} casualties: <b>{0}</b> <br>
            Serious {1} casualties: <b>{0}</b> <br>
            Slight {1} casualties: <b>{0}</b>
        """.format("{}", casualty_type)
    )

    df = df.with_columns(
        collision_label = pl.format(
            label_format,
            'collision_index',
            'date',
            'danger_metric',
            f'max_{casualty_type}_severity',
            'stats19_link',
            f'fatal_{casualty_type}_casualties',
            f'serious_{casualty_type}_casualties',
            f'slight_{casualty_type}_casualties'
        )
    )

    return df


def create_junction_labels(df: pl.DataFrame, casualty_type: str) -> str:
    """
    Takes a row of data from a dataframe and extracts info for junction map labels
    """
    label_format = (
        """
            <h3>{0}</h3>
            Dangerous Junction Rank: <b>{0}</b> <br>
            Danger Metric: <b>{0}</b> <br>
            <hr>
            Fatal {1} casualties: <b>{0}</b> <br>
            Serious {1} casualties: <b>{0}</b> <br>
            Slight {1} casualties: <b>{0}</b>
            <hr>
        """.format("{}", casualty_type)
    )

    df = df.with_columns(
        label = pl.format(
            label_format,
            'junction_cluster_name',
            'junction_rank',
            'recency_danger_metric',
            f'fatal_{casualty_type}_casualties',
            f'serious_{casualty_type}_casualties',
            f'slight_{casualty_type}_casualties'
        )
    )

    return df


@st.cache_resource(show_spinner=False, ttl=3*60)
def calculate_dangerous_junctions(
    _junction_collisions: pl.DataFrame,
    n_junctions: int,
    casualty_type: str
) -> pl.DataFrame:
    """
    Calculate most dangerous junctions in data and return n worst.
    """
    grp_cols = [
        'junction_cluster_id', 'junction_cluster_name',
        'latitude_cluster', 'longitude_cluster', 'notes'
    ]

    dangerous_junctions = (
        _junction_collisions
        .group_by(grp_cols)
        .agg(
            pl.col('recency_danger_metric').sum(),
            pl.col(f'fatal_{casualty_type}_casualties').sum(),
            pl.col(f'serious_{casualty_type}_casualties').sum(),
            pl.col(f'slight_{casualty_type}_casualties').sum()
        )
        .sort(by=['recency_danger_metric', f'fatal_{casualty_type}_casualties'], descending=[True, True])
        .head(n_junctions)
        .with_row_count(name='junction_rank', offset=1)
    )

    dangerous_junctions = calculate_metric_trajectories(_junction_collisions, dangerous_junctions)

    dangerous_junctions = create_junction_labels(dangerous_junctions, casualty_type)

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


@st.cache_resource(show_spinner=False, ttl=3*60)
def get_low_level_junction_data(junction_collisions: pl.DataFrame, chosen_point: list) -> pl.DataFrame:
    """
    Given a chosen junction get the low level collision data for that junction
    """
    low_junction_collisions = junction_collisions.filter(
        (pl.col('latitude_cluster') == chosen_point[0]) &
        (pl.col('longitude_cluster') == chosen_point[1])
    )
    return low_junction_collisions


def high_level_map(dangerous_junctions: pl.DataFrame, map_data: pl.DataFrame, n_junctions: int) -> folium.Map:
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

    dangerous_junction_cluster_ids = dangerous_junctions.get_column('junction_cluster_id').unique()
    map_data = map_data.filter(
        pl.col('junction_cluster_id').is_in(dangerous_junction_cluster_ids)
    )

    pal = get_html_colors(n_junctions)

    # add junction markers
    cols = ['latitude_cluster', 'longitude_cluster', 'label', 'junction_rank']

    for lat, lon, label, rank in dangerous_junctions.select(cols).rows()[::-1]:
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
    sw = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].min().rows()[0]
    ne = dangerous_junctions[['latitude_cluster', 'longitude_cluster']].max().rows()[0]
    m.fit_bounds([sw, ne])

    return m


def low_level_map(
    dangerous_junctions: pl.DataFrame, junction_collisions: pl.DataFrame,
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
    for id, lat, lon, junction_rank in dangerous_junctions.select(cols).rows():

        # filter lower level data to cluster
        id_collisions = junction_collisions.filter(pl.col('junction_cluster_id') == id)

        cols = ['latitude', 'longitude', f'max_{casualty_type}_severity', 'collision_label']
        for collision_lat, collision_lon, severity, label in id_collisions.select(cols).rows():
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

