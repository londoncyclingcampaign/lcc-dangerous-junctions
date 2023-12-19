"""
This takes a set of collision data cleaned with the stats19 data and cleans it further for use by LCC, including:
- Filtering to London # JH note - doesn't do this
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
    
    fatal = severities.count('Fatal')
    serious = severities.count('Serious')
    slight = severities.count('Slight')
    
    return fatal, serious, slight


def get_recency_weight(row, min_year):
    '''
    Upweights more severe collisions for junction comparison.
    '''
    year = row['year']
    recency_weight = np.log10(year - min_year + 6)
        
    return recency_weight


def get_max_severity(row, casualty_type):
    '''
    Finds the max severity of a cyclist in collision
    '''
    if row[f'fatal_{casualty_type}_casualties'] > 0:
        return 'fatal'
    if row[f'serious_{casualty_type}_casualties'] > 0:
        return 'serious'
    if row[f'slight_{casualty_type}_casualties'] > 0:
        return 'slight'
    else:
        return None


def recalculate_severity(casualties, mode_of_travel):
    '''
    recalculate severities based on cyclists or pedestrian only + apply weightings
    '''
    recalculated_severities = (
        casualties
        [casualties['casualty_type'] == mode_of_travel]
        .groupby(['accident_index'])
        .apply(accident_severity_counts)
        .reset_index()
    )

    if mode_of_travel == 'Cyclist':
        casualty_type = 'cyclist'
    else:
        casualty_type = mode_of_travel

    # split out cols
    new_cols = [
        f'fatal_{casualty_type}_casualties',
        f'serious_{casualty_type}_casualties',
        f'slight_{casualty_type}_casualties'
    ]
    recalculated_severities[new_cols] = pd.DataFrame(
        recalculated_severities[0].tolist(),
        index=recalculated_severities.index
    )

    recalculated_severities[f'max_{casualty_type}_severity'] = recalculated_severities.apply(
        lambda row: get_max_severity(row, casualty_type), axis=1
    )

    # remove unrequired cols
    recalculated_severities.drop(columns=[0], inplace=True)

    return recalculated_severities


def main():

    params = yaml.load(open("dft_params.yaml", 'r'), Loader=Loader)

    print('Reading in data')
    collisions = pd.read_csv('data_dft/collisions.csv', low_memory=False)
    casualties = pd.read_csv('data_dft/casualties.csv', low_memory=False)

    # filter to junctions
    print('Filter to Junctions')
    junction_types = params['valid_junction_types']

    mask = collisions.junction_detail.isin(junction_types)
    collisions = collisions.loc[mask, :]

    # pull out all cyclist and pedestrian crash ids
    valid_crash_ids = casualties[
        casualties['casualty_type'].isin(params['valid_casualty_types'])
    ]['accident_index'].unique()

    print(f'Filter to cyclist & pedestrian collisions, {len(valid_crash_ids)} crash IDs in data')

    collisions = collisions[collisions.accident_index.isin(valid_crash_ids)]
    casualties = casualties[casualties.accident_index.isin(valid_crash_ids)]

    print('Recalculate severities and danger metrics')
    print(collisions['year'])
    min_year = min(collisions['year'])
    recalculated_cyclist_severities = recalculate_severity(casualties, 'Cyclist')
    recalculated_pedestrian_severities = recalculate_severity(casualties, 'Pedestrian')

    # # join back to the datasets with severity in it
    collisions = (
        collisions
        .merge(recalculated_cyclist_severities, how='left', on='accident_index')
        .merge(recalculated_pedestrian_severities, how='left', on='accident_index')
    )
    
    collisions['recency_weight'] = collisions.apply(
        lambda row: get_recency_weight(row, min_year), axis=1
    )

    print(collisions.columns)

    collisions.loc[:, 'is_cyclist_collision'] = False
    collisions.loc[:, 'is_Pedestrian_collision'] = False
    collisions.loc[~collisions['max_cyclist_severity'].isnull(), 'is_cyclist_collision'] = True
    collisions.loc[~collisions['max_Pedestrian_severity'].isnull(), 'is_Pedestrian_collision'] = True

    print('Example data')
    print(collisions)

    print('Cyclist collisions per year check')
    print(
        collisions[collisions['is_cyclist_collision']]
        .groupby('year')
        ['accident_index']
        .nunique()
    )

    print('Pedestrian collisions per year check')
    print(
        collisions[collisions['is_Pedestrian_collision']]
        .groupby('year')
        ['accident_index']
        .nunique()
    )

    # output csvs
    print('Output to csv')
    collisions.to_csv('data_dft/pedestrian-and-cyclist-collisions.csv', index=False)


if __name__ == "__main__":
    main()

