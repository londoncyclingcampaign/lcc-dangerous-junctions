"""
This script is based on notebooks/junctions-graph.ipynb
It builds a graph of London junctions, simplifies this and then creates a dataset for this.
"""
import yaml
import pandas as pd
import osmnx as ox

from yaml import Loader

# this prevents a lot of future warnings that are coming out of oxmnx
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)


def convert_strings_list(x):
    '''
    Function to convert a list stored in a string to a list.
    '''
    if type(x) == int:
        return [x]
    else:
        return x.strip('][').split(', ')


def main():

    # read in data params
    params = yaml.load(open("params.yaml", 'r'), Loader=Loader)

    # tolerance = params['tolerance']

    # build initial junctions graph
    print('Building initial junction graph')
    G1 = ox.graph_from_place(
        'London, UK',
        network_type='drive',
        simplify=True,
        clean_periphery=True
    )

    # loop through tolerance options.
    for tolerance in [20, 22]:
        print(f'tolerance={tolerance}')

        # simplify graph using the consolidate_intersections()
        print('Consolidating intersections')
        G2 = ox.consolidate_intersections(
            ox.project_graph(G1),
            tolerance=tolerance,
            rebuild_graph=True,
            dead_ends=False,
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
            .drop(columns=['highway', 'street_count', 'ref'])
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
            .drop(columns=['x', 'y', 'street_count', 'highway', 'lon', 'lat', 'ref'])
            .rename(columns={'osmid': 'osmid_cluster'})
        )


        # Combine datasets
        df = df_lower.merge(
            df_higher,
            how='left',
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

        print(f'Outputing data: data/junctions-tolerance={tolerance}.csv')
        df.to_csv(f'data/junctions-tolerance={tolerance}.csv', index=False)


if __name__ == "__main__":
    main()

