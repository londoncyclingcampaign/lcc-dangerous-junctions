import yaml
import pandas as pd

from yaml import Loader


def replace_code_with_values(df, schema, table, field):
    return df.replace(
        {
            field: schema.loc[
                (schema["table"] == table) & (schema["field name"] == field),
                ["code/format", "label"],
            ]
            .set_index("code/format")
            .to_dict()["label"]
        }
    )


def main():
    params = yaml.load(open("dft_params.yaml", "r"), Loader=Loader)

    # ====================== SCHEMA ===================================== #

    remote_schema_path = params["base_dft_url"] + params["schema_file_name"] + ".xlsx"
    local_schema_path = f"data_dft/{params['schema_file_name']}.csv"

    try:
        schema = pd.read_csv(local_schema_path)
    except FileNotFoundError:
        schema = pd.read_excel(remote_schema_path)
        schema.to_csv(local_schema_path, index=False)

    # ====================== COLLISIONS ===================================== #

    remote_collision_path = params["base_dft_url"] + params["collision_file_name"]
    local_collision_path = "data_dft/" + params["collision_file_name"].format(
        year="all"
    )

    try:
        collisions = pd.read_csv(local_collision_path)
    except FileNotFoundError:
        collisions = pd.concat(
            [
                pd.read_csv(
                    remote_collision_path.format(year=year),
                    low_memory=False,
                )
                for year in params["dft_data_years"]
            ]
        )
        collisions.to_csv(local_collision_path, index=False)

    collision_cols = params["collision_columns"]

    cleaned_collisions = (
        collisions[collision_cols]
        .pipe(
            replace_code_with_values, schema, "Accident", "local_authority_ons_district"
        )
        .pipe(replace_code_with_values, schema, "Accident", "accident_severity")
        .pipe(replace_code_with_values, schema, "Accident", "junction_detail")
        .assign(
            date=lambda x: pd.to_datetime(x["date"], format="mixed", dayfirst=True),
            year=lambda x: x["date"].dt.year,
        )
    )

    print("Collision example rows:")
    print(cleaned_collisions.head())

    # ====================== CASUALTIES ===================================== #

    remote_casualty_path = params["base_dft_url"] + params["casualty_file_name"]
    local_casualty_path = "data_dft/" + params["casualty_file_name"].format(year="all")

    try:
        casualties = pd.read_csv(local_casualty_path)

    except FileNotFoundError:
        casualties = pd.concat(
            [
                pd.read_csv(
                    remote_casualty_path.format(year=year),
                    low_memory=False,
                )
                for year in params["dft_data_years"]
            ]
        )
        casualties.to_csv(local_casualty_path, index=False)

    casualty_cols = params["casualty_columns"]

    cleaned_casualties = (
        casualties[casualty_cols]
        .pipe(replace_code_with_values, schema, "Casualty", "casualty_class")
        .pipe(replace_code_with_values, schema, "Casualty", "casualty_severity")
        .pipe(replace_code_with_values, schema, "Casualty", "casualty_type")
    )

    print("Casualty example rows:")
    print(cleaned_casualties.head())

    # output data
    cleaned_casualties.to_csv("data_dft/casualties.csv", index=False)
    cleaned_collisions.to_csv("data_dft/collisions.csv", index=False)


if __name__ == "__main__":
    main()
