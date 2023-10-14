"""
This script is based on notebooks/junctions-graph.ipynb
It builds a graph of London junctions, simplifies this and then creates a dataset for this.
"""
import yaml
import pandas as pd
import numpy as np
import osmnx as ox

from yaml import Loader

# this prevents a lot of future warnings that are coming out of oxmnx
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)


def convert_strings_list(x: str) -> list:
    '''
    Function to convert a list stored in a string to a list.
    '''
    if type(x) == int:
        return [x]
    else:
        return x.strip('][').split(', ')


def combine_names(names) -> list:
    '''
    Takes a list of names, flattens them and returns unique list
    '''
    if type(names) == str:
        return [names]
    
    flat_names = []
    for n in names:
        if type(n) == list:
            for m in n:
                flat_names.append(m)
        else:
            flat_names.append(n)
    
    unique_names = list(set(flat_names))

    return unique_names


def shorten_road_names(name: str) -> str:
    '''
    Shortern elements of road names to save space
    '''
    replacements = {
        'Avenue': 'Ave',
        'Bridge': 'Brg',
        'Gardens': 'Gdns',
        'Place': 'Pl',
        'Road': 'Rd',
        'Street': 'St',
        'Square': 'Sq',
    }
    for k, v in replacements.items():
        name = name.replace(k, v)
    return name


def list_to_string_name(names: list) -> str:
    '''
    Convert list of names for junction to a string
    '''
    names = [name for name in names if (name != '') & (name == name)]
        
    name = '-'.join(names)
    if name == '':
        name = 'Unknown'
    return name


def name_junctions(lower_level_graph, nodes_df: pd.DataFrame) -> pd.DataFrame:
    """
    Create names for junctions using the edge names from graph
    """
    junction_names = (
        ox
        .graph_to_gdfs(lower_level_graph, nodes=False)
        .reset_index()
        [['u', 'name']]
        .fillna('')
    )

    junction_names['name'] = junction_names['name'].apply(combine_names)

    nodes_df = nodes_df.merge(
        junction_names,
        how='left',
        left_on='junction_id',
        right_on='u'
    )

    cluster_names = (
        nodes_df
        .groupby('junction_cluster_id')['name']
        .apply(combine_names)
        .reset_index()
    )

    nodes_df = nodes_df.merge(
        cluster_names,
        how='left',
        on='junction_cluster_id',
        suffixes=['', '_cluster']
    )

    nodes_df['junction_cluster_name'] = nodes_df['name_cluster'].apply(list_to_string_name)

    nodes_df['junction_cluster_name'] = nodes_df['junction_cluster_name'].apply(shorten_road_names)

    nodes_df['name_rank'] = (
        nodes_df
        .groupby(['junction_cluster_name'])['junction_cluster_id']
        .transform('rank', method='dense')
    )

    nodes_df['name_max_rank'] = (
        nodes_df
        .groupby(['junction_cluster_name'])['name_rank']
        .transform('max')
    )

    nodes_df['junction_cluster_name'] = np.where(
        nodes_df['name_max_rank'] == 1,
        nodes_df['junction_cluster_name'],
        nodes_df['junction_cluster_name'] + '-' + nodes_df['name_rank'].astype(int).astype(str)
    )

    nodes_df.drop(columns=['name', 'u', 'name_rank', 'name_cluster'], inplace=True)

    # finally, drop dups
    nodes_df = nodes_df.drop_duplicates()

    return nodes_df


def main():

    # read in data params
    params = yaml.load(open("params.yaml", 'r'), Loader=Loader)

    tolerance = params['tolerance']

    # build initial junctions graph
    print('Building initial junction graph')
    G1 = ox.graph_from_place(
        'Greater London, UK',  # critical to use greater london, the city of London is not included otherwsie!!
        network_type='drive',
        simplify=True,
        clean_periphery=True
    )
    # for testing use:
    # G1 = ox.graph_from_address(
    #     'Greater London, UK',
    #     network_type='drive',
    #     dist=1000
    # )

    # simplify graph using the consolidate_intersections()
    print('Consolidating intersections')
    G2 = ox.consolidate_intersections(
        ox.project_graph(G1),
        tolerance=tolerance,
        rebuild_graph=True,
        dead_ends=True,  # true means we don't filter out dead ends.
        reconnect_edges=True
    )

    # create datafraems from G1 & G2
    df_lower = (
        ox.graph_to_gdfs(
            G1,
            nodes=True,
            edges=False,
            node_geometry=True,
            fill_edge_geometry=False
        )
        .drop(columns=['highway', 'street_count'])
        .reset_index()
        .rename(columns={'y': 'lat', 'x': 'lon', 'osmid': 'osmid_original'})
    )

    df_higher = ox.graph_to_gdfs(
        G2,
        nodes=True,
        edges=False,
        node_geometry=True,
        fill_edge_geometry=False
    )


    # Create hierarchical junction dataframe
    # 
    # This needs to store both the lower level junctions (before simplifying) and the higher level.
    # This is because we want to map collisions to the lower level and then aggregate at the higher level.
    # 
    # For this we need to flatten the df_higher dataframe so we can join the datasets.
    print('Creating junction heirarchy')

    df_higher['osmid_original'] = df_higher['osmid_original'].apply(convert_strings_list)
    df_higher = df_higher.explode('osmid_original')
    df_higher['osmid_original'] = df_higher['osmid_original'].astype(int)

    df_higher = (
        df_higher
        .reset_index()
        .drop(columns=['x', 'y', 'street_count', 'highway', 'lon', 'lat'])
        .rename(columns={'osmid': 'osmid_cluster'})
    )

    # Combine datasets
    df = df_lower.merge(
        df_higher,
        how='inner',
        on='osmid_original',
        suffixes=['_original', '_cluster']
    )

    # calculate lat, lons for clusters
    cluster_coords = (
        df
        .groupby('osmid_cluster')[['lat', 'lon']]
        .mean()
        .reset_index()
        .rename(columns={'lat': 'latitude_cluster', 'lon': 'longitude_cluster'})
    )

    # join in
    df = df.merge(
        cluster_coords,
        how='left',
        on='osmid_cluster'
    )

    # fill nulls with the lower level coordinate when missing
    df['latitude_cluster'] = df['latitude_cluster'].fillna(df['lat'])
    df['longitude_cluster'] = df['longitude_cluster'].fillna(df['lon'])

    # drop some cols and rename some
    df = (
        df
        .drop(
            columns=['geometry_original', 'geometry_cluster']
        )
        .reset_index()
        .rename(
            columns={
                'index': 'junction_index',
                'lat': 'latitude_junction',
                'lon': 'longitude_junction',
                'osmid_original': 'junction_id',
                'osmid_cluster': 'junction_cluster_id'
            }
        )
    )

    # finally, name junctions
    print('Naming junctions')
    df = name_junctions(G1, df)

    print(f'Outputing data: data/junctions-tolerance={tolerance}.csv')
    df.to_csv(f'data/junctions-tolerance={tolerance}.csv', index=False)
    df.to_parquet(f'data/junctions-tolerance={tolerance}.parquet', engine='pyarrow')


if __name__ == "__main__":
    main()

