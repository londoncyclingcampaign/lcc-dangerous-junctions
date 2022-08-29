import folium
import streamlit as st
import pandas as pd
import pydeck as pdk

from streamlit_folium import st_folium, folium_static


@st.cache
def read_in_data():
    junctions = pd.read_csv('data/top-dangerous-junctions.csv')
    collisions = pd.read_csv('data/top-dangerous-junction-collisions.csv')

    junctions['map_label'] = junctions['cluster'].apply(lambda x: f'Cluster: {x}')
    collisions['map_label'] = collisions.apply(
        lambda row: f"""
        ID: {row['id']}, Cluster: {row['cluster']}, Date: {row['date']}, 
        Serious casualties: {row['n_serious']}, Fatal casualties: {row['n_fatal']}
        """,
        axis=1
    )
    return junctions, collisions


def generate_map(map_data, radius=6, color='blue', zoom=12):
    avg_lat = map_data['latitude'].mean()
    avg_lon = map_data['longitude'].mean()

    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=zoom)

    for label, lat, lon in map_data[['map_label', 'latitude', 'longitude']].values:
        folium.CircleMarker(
            location=[lat, lon],
            popup=label,
            fill=True,
            color=color,
            fill_color=color,
            radius=radius
        ).add_to(m)

    folium_static(m, width=1750, height=500)
    return None


# =========================================================================== #

st.set_page_config(layout="wide")
st.markdown('# Dangerous Junctions')

# SECTION 1

junctions, collisions = read_in_data()

n_junctions = st.slider(
    label='Select number of dangerous junctions to show:',
    min_value=0,
    max_value=len(junctions),
    value=5,
)

generate_map(junctions.head(n_junctions))
st.dataframe(junctions.head(n_junctions))


# =========================================================================== #

# SECTION 2

st.markdown('---')
st.markdown('## Investigate Junctions')

selected_junctions = st.multiselect(
	label='Select junction to investigate',
	options=junctions.cluster.unique(),
	default=junctions.cluster.unique()[0]
)

selected_junction_collisions = collisions[collisions.cluster.isin(selected_junctions)]

generate_map(selected_junction_collisions, radius=4, color='red', zoom=16)
st.dataframe(selected_junction_collisions)

