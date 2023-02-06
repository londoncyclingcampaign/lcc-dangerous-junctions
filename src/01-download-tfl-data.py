import re
import yaml
import requests
import pandas as pd

from io import StringIO
from yaml import Loader
from convertbng.util import convert_lonlat


def extract_columns(df: pd.DataFrame, schema: dict) -> pd.DataFrame:
    """
    Extract required columns based on schema + rename columns so consistent
    """
    inverse_schema = {}
    for key, val in schema.items():
        for v in val:
            inverse_schema[v] = key
        
    df = df.rename(columns=inverse_schema)
    columns = schema.keys()
    return df[columns]


def format_name(name: str) -> str:
    """
    format strings to consistent lower case format
    """
    name = name.strip() # strip trailing spaces
    name = name.lower()
    name = name.lstrip('_')  # string underscores infront of col name
    name = re.sub('/', '_or_', name)  # chnage slash to 'or'
    name = re.sub(r'[^\w\s]', '', name)  # remove punctuation
    name = name.replace(' ', '_')  # replace spaces between words w/ underscores
    
    return name


def clean_collision_id(raw_collision_id: str, year: int) -> str:
    """
    Make TfL collision ids match the stats19 ones
    """
    collision_id = str(year)[0:2] + str(raw_collision_id)[-9:]
    collision_id = str(collision_id)
    return collision_id


def format_category(val: str, categories: list) -> str:
    """
    Format category names to be consistent
    """
    val = format_name(val)
    for category in categories:
        if category in val:
            return category
    # return column if no matches found
    print(f'No matches found for: {val}')
    return val
    
    
def format_time(time: str) -> str:
    """
    Format time if in format '0731 (rather than 07:31)
    """
    if time[0] == "'":
        time = f'{time[1:3]}:{time[3:]}'
    
    return time


def create_alias_dict(alias_df, alias_type):
    alias_dict = {}
    alias_df = alias_df[alias_df['type'] == alias_type]
    for alias, consistent_name in alias_df[['alias', 'consistent_name']].values:
        alias_dict[alias] = consistent_name
    
    return alias_dict


def process_yearly_data(links: list, required_cols, aliases) -> pd.DataFrame:
    """
    Loop through TfL  download links, download, format and combine.
    """
    dfs = []

    with requests.Session() as session:
        for link in links:
            print(f'Processing: {link}')
            download = session.get(link)

            n = 0
            cols = ['Unnamed:']
            while len([c for c in cols if 'Unnamed:' in c]) > 0:
                df = pd.read_csv(
                    StringIO(download.content.decode(encoding='utf-8', errors='replace')),
                    encoding='unicode_escape',
                    low_memory=False,
                    skiprows=n
                )
                cols = df.columns
                n += 1
            
            df.columns = [col.strip() for col in df.columns]
            df.rename(columns=aliases, inplace=True)

            df = df[required_cols]

            dfs.append(df)

    combined_df = pd.concat(dfs)
    return combined_df


def main():
    params = yaml.load(open("params.yaml", 'r'), Loader=Loader)

    aliases = pd.read_csv('data/tfl-aliases.csv')

    column_aliases = create_alias_dict(aliases, 'column')
    value_aliases = create_alias_dict(aliases, 'value')

    collision_cols = params['collision_columns']
    casualty_cols = params['casualty_columns']

    collision_links = [link for link in params['data_links'] if 'attendant' in link]
    casualty_links = [link for link in params['data_links'] if 'casualty' in link]

    # ====================== COLLISIONS ===================================== #

    collisions = process_yearly_data(
        collision_links,
        collision_cols,
        column_aliases
    )

    collisions['date'] = pd.to_datetime(
        collisions['date'],
        infer_datetime_format=True,
        dayfirst=True
    )
    collisions['year'] = collisions['date'].dt.year

    collisions['collision_id'] = collisions.apply(
        lambda row: clean_collision_id(row['raw_collision_id'], row['year']), axis=1
    )

    collisions['time'] = collisions['time'].apply(format_time)
    collisions['time'] = pd.to_datetime(collisions['time']).dt.time

    collisions.replace(value_aliases, inplace=True)

    for col in ['borough', 'location']:
        collisions[col] = collisions[col].apply(lambda x: x.upper())

    # convert easting, northings
    collisions['longitude'], collisions['latitude'] = convert_lonlat(
        collisions['easting'],
        collisions['northing']
    )

    print(collisions.head())

    # ====================== CASUALTIES ===================================== #

    casualties = process_yearly_data(
        casualty_links,
        casualty_cols,
        column_aliases
    )

    # join to get the valid collision id from collision data
    casualties = casualties.merge(
        collisions[['raw_collision_id', 'collision_id']],
        how='inner',
        on='raw_collision_id'
    )

    casualties.replace(value_aliases, inplace=True)

    print(casualties.head())

    # output data
    collisions.to_csv('data/collisions.csv', index=False)
    casualties.to_csv('data/casualties.csv', index=False)


if __name__ == "__main__":
    main()
