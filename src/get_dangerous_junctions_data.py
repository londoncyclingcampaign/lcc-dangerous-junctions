"""
Script to pull a csv with most dangerous junctions data.
"""

import os
import yaml

from app_functions import *

ENVIRONMENT = os.environ.get("ENVIRONMENT", "prod")
DATA_PARAMETERS = yaml.load(open("params.yaml", 'r'), Loader=Loader)

junctions, collisions, notes = read_in_data(tolerance=15)


for casualty_type in ['pedestrian', 'cyclist']:
    print(casualty_type)

    OUTPUT_COLS = [
        'borough',
        'casualty_type',
        'junction_rank',
        'junction_cluster_name',
        'latitude_cluster',
        'longitude_cluster',
        'gmaps_link',
        'recency_danger_metric',
        f'fatal_{casualty_type}_casualties',
        f'serious_{casualty_type}_casualties',
        f'slight_{casualty_type}_casualties',
        'notes'
    ]

    dangerous_junctions_list = []
    for borough in collisions['borough'].unique():
        print(borough)

        junction_collisions = combine_junctions_and_collisions(
            junctions,
            collisions,
            notes,
            casualty_type,
            boroughs=[borough]
        )

        dangerous_junctions = calculate_dangerous_junctions(
            junction_collisions,
            n_junctions=10,
            casualty_type=casualty_type
        )

        dangerous_junctions['borough'] = borough
        dangerous_junctions['casualty_type'] = casualty_type

        dangerous_junctions['gmaps_link'] = dangerous_junctions.apply(
            lambda row: f"https://www.google.com/maps/place/{row['latitude_cluster'],row['longitude_cluster']}",
            axis=1
        )

        dangerous_junctions_list.append(dangerous_junctions)

    pd.concat(dangerous_junctions_list)[OUTPUT_COLS].to_csv(
        f'data/2024_{casualty_type}_most_dangerous_junctions.csv',
        index=False
    )

