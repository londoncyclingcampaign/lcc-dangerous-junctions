import streamlit as st
import pandas as pd
import pydeck as pdk


st.set_page_config(layout="wide")
st.markdown('# Dangerous Junctions')


# PART 1

junctions = pd.read_csv('data/top-100-dangerous-junctions.csv')
collisions = pd.read_csv('data/top-100-dangerous-junction-collisions.csv')

n = st.slider('Select number of dangerous junctsions to show', 0, 100, 5)

st.dataframe(junctions.head(n))

st.map(junctions.head(n), zoom=12)


# PART 2

st.markdown('---')
st.markdown('## Investigate Junctions')

selected_junctions = st.multiselect(
	label='Select junction to investigate',
	options=junctions.cluster.unique(),
	default=junctions.cluster.unique()[0]
)


st.pydeck_chart(pdk.Deck(
     map_style='mapbox://styles/mapbox/light-v9',
     initial_view_state=pdk.ViewState(
         latitude=collisions[collisions.cluster.isin(selected_junctions)]['latitude'].mean(),
         longitude=collisions[collisions.cluster.isin(selected_junctions)]['longitude'].mean(),
         zoom=16
     ),
     layers=[
         pdk.Layer(
             'ScatterplotLayer',
             data=collisions[collisions.cluster.isin(selected_junctions)],
             get_position='[longitude, latitude]',
             get_color='[200, 30, 0, 160]',
             get_radius=5,
             auto_highlight=True
         ),
     ],
 ))

st.dataframe(collisions[collisions.cluster.isin(selected_junctions)])

