import tempfile
import shutil
from pathlib import Path
from datetime import date

import click
import s3fs
import pandas as pd

from vptstools.vpts import vpts, vpts_to_csv
from vptstools.s3 import handle_manifest, OdimFilePath

S3_BUCKET = "aloft"  # TODO - use config instead of hardcoded value
S3_BUCKET_CREATION = pd.Timestamp("2022-08-02 00:00:00", tz="UTC")
MANIFEST_URL = f"s3://aloft-inventory/{S3_BUCKET}/{S3_BUCKET}-hdf5-files-inventory"
MANIFEST_HOUR_OF_DAY = "01-00"


@click.command()
@click.option(
    "--modified-days-ago",
    "modified_days_ago",
    default=2,
    type=int,
    help="Range of h5 vp files to include, i.e. files modified between now and N"
         "modified-days-ago. If 0, all h5 files in the bucket will be included.",
)
@click.option(
    "--aws-profile",
    "aws_profile",
    default=None,
    help="(Optionally) AWS profile used to interact with the S3 bucket.",
)
def cli(modified_days_ago, aws_profile):
    """Convert and aggregate h5 vp files to daily/monthly vpts files on S3 bucket

    Check the latest modified h5 vp files on the S3 bucket using an S3 inventory,
    convert those files from ODIM bird profile to the VPTS CSV format and
    upload the generated daily/monthly vpts files to S3.
    """
    if aws_profile:
        storage_options = {"profile": aws_profile}
    else:
        storage_options = dict()
    # Load the S3 manifest of today
    click.echo(f"Load the S3 manifest of {date.today()}.")

    manifest_parent_key = (
        pd.Timestamp.now(tz="utc").date() - pd.Timedelta("1day")
    ).strftime(f"%Y-%m-%dT{MANIFEST_HOUR_OF_DAY}Z")
    s3_url = f"{MANIFEST_URL}/{manifest_parent_key}/manifest.json"  # define manifest of today

    click.echo(f"Extract coverage and days to recreate from manifest {s3_url}.")
    if modified_days_ago == 0:
        modified_days_ago = (pd.Timestamp.now(tz="utc") - S3_BUCKET_CREATION).days + 1
        click.echo(
            f"Recreate the full set of bucket files (files modified since {modified_days_ago}days). "
            f"This will take a while!"
        )

    df_cov, days_to_create_vpts = handle_manifest(
        s3_url,
        modified_days_ago=f"{modified_days_ago}day",
        storage_options=storage_options,
    )

    # Save coverage file to S3 bucket
    click.echo("Save coverage file to S3.")
    df_cov["directory"] = df_cov["directory"].str.join("/")
    df_cov.to_csv(
        f"s3://{S3_BUCKET}/coverage.csv", index=False, storage_options=storage_options
    )

    # CUSTOM - Limit to Belgian stations
    days_to_create_vpts[days_to_create_vpts["directory"].apply(lambda x: x[2] in ["bejab", "bewid"])]

    # Run vpts daily conversion for each radar-day with modified files
    inbo_s3 = s3fs.S3FileSystem(**storage_options)

    click.echo(f"Create {days_to_create_vpts.shape[0]} daily vpts files.")
    for j, daily_vpts in enumerate(days_to_create_vpts["directory"]):

        # Enlist files of the day to rerun (all the given day)
        source, _, radar_code, year, month, day = daily_vpts
        odim_path = OdimFilePath(source, radar_code, "vp", year, month, day)
        odim5_files = inbo_s3.ls(f"{S3_BUCKET}/{odim_path.s3_folder_path_h5}")
        click.echo(f"Create daily vpts file {odim_path.s3_xfile_path_daily_vpts}.")
        # - create tempdir
        temp_folder_path = Path(tempfile.mkdtemp())

        # - download the files of the day
        h5_file_local_paths = []
        for i, file_key in enumerate(odim5_files):
            h5_path = OdimFilePath.from_inventory(file_key)
            h5_local_path = str(temp_folder_path / h5_path.file_name)
            inbo_s3.download(file_key, h5_local_path)
            h5_file_local_paths.append(h5_local_path)

        # - run vpts on all locally downloaded files
        df_vpts = vpts(h5_file_local_paths)

        # - save vpts file locally
        vpts_to_csv(df_vpts, temp_folder_path / odim_path.daily_vpts_file_name)

        # - copy vpts file to S3
        inbo_s3.put(
            str(temp_folder_path / odim_path.daily_vpts_file_name),
            f"{S3_BUCKET}/{odim_path.s3_file_path_daily_vpts}",
        )

        # - remove tempdir with local files
        shutil.rmtree(temp_folder_path)

    click.echo("Finished creating daily vpts files.")

    # Run vpts monthly conversion for each radar-day with modified files
    # TODO - abstract monthly procedure to separate functionality
    months_to_create_vpts = days_to_create_vpts
    months_to_create_vpts["directory"] = months_to_create_vpts["directory"].apply(
        lambda x: x[:-1]
    )  # remove day
    months_to_create_vpts = (
        months_to_create_vpts.groupby("directory").size().reset_index()
    )

    click.echo(f"Create {months_to_create_vpts.shape[0]} monthly vpts files.")
    for j, monthly_vpts in enumerate(months_to_create_vpts["directory"]):
        source, _, radar_code, year, month = monthly_vpts
        odim_path = OdimFilePath(source, radar_code, "vp", year, month, "01")

        click.echo(f"Create monthly vpts file {odim_path.s3_file_path_monthly_vpts}.")
        file_list = inbo_s3.ls(f"{S3_BUCKET}/{odim_path.s3_path_setup('daily')}")
        files_to_concat = sorted(
            [
                daily_vpts
                for daily_vpts in file_list
                if daily_vpts.find(f"{odim_path.year}{odim_path.month}") >= 0
            ]
        )
        # do not parse Nan values, but keep all data as string
        df_month = pd.concat(
            [
                pd.read_csv(
                    f"s3://{file_path}",
                    dtype=str,
                    keep_default_na=False,
                    na_values=None,
                )
                for file_path in files_to_concat
            ]
        )
        df_month.to_csv(
            f"s3://{S3_BUCKET}/{odim_path.s3_file_path_monthly_vpts}",
            index=False,
            storage_options=storage_options,
        )

    click.echo("Finished creating monthly vpts files.")
    click.echo("Finished vpts update procedure.")


if __name__ == "__main__":
    cli()
