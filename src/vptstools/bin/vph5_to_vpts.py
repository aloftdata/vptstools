import os
import tempfile
from functools import partial
import shutil
from pathlib import Path
from datetime import date

import boto3
import click
from dotenv import load_dotenv
import s3fs
import pandas as pd

from vptstools.vpts import vpts, vpts_to_csv
from vptstools.s3 import handle_manifest, OdimFilePath, extract_daily_group_from_path
from vptstools.bin.click_exception import catch_all_exceptions, report_click_exception_to_sns

# Load environmental variables from file in dev
# (load_dotenv doesn't override existing environment variables)
load_dotenv()

S3_BUCKET = os.environ.get("DESTINATION_BUCKET", "inbo-aloft-uat-eu-west-1-default")
INVENTORY_BUCKET = os.environ.get("INVENTORY_BUCKET", "inbo-aloft-uat-eu-west-1-inventory")
AWS_SNS_TOPIC = os.environ.get("SNS_TOPIC")
AWS_PROFILE = os.environ.get("AWS_PROFILE", None)
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")

MANIFEST_URL = f"s3://{INVENTORY_BUCKET}/{S3_BUCKET}/{S3_BUCKET}-hdf5-files-inventory"
S3_BUCKET_CREATION = pd.Timestamp("2022-08-02 00:00:00", tz="UTC")
MANIFEST_HOUR_OF_DAY = "01-00"


# Prepare SNS report handler
sns_report_exception = partial(report_click_exception_to_sns,
                               aws_sns_topic=AWS_SNS_TOPIC,
                               subject="Conversion from HDF5 files to daily/monthly VPTS files failed.",
                               profile_name=AWS_PROFILE,
                               region_name=AWS_REGION
                               )


@click.command(cls=catch_all_exceptions(click.Command, handler=sns_report_exception))  # Add SNS-reporting on exception
@click.option(
    "--modified-days-ago",
    "modified_days_ago",
    default=2,
    type=int,
    help="Range of HDF5 VP files to include, i.e. files modified between now and N"
    "modified-days-ago. If 0, all HDF5 files in the bucket will be included.",
)
@click.option(
    "--path-s3-folder",
    "path_s3_folder",
    type=str,
    help="Apply the conversion to VPTS to all files within a S3 sub-folders instead "
         "of using the modified date of the files. This option does not use the inventory files."
)
def cli(modified_days_ago, path_s3_folder=None):
    """Convert and aggregate HDF5 VP files to daily and monthly VPTS CSV files on S3 bucket

    Check the latest modified
    `ODIM HDF5 bird VP profile <https://github.com/adokter/vol2bird/wiki/ODIM-bird-profile-format-specification>`_  on the
    Aloft S3 bucket (as generated by `vol2bird <https://github.com/adokter/vol2bird>`_ and transferred using the
    :py:mod:`vpts.bin.transfer_baltrad` CLI routine). Using an
    `s3 inventory bucket <https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-inventory.html>`_, check which
    HDF5 files were recently added and convert those files from ODIM bird profile to the
    `VPTS CSV format <https://github.com/enram/vpts-csv>`_. Finally, upload the generated daily/monthly VPTS files to S3.

    When using the `path_s3_folder` option, the modified date is not used, but a recursive search within the given s3
    path is applied to define the daily/monthly files to recreate.
    E.g. `vph5_to_vpts --path-s3-folder uva/hdf5/nldhl/2019` or
    `vph5_to_vpts --path-s3-folder baltrad/hdf5/bejab/2022/10`.

    Besides, while scanning the S3 inventory to define the files to convert,
    the CLI routine creates the ``coverage.csv`` file and uploads it to the bucket.

    Configuration is loaded from the following environmental variables:

    - ``DESTINATION_BUCKET``: AWS S3 bucket to read and write data to
    - ``INVENTORY_BUCKET``: AWS S3 bucket configured as `s3 inventory bucket <https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-inventory.html>`_ for the S3_BUCKET.
    - ``SNS_TOPIC``: AWS SNS topic to report when routine fails
    - ``AWS_REGION``: AWS region where the SNS alerting is defined
    - ``AWS_PROFILE``: AWS profile (mainly useful for local development when working with multiple AWS profiles)
    """
    if AWS_PROFILE:
        storage_options = {"profile": AWS_PROFILE}
        boto3_options = {"profile_name": AWS_PROFILE}
    else:
        storage_options = dict()
        boto3_options = dict()

    if path_s3_folder:
        click.echo(f"Applying the vpts conversion to all files within {path_s3_folder}. "
                   f"Ignoring the modified date of the files.")

        inbo_s3 = s3fs.S3FileSystem(**storage_options)
        odim5_files = inbo_s3.glob(f"{S3_BUCKET}/{path_s3_folder}/**/*.h5")

        days_to_create_vpts = (
            pd.DataFrame(odim5_files, columns=["file"])
            .set_index("file")
            .groupby(extract_daily_group_from_path).size().reset_index()
            .rename(
                columns={
                    "index": "directory",
                    0: "file_count",
                }
            )
        )

    else:
        # Load the S3 manifest of today
        click.echo(f"Load the S3 manifest of {date.today()} to rerun only files modified "
                   f"since {modified_days_ago} days ago.")

        manifest_parent_key = (
            pd.Timestamp.now(tz="utc").date() - pd.Timedelta("1day")
        ).strftime(f"%Y-%m-%dT{MANIFEST_HOUR_OF_DAY}Z")
        # define manifest of today
        s3_url = f"{MANIFEST_URL}/{manifest_parent_key}/manifest.json"

        click.echo(f"Extract coverage and days to recreate from manifest {s3_url}.")
        if modified_days_ago == 0:
            modified_days_ago = (pd.Timestamp.now(tz="utc") - S3_BUCKET_CREATION).days + 1
            click.echo(
                f"Recreate the full set of bucket files (files "
                f"modified since {modified_days_ago}days). "
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

    # Run VPTS daily conversion for each radar-day with modified files
    inbo_s3 = s3fs.S3FileSystem(**storage_options)
    # PATCH TO OVERCOME RECURSIVE s3fs in wrapped context
    session = boto3.Session(**boto3_options)
    s3_client = session.client("s3")

    click.echo(f"Create {days_to_create_vpts.shape[0]} daily VPTS files.")
    for j, daily_vpts in enumerate(days_to_create_vpts["directory"]):
        try:
            # Enlist files of the day to rerun (all the given day)
            source, _, radar_code, year, month, day = daily_vpts
            odim_path = OdimFilePath(source, radar_code, "vp", year, month, day)
            odim5_files = inbo_s3.ls(f"{S3_BUCKET}/{odim_path.s3_folder_path_h5}")
            click.echo(f"Create daily VPTS file {odim_path.s3_file_path_daily_vpts}.")
            # - create tempdir
            temp_folder_path = Path(tempfile.mkdtemp())

            # - download the files of the day
            h5_file_local_paths = []
            for i, file_key in enumerate(odim5_files):
                h5_path = OdimFilePath.from_s3fs_enlisting(file_key)
                h5_local_path = str(temp_folder_path / h5_path.file_name)
                # inbo_s3.get_file(file_key, h5_local_path)
                # s3f3 fails in wrapped moto environment; fall back to boto3
                s3_client.download_file(
                    S3_BUCKET,
                    f"{h5_path.s3_folder_path_h5}/{h5_path.file_name}",
                    h5_local_path,
                )
                h5_file_local_paths.append(h5_local_path)

            # - run VPTS on all locally downloaded files
            df_vpts = vpts(h5_file_local_paths)

            # - save VPTS file locally
            vpts_to_csv(df_vpts, temp_folder_path / odim_path.daily_vpts_file_name)

            # - copy VPTS file to S3
            inbo_s3.put(
                str(temp_folder_path / odim_path.daily_vpts_file_name),
                f"{S3_BUCKET}/{odim_path.s3_file_path_daily_vpts}",
            )

            # - remove tempdir with local files
            shutil.rmtree(temp_folder_path)
        except Exception as exc:
            click.echo(f"[WARNING] - During conversion from HDF5 files of {source}/{radar_code} at "
                       f"{year}-{month}-{day} to daily VPTS file, the following error occurred: {exc}.")

    click.echo("Finished creating daily VPTS files.")

    # Run VPTS monthly conversion for each radar-day with modified files
    # TODO - abstract monthly procedure to separate functionality
    months_to_create_vpts = days_to_create_vpts
    months_to_create_vpts["directory"] = months_to_create_vpts["directory"].apply(
        lambda x: x[:-1]
    )  # remove day
    months_to_create_vpts = (
        months_to_create_vpts.groupby("directory").size().reset_index()
    )

    click.echo(f"Create {months_to_create_vpts.shape[0]} monthly VPTS files.")
    for j, monthly_vpts in enumerate(months_to_create_vpts["directory"]):
        try:
            source, _, radar_code, year, month = monthly_vpts
            odim_path = OdimFilePath(source, radar_code, "vp", year, month, "01")

            click.echo(f"Create monthly VPTS file {odim_path.s3_file_path_monthly_vpts}.")
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
        except Exception as exc:
            click.echo(f"[WARNING] - During conversion from HDF5 files of {source}/{radar_code} at "
                       f"{year}-{month}-{day} to monthly VPTS file, the following error occurred: {exc}.")

    click.echo("Finished creating monthly VPTS files.")
    click.echo("Finished VPTS update procedure.")


if __name__ == "__main__":
    cli()
