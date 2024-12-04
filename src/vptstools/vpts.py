import json
from pathlib import Path
import functools
import multiprocessing
from datetime import datetime
from typing import List, Any

from dataclasses import dataclass
import tempfile

import pandas as pd
from frictionless import validate

from vptstools.odimh5 import ODIMReader, check_vp_odim
from vptstools.vpts_csv import get_vpts_version

NODATA = ""
UNDETECT = "NaN"

DESCRIPTOR_FILENAME = "vpts.resource.json"
CSV_ENCODING = (
    "utf8"  # !! Don't change, only utf-8 is accepted in frictionless resources
)
CSV_FIELD_DELIMITER = ","


def _odim_get_variables(dataset, variable_mapping: dict, quantity: str) -> List[Any]:
    """In a given dataset, find the requested quantity and return a 1d list
    of the values

    'nodata' and 'undetect' are interpreted according to the metadata in the
    'what' group.

    Parameters
    ----------
    dataset : HDF5 group
        HDF5 group
    variable_mapping : dict
        Map the variables names to the dataset ID in the ODIM file
    quantity : str
        Variable name to extract

    Notes
    -----
    In order to handle the 'nodata' and 'undetect', a list overcomes casting as is done
    when using numpy in this case (and the non exsitence of Nan for integer in numpy).
    """
    data_group = variable_mapping[quantity]

    gain = dataset[data_group]["what"].attrs["gain"]
    offset = dataset[data_group]["what"].attrs["offset"]

    nodata_val = dataset[data_group]["what"].attrs["nodata"]
    undetect_val = dataset[data_group]["what"].attrs["undetect"]

    # Apply offset/gain while preserving the original variable datatype
    variable_dtype = dataset[data_group]["data"].dtype
    values = (
        (dataset[data_group]["data"] * gain + offset)
        .astype(variable_dtype)
        .flatten()
        .tolist()
    )
    # use regular list here to have mixed dtypes for the data versus nodata/undetect
    values = [NODATA if value == nodata_val else value for value in values]
    values = [UNDETECT if value == undetect_val else value for value in values]
    return values


@dataclass(frozen=True)
class BirdProfile:
    """Represent ODIM source file

    Data class representing a single input ODIM source file, i.e.
    (https://github.com/adokter/vol2bird/wiki/ODIM-bird-profile-format-specification)
    single datetime, single radar, multiple altitudes with
    variables for each altitude: dd, ff, ...

    This object aims to stay as close as possible to the HDF5 file
    (no data simplification/loss at this stage). Use the `from_odim` method
    as a convenient instantiation.
    """

    identifiers: dict  # {'WMO':'06477', 'NOD':'bewid', 'RAD':'BX41', 'PLC':'Wideumont'}
    datetime: datetime
    what: dict
    where: dict
    how: dict
    levels: List[int]
    variables: dict
    source_file: str = ""

    def __post_init__(self):
        if not isinstance(self.source_file, str):
            raise TypeError(
                f"Source_file {self.source_file} need to be a str representation of a file path."
            )

    def __lt__(self, other):  # Allows sorting by datetime
        return self.datetime < other.datetime

    def __str__(self):
        return f"Bird profile: {self.datetime:%Y-%m-%d %H:%M} - {self.identifiers}"

    def __repr__(self):
        return f"Bird profile: {self.datetime:%Y-%m-%d %H:%M} - {self.identifiers}"

    def to_vp(self, vpts_csv_version):
        """Convert profile data to a CSV

        Parameters
        ----------
        vpts_csv_version : AbstractVptsCsv
            Ruleset with the VPTS CSV ruleset to use, e.g. v1.0

        Notes
        -----
        When 'NaN' or 'NA' values are present inside a column, the object data type
        will be kept. Otherwise the difference between NaN and NA would be lost and
        this overcomes int to float conversion when Nans are available as no int NaN
        is supported by Pandas.
        """
        df = pd.DataFrame(vpts_csv_version.mapping(self), dtype=str)

        df = df.replace(
            {UNDETECT: vpts_csv_version.undetect, NODATA: vpts_csv_version.nodata}
        )

        # sort the data according to sorting rule
        df = (
            df.astype(vpts_csv_version.sort)
            .sort_values(by=list(vpts_csv_version.sort.keys()))
            .astype(str)
        )

        return df

    @classmethod
    def from_odim(cls, source_odim: ODIMReader, source_file=None):
        """Extract BirdProfile information from ODIM with OdimReader

        Parameters
        ----------
        source_odim : ODIMReader
            ODIM file reader interface.
        source_file : str, optional
            URL or path to the source file from which the data were derived.
        """
        dataset1 = source_odim.hdf5["dataset1"]
        variable_mapping = {
            value[f"/dataset1/{key}"]["what"].attrs["quantity"].decode("utf8"): key
            for key, value in dataset1.items()
            if key != "what"
        }
        height_values = _odim_get_variables(dataset1, variable_mapping, quantity="HGHT")

        variable_mapping.pop("HGHT")
        variables = dict()
        for variable in variable_mapping.keys():
            variables[variable] = _odim_get_variables(
                dataset1, variable_mapping, quantity=variable
            )

        # Resolve hdf5 file full path if no source_file is provided by the user
        if not source_file:
            source_file = Path(source_odim.hdf5.filename).name

        return cls(
            datetime=source_odim.root_datetime,
            identifiers=source_odim.root_source,
            what=dict(source_odim.what),
            where=dict(source_odim.where),
            how=dict(source_odim.how),
            levels=[int(height) for height in height_values],
            variables=variables,
            source_file=str(source_file),
        )


def vp(file_path, vpts_csv_version="v1.0", source_file=""):
    """Convert ODIM HDF5 file to a DataFrame

    Parameters
    ----------
    file_path : Path
        File Path of ODIM HDF5
    vpts_csv_version : str, default ""
        Ruleset with the VPTS CSV ruleset to use, e.g. v1.0
    source_file : str | callable
        URL or path to the source file from which the data were derived or
        a callable that converts the file_path to the source_file. See
        https://aloftdata.eu/vpts-csv/#source_file for more information on
        the source file field.


    Examples
    --------
    >>> file_path = Path("bejab_vp_20221111T233000Z_0x9.h5")
    >>> vp(file_path)
    >>> vp(file_path,
    ...    source_file="s3://aloftdata/baltrad/hdf5/2022/11/11/bejab_vp_20221111T233000Z_0x9.h5")  #noqa

    Use file name itself as source_file representation in VP file using a custom
    callable function

    >>> vp(file_path, source_file=lambda x: Path(x).name)
    """
    # Convert file_path into source_file using callable
    if callable(source_file):
        source_file = source_file(file_path)

    with ODIMReader(file_path) as odim_vp:
        check_vp_odim(odim_vp)
        vp = BirdProfile.from_odim(odim_vp, source_file)
    return vp.to_vp(get_vpts_version(vpts_csv_version))


def _convert_to_source(file_path):
    """Return the file name itself from a file path"""
    return Path(file_path).name


def vpts(file_paths, vpts_csv_version="v1.0", source_file=None):
    """Convert set of HDF5 files to a DataFrame all as string

    Parameters
    ----------
    file_paths : Iterable of file paths
        Iterable of ODIM HDF5 file paths
    vpts_csv_version : str
        Ruleset with the VPTS CSV ruleset to use, e.g. v1.0
    source_file : callable, optional
        A callable that converts the file_path to the source_file. When None,
        the file name itself (without parent folder reference) is used.

    Notes
    -----
    Due tot the multiprocessing support, the source_file as a callable can not be
    a anonymous lambda function.

    Examples
    --------
    >>> file_paths = sorted(Path("../data/raw/baltrad/").rglob("*.h5"))
    >>> vpts(file_paths)

    Use file name itself as source_file representation in VP file using a
    custom callable function

    >>> def path_to_source(file_path):
    ...     return Path(file_path).name
    >>> vpts(file_paths, source_file=path_to_source)
    """
    # Use the file nam itself as source_file when no custom callable is provided
    if not source_file:
        source_file = _convert_to_source

    cpu_count = max(multiprocessing.cpu_count() - 1, 1)
    with multiprocessing.Pool(processes=cpu_count) as pool:
        data = pool.map(
            functools.partial(
                vp, vpts_csv_version=vpts_csv_version, source_file=source_file
            ),
            file_paths,
        )

    vpts_ = pd.concat(data)

    # Convert according to defined rule set
    vpts_csv = get_vpts_version(vpts_csv_version)
    vpts_ = (
        vpts_.astype(vpts_csv.sort)
        .sort_values(by=list(vpts_csv.sort.keys()))
        .astype(str)
    )
    return vpts_


def vpts_to_csv(df, file_path):
    """Write VP or VPTS to file

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame with VP or VPTS data
    file_path : Path | str
        File path to store the VPTS file
    """
    # check for str input of Path
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    # create directory if not yet existing
    file_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(file_path, sep=CSV_FIELD_DELIMITER, encoding=CSV_ENCODING, index=False)


def validate_vpts(df, schema_version="v1.0"):
    """Validate VPTS DataFrame against the frictionless data schema and return report

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame as created by the vp or vpts functions
    schema_version : str, v1.0,...
        Version according to a release tag of https://github.com/aloftdata/vpts-csv/tags

    Returns
    -------
    dict
        Frictionless validation report
    """
    tmp_path = Path(tempfile.mkdtemp())
    vpts_file_path = tmp_path / "vpts.csv"
    vpts_to_csv(df, vpts_file_path)
    _write_resource_descriptor(vpts_file_path, schema_version)
    report = validate(tmp_path / DESCRIPTOR_FILENAME)
    return report


def _write_resource_descriptor(vpts_file_path: Path, schema_version="v1.0"):
    """Write a frictionless resource descriptor file

    Parameters
    ----------
    vpts_file_path : pathlib.Path
        File path of the resource (VPTS file) written to disk
    schema_version :
        Version according to a release tag of https://github.com/aloftdata/vpts-csv/tags
    """
    content = {
        "name": "vpts",
        "path": vpts_file_path.name,
        "format": "csv",
        "mediatype": "text/csv",
        "encoding": CSV_ENCODING,
        "dialect": {"delimiter": CSV_FIELD_DELIMITER},
        "schema": f"https://raw.githubusercontent.com/aloftdata/vpts-csv/"
        f"{schema_version}/vpts-csv-table-schema.json",
    }
    vpts_file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(vpts_file_path.parent / DESCRIPTOR_FILENAME, "w") as outfile:
        json.dump(content, outfile, indent=4, sort_keys=True)
