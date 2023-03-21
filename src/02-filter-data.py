"""
This takes a set of collision data cleaned with the stats19 data and cleans it further for use by LCC, including:
- Filtering to London
- Filtering to collisions at junctions only
- Weights the severity of collisions
"""
import yaml
import pandas as pd
import numpy as np

from yaml import Loader


def accident_severity_counts(row):
    '''
    Count severities of each type
    '''
    severities = row['casualty_severity']
    severities = severities.tolist()
    
    fatal = severities.count('fatal')
    serious = severities.count('serious')
    slight = severities.count('slight')
    
    return fatal, serious, slight


def get_danger_metric(row):
    '''
    Upweights more severe collisions for junction comparison.
    '''
    fatal = row['fatal_cyclist_casualties']
    serious = row['serious_cyclist_casualties']
    slight = row['slight_cyclist_casualties']
    
    danger_meric = 5 * fatal + 3 * serious + slight
        
    return danger_meric


def get_recency_danger_metric(row, min_year):
    '''
    Upweights more severe collisions for junction comparison.
    '''
    year = row['year']
    danger_metric = row['danger_metric']
    
    recency_weight = np.log10(year - min_year + 2)
    
    recency_danger_metric = danger_metric * recency_weight
        
    return recency_danger_metric


def get_max_cyclist_severity(row):
    '''
    Finds the max severity of a cyclist in collision
    '''
    if row['fatal_cyclist_casualties'] > 0:
        return 'fatal'
    if row['serious_cyclist_casualties'] > 0:
        return 'serious'
    if row['slight_cyclist_casualties'] > 0:
        return 'slight'
    else:
        return None


def recalculate_severity(casualties, min_year):
    '''
    recalculate severities based on cyclists only + apply weightings
    '''
    recalculated_severities = (
        casualties
        [casualties['mode_of_travel'] == 'pedal_cycle']
        .groupby(['collision_id'])
        .apply(accident_severity_counts)
        .reset_index()
    )

    # split out cols
    new_cols = [
        'fatal_cyclist_casualties', 'serious_cyclist_casualties', 'slight_cyclist_casualties'
    ]
    recalculated_severities[new_cols] = pd.DataFrame(
        recalculated_severities[0].tolist(),
        index=recalculated_severities.index
    )

    recalculated_severities['danger_metric'] = recalculated_severities.apply(
        get_danger_metric, axis=1
    )
    recalculated_severities['max_cyclist_severity'] = recalculated_severities.apply(
        get_max_cyclist_severity, axis=1
    )

    # remove unrequired cols
    recalculated_severities.drop(columns=[0], inplace=True)

    return recalculated_severities


def main():

    # read in data processing params from params.yaml
    params = yaml.load(open("params.yaml", 'r'), Loader=Loader)

    print('Reading in data')
    collisions = pd.read_csv('data/collisions.csv', low_memory=False)
    casualties = pd.read_csv('data/casualties.csv', low_memory=False)

    # filter to junctions
    print('Filter to Junctions')
    junction_types = params['valid_junction_types']
    collisions = collisions[collisions.junction_detail.isin(junction_types)]

    # pull out all cyclist crash ids
    cyclist_crash_ids = casualties[
        casualties['mode_of_travel'] == 'pedal_cycle'
    ]['collision_id'].unique()

    print(f'Filter to cyclist collisions, {len(cyclist_crash_ids)} crash IDs in data')

    collisions = collisions[collisions.collision_id.isin(cyclist_crash_ids)]
    casualties = casualties[casualties.collision_id.isin(cyclist_crash_ids)]

    print('Recalculate severities and danger metrics')
    min_year = min(collisions['year'])
    recalculated_severities = recalculate_severity(casualties, min_year)

    # # join back to the datasets with severity in it
    collisions = collisions.merge(recalculated_severities, how='left', on='collision_id')
    # casualties = casualties.merge(recalculated_severities, how='left', on='collision_id')
    
    collisions['recency_danger_metric'] = collisions.apply(
        lambda row: get_recency_danger_metric(row, min_year), axis=1
    )

    print(collisions)

    # output csvs
    print('Output to csv')
    collisions.to_csv('data/cycling-collisions.csv', index=False)
    # casualties.to_csv('data/collision-data/london-casualties.csv', index=False)


if __name__ == "__main__":
    main()

