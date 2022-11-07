import folium
import geopandas
import streamlit as st
import numpy as np
import pandas as pd
import pydeck as pdk

from streamlit_folium import st_folium, folium_static


# TODO: Prevent maps re-rendering when the other is changed


@st.cache
def read_in_data():
    junctions = pd.read_csv('data/junctions.csv')
    collisions = pd.read_csv('data/collisions.csv')

    return junctions, collisions


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


def generate_map(map_data, junction_collisions, radius=6, color='blue', zoom=12):
    avg_lat = map_data['latitude_cluster'].mean()
    avg_lon = map_data['longitude_cluster'].mean()

    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=zoom)

    cols = ['junction_cluster_id', 'latitude_cluster', 'longitude_cluster', 'label']
    for cluster_id, lat, lon, label in map_data[cols].values:
        iframe = folium.IFrame(label)
        popup = folium.Popup(iframe, min_width=240, max_width=240)
        folium.Marker(
            location=[lat, lon],
            popup=popup,
            radius=4
        ).add_to(m)

        # filter lower level data to cluster
        id_collisions = junction_collisions[junction_collisions['junction_cluster_id'] == cluster_id]

        collision_coords = id_collisions[['latitude', 'longitude']].dropna().values

        # draw lines between central point and collisions
        lines = folium.PolyLine(locations=[[coord, [lat, lon]] for coord in collision_coords], weight=3, color='grey')
        m.add_child(lines)

        for collision_lat, collision_lon in collision_coords:
            folium.CircleMarker(
                location=[collision_lat, collision_lon],
                # popup=label,
                fill=True,
                color='orange',
                fill_color='orange',
                radius=2
            ).add_to(m)


    sw = map_data[['latitude_cluster', 'longitude_cluster']].min().values.tolist()
    ne = map_data[['latitude_cluster', 'longitude_cluster']].max().values.tolist()
    m.fit_bounds([sw, ne])

    folium_static(m, width=1800, height=800)
    return None


# =========================================================================== #

st.set_page_config(layout="wide")
st.markdown('# Dangerous Junctions')

junctions, collisions = read_in_data()

col1, col2, col3, col4, col5 = st.columns([4, 1, 4, 1, 4])

with col1:
    n_junctions = st.slider(
        label='Number of dangerous junctions to show:',
        min_value=0,
        max_value=200,  # not sure we'd ever need to view more?
        # max_value=junctions.junction_cluster_id.nunique(),
        value=20,
    )

with col3:
    min_year, max_year = st.slider(
        label='Select date period:',
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

generate_map(dangerous_junctions, junction_collisions)
st.dataframe(dangerous_junctions)

