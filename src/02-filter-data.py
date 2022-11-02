"""
This takes a set of collision data cleaned with the stats19 data and cleans it further for use by LCC, including:
- Filtering to London
- Filtering to crashes at junctions only
- Weights the severity of crashes
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
    
    fatal = severities.count('Fatal')
    serious = severities.count('Serious')
    slight = severities.count('Slight')
    
    return fatal, serious, slight


def get_danger_metric(row):
    '''
    Upweights more severe collisions for junction comparison.
    '''
    fatal = row['fatal_cyclist_casualties']
    serious = row['serious_cyclist_casualties']
    
    total_severity = 3 * fatal + serious
        
    return total_severity


def get_recency_danger_metric(row, min_year):
    '''
    Upweights more severe collisions for junction comparison.
    '''
    year = row['accident_year']
    fatal = row['fatal_cyclist_casualties']
    serious = row['serious_cyclist_casualties']
    
    recency_weight = np.log10(year - min_year + 1)
    
    total_severity = 3 * fatal + serious
    weighted_severity = total_severity * recency_weight
        
    return weighted_severity


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
        casualties[casualties['casualty_type'] == 'Cyclist']
        .groupby(['accident_index', 'accident_year'])
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
    recalculated_severities['recency_danger_metric'] = recalculated_severities.apply(
        lambda row: get_recency_danger_metric(row, min_year), axis=1
    )
    recalculated_severities['max_cyclist_severity'] = recalculated_severities.apply(
        get_max_cyclist_severity, axis=1
    )

    # remove unrequired cols
    recalculated_severities.drop(columns=[0, 'accident_year'], inplace=True)

    return recalculated_severities


def main():

    # read in data processing params from params.yaml
    params = yaml.load(open("params.yaml", 'r'), Loader=Loader)

    print('Reading in data')
    crashes = pd.read_csv('data/collision-data/crashes.csv', low_memory=False)
    casualties = pd.read_csv('data/collision-data/casualties.csv', low_memory=False)
    vehicles = pd.read_csv('data/collision-data/vehicles.csv', low_memory=False)

    # filter to london
    print('Filter to London')
    crashes = crashes[
        (crashes['latitude'] >= params['min_latitude']) &
        (crashes['latitude'] <= params['max_latitude']) &
        (crashes['longitude'] >= params['min_longitude']) &
        (crashes['longitude'] <= params['max_longitude'])
    ]

    # filter to junctions
    print('Filter to Junctions')
    junction_types = params['valid_junction_types']
    crashes = crashes[crashes.junction_detail.isin(junction_types)]

    # now filter casualty and vehicle data to only include crash IDs from the crashes data
    casualties = casualties[casualties.accident_index.isin(crashes.accident_index)]
    vehicles = vehicles[vehicles.accident_index.isin(crashes.accident_index)]

    # pull out all cyclist crash ids
    cyclist_crash_ids = casualties[
        casualties['casualty_type'] == 'Cyclist'
    ]['accident_index'].unique()

    print(f'Filter to cyclist collisiions, {len(cyclist_crash_ids)} crash IDs in data')

    crashes = crashes[crashes.accident_index.isin(cyclist_crash_ids)]
    casualties = casualties[casualties.accident_index.isin(cyclist_crash_ids)]
    vehicles = vehicles[vehicles.accident_index.isin(cyclist_crash_ids)]

    print('Recalculate severities and danger metrics')
    min_year = min(crashes['accident_year'])
    recalculated_severities = recalculate_severity(casualties, min_year)

    # join back to the datasets with severity in it
    crashes = crashes.merge(recalculated_severities, how='left', on='accident_index')
    casualties = casualties.merge(recalculated_severities, how='left', on='accident_index')

    # output csvs
    print('Output to csv')
    crashes.to_csv('data/collision-data/london-crashes.csv', index=False)
    casualties.to_csv('data/collision-data/london-casualties.csv', index=False)
    vehicles.to_csv('data/collision-data/london-vehicles.csv', index=False)


if __name__ == "__main__":
    main()