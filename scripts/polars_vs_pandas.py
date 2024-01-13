"""
Is it worth switching from pandas to polars for speed and lower memeory usage?
"""
import sys
import yaml
import time
import polars as pl
import pandas as pd
import streamlit as st

from yaml import Loader
# from st_files_connection import FilesConnection

# storage_client = storage.Client(
#     project='lcc-dangerous-junctions'
# )
from fsspec import filesystem


# secrets = {"token": st.secrets}

DATA_PARAMETERS = yaml.load(open("params.yaml", 'r'), Loader=Loader)


time0 = time.time()
for i in range(10):
    fs = filesystem('gcs', token=st.secrets.connections.gcs.to_dict())
    with fs.open("gs://lcc-app-data/junctions-tolerance=15.parquet", "rb") as f:
        df = pl.read_parquet(
            f,
            columns=DATA_PARAMETERS['junction_app_columns'],
        )
    time1 = time.time()
print(f'Polars: {time1 - time0}')
print(sys.getsizeof(df))

# time0 = time.time()
# for i in range(10):
#     conn = st.experimental_connection('gcs', type=FilesConnection)
#     junctions = conn.read(
#         "lcc-app-data/junctions-tolerance=15.parquet",
#         input_format="parquet",
#         engine='pyarrow',
#         columns=DATA_PARAMETERS['junction_app_columns']
#     )
# time1 = time.time()
# print(f'Pandas: {time1 - time0}')
# print(sys.getsizeof(junctions))

# source = "gs://lcc-app-data/collisions-tolerance=15.parquet"

# df = pl.read_parquet(source)

print(df.head())

n = 10

# POLARS
time0 = time.time()
for i in range(n):
    junctions = pl.read_parquet(
        'data/junctions-tolerance=15.parquet',
        columns=DATA_PARAMETERS['junction_app_columns']
    )
    collisions = pl.read_parquet(
        'data/collisions-tolerance=15.parquet',
        columns=DATA_PARAMETERS['collision_app_columns']
    )
    junctions = junctions.with_columns(pl.col('junction_index').cast(pl.Float64, strict=False))

    junction_collisions = junctions.join(collisions, how='inner', on=['junction_id', 'junction_index'])
time1 = time.time()

print(f'Polars - time: {time1 - time0}s')
print(f'Polars - size: {sys.getsizeof(junction_collisions) / (1024 * 1024)}MB')

# PANDAS
time0 = time.time()
for i in range(n):
    junctions = pd.read_parquet(
        'data/junctions-tolerance=15.parquet',
        engine='pyarrow',
        columns=DATA_PARAMETERS['junction_app_columns']
    )
    collisions = pd.read_parquet(
        'data/collisions-tolerance=15.parquet',
        engine='pyarrow',
        columns=DATA_PARAMETERS['collision_app_columns']
    )

    junction_collisions = junctions.merge(collisions, how='inner', on=['junction_id', 'junction_index'])
time1 = time.time()

print(f'Pandas - time: {time1 - time0}s')
print(f'Pandas - size: {sys.getsizeof(junction_collisions) / (1024 * 1024)}MB')
