import folium
import geopandas
import streamlit as st
import pandas as pd
import pydeck as pdk

from streamlit_folium import st_folium, folium_static


# TODO: Prevent maps re-rendering when the other is changed


@st.cache
def read_in_data():
    junctions = pd.read_csv('data/junctions.csv')
    collisions = pd.read_csv('data/collisions.csv')

    # junctions['map_label'] = junctions['cluster'].apply(lambda x: f'Cluster: {x}')
    # collisions['map_label'] = collisions.apply(
    #     lambda row: f"""
    #     ID: {row['id']}, Cluster: {row['cluster']}, Date: {row['date']}, 
    #     Serious casualties: {row['n_serious']}, Fatal casualties: {row['n_fatal']}
    #     """,
    #     axis=1
    # )
    return junctions, collisions


def combine_junctions_and_collisions(junctions, collisions, min_year, max_year):
    junction_collisions = (
        junctions
        .merge(
            collisions[
                (collisions['accident_year'] >= min_year) &
                (collisions['accident_year'] <= max_year)
            ],
            how='left',
            on=['junction_id', 'junction_index']
        )
    )

    return junction_collisions


def calculate_dangerous_junctions(junction_collisions, n_junctions):
    dangerous_junctions = (
        junction_collisions
        .groupby(['junction_cluster_id', 'latitude_cluster', 'longitude_cluster'])['recency_danger_metric']
        .sum()
        .reset_index()
        .sort_values(by='recency_danger_metric', ascending=False)
        .head(n_junctions)
    )

    return dangerous_junctions


def generate_map(map_data, junction_collisions, radius=6, color='blue', zoom=12):
    avg_lat = map_data['latitude_cluster'].mean()
    avg_lon = map_data['longitude_cluster'].mean()

    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=zoom)

    ids = map_data['junction_cluster_id']

    junction_collisions = junction_collisions[junction_collisions['junction_cluster_id'].isin(ids)]

    for lat, lon in junction_collisions[['latitude_junction', 'longitude_junction']].dropna().values:
        folium.CircleMarker(
            location=[lat, lon],
            # popup=label,
            fill=True,
            color='green',
            fill_color='green',
            radius=1
        ).add_to(m)

    for lat, lon in junction_collisions[['latitude', 'longitude']].dropna().values:
        folium.CircleMarker(
            location=[lat, lon],
            # popup=label,
            fill=True,
            color='red',
            fill_color='red',
            radius=1
        ).add_to(m)

    all_points = pd.concat([
        junction_collisions[['latitude_junction', 'longitude_junction', 'junction_cluster_id']].rename(columns={'latitude_junction': 'latitude', 'longitude_junction': 'longitude'}),
        junction_collisions[['latitude', 'longitude', 'junction_cluster_id']]
    ])
    all_points = geopandas.GeoDataFrame(
        all_points,
        geometry=geopandas.points_from_xy(
            all_points.longitude,
            all_points.latitude,
            crs="EPSG:4326"
        )
    )

    polygons = all_points.dissolve('junction_cluster_id').convex_hull
    folium.GeoJson(polygons).add_to(m)
    folium.LatLngPopup().add_to(m)

    sw = junction_collisions[['latitude', 'longitude']].min().values.tolist()
    ne = junction_collisions[['latitude', 'longitude']].max().values.tolist()
    m.fit_bounds([sw, ne])


    # for lat, lon in map_data[['latitude_cluster', 'longitude_cluster']].values:
    #     folium.CircleMarker(
    #         location=[lat, lon],
    #         # popup=label,
    #         fill=True,
    #         color=color,
    #         fill_color=color,
    #         radius=radius
    #     ).add_to(m)

    folium_static(m, width=1400, height=600)
    return None


# =========================================================================== #

st.set_page_config(layout="wide")
st.markdown('# Dangerous Junctions')

# SECTION 1

junctions, collisions = read_in_data()

n_junctions = st.slider(
    label='Select number of dangerous junctions to show:',
    min_value=0,
    max_value=200,  # not sure we'd ever need to view more?
    # max_value=junctions.junction_cluster_id.nunique(),
    value=25,
)

min_year, max_year = st.slider(
    label='Select minimum year:',
    min_value=2011,
    max_value=2021,
    value=(2015, 2021)
)

junction_collisions = combine_junctions_and_collisions(junctions, collisions, min_year, max_year)
dangerous_junctions = calculate_dangerous_junctions(junction_collisions, n_junctions)

generate_map(dangerous_junctions, junction_collisions)
st.dataframe(dangerous_junctions)


# =========================================================================== #

# SECTION 2

# st.markdown('---')
# st.markdown('## Investigate Junctions')

# selected_junctions = st.multiselect(
# 	label='Select junction to investigate',
# 	options=junctions.cluster.unique(),
# 	default=junctions.cluster.unique()[0]
# )

# selected_junction_collisions = collisions[collisions.cluster.isin(selected_junctions)]

# generate_map(selected_junction_collisions, radius=4, color='red', zoom=16)
# st.dataframe(selected_junction_collisions)

