import yaml
import pandas as pd

from sklearn.neighbors import BallTree
from yaml import Loader


def get_nearest_junction(row, tree):
    '''
    Find nearest junction to crash / collision. Return distance and the index for junction
    '''
    crash_coordinate = row[['latitude', 'longitude']].values
    result = tree.query([crash_coordinate])

    distance = result[0][0][0]  # result is weirdly nested
    index = result[1][0][0]
    return distance, index


def main():

    # read in data params
    params = yaml.load(open("params.yaml", 'r'), Loader=Loader)

    top_n = params['number_of_dangerous_collisions']
    distance_threshold = params['distance_to_junction_threshold']

    # read in data
    # collisions = (
    #     pd
    #     .read_csv('data/collision-data/london-crashes.csv')
    #     .rename(columns={'accident_index': 'id'})
    # )
    # collisions = collisions[collisions['max_cyclist_severity'] != 'slight']

    # loop through tolerance options.
    for tolerance in [15]:

        print(f'tolerance={tolerance}')

        # read in data
        collisions = (
            pd
            .read_csv('data/cycling-collisions.csv')
            .rename(columns={'collision_id': 'id'})
        )
        collisions = collisions[collisions['max_cyclist_severity'] != 'slight']

        junctions = pd.read_csv(f'data/junctions-tolerance={tolerance}.csv', low_memory=False)

        # Find nearest junction to each collision
        # Use BallTree algorithm.
        # Havesine distance since these are coordinates.

        print('Finding nearest junction to each collision')
        tree = BallTree(junctions[['latitude_junction', 'longitude_junction']], metric='haversine')

        collisions[['distance_to_junction', 'junction_index']] = collisions.apply(
            lambda row: get_nearest_junction(row, tree), axis=1, result_type='expand'
        )

        # join to get junction ids
        collisions = collisions.merge(
            junctions[['junction_index', 'junction_id']],
            how='left',
            on='junction_index'
        )

        # combine datasets
        junction_collisions = (
            junctions
            .merge(
                collisions,
                how='left',
                on=['junction_id', 'junction_index']
            )
        )

        # filter to those within certain distance
        junction_collisions = junction_collisions[
            junction_collisions['distance_to_junction'] <= distance_threshold
        ]

        junction_stats = (
            junction_collisions
            .groupby(['junction_cluster_id', 'latitude_cluster', 'longitude_cluster'])
            .agg({'recency_danger_metric': 'sum', 'slight_cyclist_casualties': 'sum'})
            .sort_values(by='recency_danger_metric', ascending=False)
            .head(top_n)
            .reset_index()
        )

        junction_stats['scaled_metric'] = (
            junction_stats['recency_danger_metric'] / junction_stats['slight_cyclist_casualties']
        )

        collisions = collisions[
            collisions['distance_to_junction'] <= distance_threshold
        ]

        # output data
        junction_stats.to_csv(f'data/dangerous-junctions-tolerance={tolerance}.csv', index=False)
        collisions.to_csv(f'data/collisions-tolerance={tolerance}.csv', index=False)


if __name__ == "__main__":
    main()
