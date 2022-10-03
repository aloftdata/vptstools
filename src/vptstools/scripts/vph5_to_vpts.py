import csv
import glob
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Any

import click
from vptstools.odimh5 import ODIMReader

# Return codes (0 = success)
EXIT_INVALID_SOURCE_FILE = 1
EXIT_NO_SOURCE_DATA = 2
EXIT_INCONSISTENT_METADATA = 3

DESCRIPTOR_FILENAME = "datapackage.json"
CSV_FILENAME = "vpts.csv"
CSV_ENCODING = "utf8"  # !! Don't change, only utf-8 is accepted in data packages
CSV_FIELD_DELIMITER = ","


class InvalidSourceODIM(Exception):
    pass


@dataclass
class Level:
    height: float  # Coded as a 64-bit float in HDF5 file
    variables: dict = field(default_factory=dict)

    def __lt__(self, other):  # Allows sorting by height
        return self.height < other.height


# Data class representing a single input source file
# (=https://github.com/adokter/vol2bird/wiki/ODIM-bird-profile-format-specification)
# =single datetime, single radar, multiple altitudes,
# usual variables for each altitude: dd, ff, ...
# This object aims to stay as close as possible to the HDF5 file
# (no data simplification/loss at this stage)
@dataclass
class Profile:
    # From what.source,
    # example: {'WMO':'06477', 'NOD':'bewid', 'RAD':'BX41', 'PLC':'Wideumont'}
    radar_identifiers: dict
    datetime: datetime
    levels: List[Level] = field(default_factory=list)

    def __lt__(self, other):  # Allows sorting by datetime
        return self.datetime < other.datetime

    def to_table(self, prepare_for_csv=True):
        """Return a list of dicts representing the content of the profile,
        such as::

            [
                { datetime: x, height: 0.0, ff: 8.23, ... },
                { datetime: x, height: 200.0, ff: 5.23, ...}
            ]

        The list is sorted by altitude. The datetime is obviously identical for all
        entries. If prepare_for_csv is True, data is transformed to fit the final
        CSV format (data types, ...)
        """
        rows = []

        for level in self.levels:
            rows.append(
                {"datetime": self.datetime, "height": level.height, **level.variables}
            )

        if prepare_for_csv:
            for i, row in enumerate(rows):
                rows[i]["datetime"] = datetime_to_proper8601(row["datetime"])
                rows[i]["height"] = int(row["height"])

        return rows

    @classmethod
    def make_from_odim(cls, source_odim: ODIMReader):
        dataset1 = source_odim.hdf5["dataset1"]
        height_values = get_values(dataset1, quantity="HGHT")

        variables_to_load = (
            {"name": "dens", "convert_to_bool": False},
            {"name": "ff", "convert_to_bool": False},
            {"name": "dd", "convert_to_bool": False},
            {"name": "eta", "convert_to_bool": False},
            {"name": "sd_vvp", "convert_to_bool": False},
            {"name": "DBZH", "convert_to_bool": False},
            {"name": "dbz", "convert_to_bool": False},
            {"name": "u", "convert_to_bool": False},
            {"name": "v", "convert_to_bool": False},
            {"name": "gap", "convert_to_bool": True},
            {"name": "w", "convert_to_bool": False},
            {"name": "n_dbz", "convert_to_bool": False},
            {"name": "n", "convert_to_bool": False},
            {"name": "n_all", "convert_to_bool": False},
            {"name": "n_dbz_all", "convert_to_bool": False},
        )

        levels = []
        for i, height in enumerate(height_values):
            levels.append(
                Level(
                    height=height,
                    variables={
                        k["name"]: get_values(
                            dataset1,
                            quantity=k["name"],
                            convert_to_bool=k["convert_to_bool"],
                        )[i]
                        for k in variables_to_load
                    },
                )
            )

        return cls(
            datetime=source_odim.root_datetime,
            radar_identifiers=source_odim.root_source,
            levels=sorted(levels),
        )


def check_source_odim(source_odim: ODIMReader) -> None:
    if not {"what", "how", "where"}.issubset(source_odim.hdf5.keys()):
        raise InvalidSourceODIM(
            "No hdf5 ODIM format: File does not contain what/how/where "
            "group information."
        )
    if source_odim.root_object_str != "VP":
        raise InvalidSourceODIM(
            f"Incorrect what.object value: expected VP, "
            f"found {source_odim.root_object_str}"
        )


def get_values(dataset, quantity: str, convert_to_bool: bool = False) -> List[Any]:
    """In a given dataset, find the requested quantity and return a 1d list
    of the values

    'nodata' and 'undetect' are interpreted according to the metadata in the
    'what' group if convert_to_bool is true, 1 will be converted to True and
    0 to False
    """
    for data_group in dataset:
        if dataset[data_group]["what"].attrs["quantity"].decode("utf8") == quantity:
            nodata_val = dataset[data_group]["what"].attrs["nodata"]
            undetect_val = dataset[data_group]["what"].attrs["undetect"]

            values = [entry[0] for entry in dataset[data_group]["data"]]
            values = ["nodata" if value == nodata_val else value for value in values]
            values = [
                "undetect" if value == undetect_val else value for value in values
            ]

            if convert_to_bool:
                values = [True if value == 1 else False for value in values]

            return values


def table_to_frictionless_csv(full_data_table, file_path_output_csv):
    keys = full_data_table[0].keys()

    # Last round of processing: boolean values must be converted to an equivalent
    # string, otherwise the CSV module will save them Capitalized, while the
    # frictionless specs asks for lowercase.
    for entry in full_data_table:
        for key in entry:
            if entry[key] is True:
                entry[key] = "true"
            if entry[key] is False:
                entry[key] = "false"

    with open(file_path_output_csv, "w", newline="", encoding=CSV_ENCODING) as output_file:
        fc = csv.DictWriter(output_file, fieldnames=keys, delimiter=CSV_FIELD_DELIMITER)
        fc.writeheader()
        fc.writerows(full_data_table)


def datetime_to_proper8601(
    d,
):
    # See https://stackoverflow.com/questions/19654578/python-utc-datetime-objects-iso-
    # format-doesnt-include-z-zulu-or-zero-offset
    return str(d).replace("+00:00", "Z")


def write_descriptor(folder_path_output: Path, full_data_table, source_metadata):
    content = {
        "radar": {
            "identifiers": source_metadata[
                "radar_identifiers"
            ]  # TODO: decide and docmuent what to do with that (in VPTS)
        },
        "temporal": {
            "start": datetime_to_proper8601(full_data_table[0]["datetime"]),
            "end": datetime_to_proper8601(full_data_table[-1]["datetime"]),
        },
        "resources": [
            {
                "name": "VPTS data",
                "path": CSV_FILENAME,
                "dialect": {"delimiter": CSV_FIELD_DELIMITER},
                "schema": {"fields": []},
            }
        ],
    }

    with open(folder_path_output / DESCRIPTOR_FILENAME, "w") as outfile:
        json.dump(content, outfile, indent=4, sort_keys=True)


def save_to_vpts(full_data_table, folder_path_output: Path, source_metadata: dict):
    if not folder_path_output.exists():
        folder_path_output.mkdir()
    table_to_frictionless_csv(
        full_data_table, output_csv_path=folder_path_output / CSV_FILENAME
    )
    write_descriptor(folder_path_output, full_data_table, source_metadata)


@click.command()
@click.argument("ODIM_hdf5_profiles")
@click.option("-o", "--output-dir-path", default="vpts_out")
def cli(odim_hdf5_profiles, output_dir_path):
    """This tool aggregate/convert a bunch of ODIM hdf5 profiles files to a
    single vpts data package"""
    # Open all ODIM files
    click.echo("Opening all the source ODIM files...", nl=False)
    odims = [ODIMReader(path) for path in glob.glob(odim_hdf5_profiles, recursive=True)]
    click.echo("Done")

    if not odims:
        click.echo(
            f"No source data file found, is the supplied "
            f"pattern ({odim_hdf5_profiles}) correct?"
        )
        sys.exit(EXIT_NO_SOURCE_DATA)

    # Individual checks for each of them
    click.echo("Individual checks on all source files...", nl=False)
    for source_odim in odims:
        try:
            check_source_odim(source_odim)
        except InvalidSourceODIM as e:
            click.echo(f"Invalid ODIM source file: {e}")
            sys.exit(EXIT_INVALID_SOURCE_FILE)
    click.echo("Done")

    click.echo("Building and sorting profiles...", nl=False)
    # Profiles will be sorted by datetimes, and (in each) levels by height
    profiles = sorted([Profile.make_from_odim(odim) for odim in odims])
    click.echo("Done")

    click.echo("Checking consistency of input files...", nl=False)
    # Extract global (to all profiles) metadata, and return an error if inconsistent
    global_metadata = {}  # Shared between all profiles
    # Check all profile refer to the same radar:
    if all(
        profile.radar_identifiers == profiles[0].radar_identifiers
        for profile in profiles
    ):
        global_metadata["radar_identifiers"] = profiles[0].radar_identifiers
    else:
        click.echo("Inconsistent radar identifiers in the source odim files!")
        sys.exit(EXIT_INCONSISTENT_METADATA)
    click.echo("Done")

    click.echo("Aggregating data...", nl=False)
    # Aggregate the tables for each profile to a single one
    full_data_table = []
    for profile in profiles:
        table = profile.to_table()
        for row in table:
            full_data_table.append((row))
    click.echo("Done")

    click.echo("Saving to vpts...", nl=False)
    save_to_vpts(
        full_data_table, output_dir=output_dir_path, source_metadata=global_metadata
    )
    click.echo("Done")


if __name__ == "__main__":
    cli(
        [
            "/Users/nicolas_noe/denmark_vp_20131229_short/dkbor_vp_*",
            "-o",
            "/Users/nicolas_noe/vpts_out",
        ]
    )
    # cli(['--help'])

# TODO: print progress during execution (+progress bar)
# TODO: CSV dialect: explicitly configure + express in datapackage.json
# (already done for field separator)
# TODO: Write a full integration test (takes a few ODIM and check the end result)
# TODO: VPTS: replace vol2bird example (+table schema) by something more up-to-date
# TODO: Put more metadata (radar, ...) in datapackage.json
# TODO: The standard allows temporal gap, but no height gap. Make sure all input
# ODIM files have the same altitudes?
