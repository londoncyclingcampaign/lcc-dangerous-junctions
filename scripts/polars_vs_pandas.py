"""
Is it worth switching from pandas to polars for speed and lower memeory usage?
"""
import sys
import yaml
import time
import polars as pl
import pandas as pd

from yaml import Loader

DATA_PARAMETERS = yaml.load(open("params.yaml", 'r'), Loader=Loader)

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

