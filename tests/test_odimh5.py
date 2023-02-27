import pytest

from vptstools.odimh5 import ODIMReader


def test_open_and_expose_hdf5(path_with_sample_odimh5):
    """ODIMReader can open a file, and then expose a hdf5 attribute"""
    odim = ODIMReader(path_with_sample_odimh5)
    assert hasattr(odim, "hdf5")


def test_with_statement(path_with_sample_odimh5):
    """ODIMReader also works with the 'with' statement"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        assert hasattr(odim, "hdf5")


def test_root_date_str(path_with_sample_odimh5):
    """The root_date_str property can be used to get the root date"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        assert odim.root_date_str == "20170214"


def test_root_datetime(path_with_sample_odimh5):
    """Root datetime is correctly parsed from h5"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        dt = odim.root_datetime

        assert dt.year == 2017
        assert dt.month == 2
        assert dt.day == 14
        assert dt.hour == 0
        assert dt.minute == 0
        assert dt.second == 16
        assert dt.microsecond == 0
        assert dt.utcoffset().total_seconds() == 0  # in UTC


def test_root_time_str(path_with_sample_odimh5):
    """The root_time_str property can be used to get the root time"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        assert odim.root_time_str == "000016"


def test_root_source_str(path_with_sample_odimh5):
    """The root_source_str property can be used to get the root source as a string"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        assert (
            odim.root_source_str
            == "WMO:06477,RAD:BX41,PLC:Wideumont,NOD:bewid,CTY:605,CMT:VolumeScanZ"
        )


def test_root_object_str(path_with_sample_odimh5):
    """The root_object_str property can be used to get the root object as a string"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        assert odim.root_object_str == "PVOL"


def test_root_source_dict(path_with_sample_odimh5):
    """The root_source property can be used to get the root source as a dict"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        assert odim.root_source == {
            "WMO": "06477",
            "RAD": "BX41",
            "PLC": "Wideumont",
            "NOD": "bewid",
            "CTY": "605",
            "CMT": "VolumeScanZ",
        }


def test_close(path_with_sample_odimh5):
    """There's a close method, HDF5 file cannot be accessed after use"""
    odim = ODIMReader(path_with_sample_odimh5)
    assert odim.hdf5.mode == "r"
    odim.close()
    with pytest.raises(ValueError):
        odim.hdf5.mode


def test_datasets(path_with_sample_odimh5):
    """Correct dataset names provided by ODIM are interpreted"""
    odim = ODIMReader(path_with_sample_odimh5)

    datasets = odim.dataset_names
    assert len(datasets) == 11
    assert "dataset1" in datasets
    assert "dataset11" in datasets
    assert not "dataset12" in datasets


def test_how(path_with_sample_odimh5):
    """metadata 'what' attributes are extracted correctly"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        assert odim.how == {
            'beamwidth': 1.0, 'endepochs': 1487030428, 'highprf': 600, 'lowprf': 0,
            'software': 'RAINBOW 5.42.9', 'startepochs': 1487030681,
            'system': 'GEMA500', 'wavelength': 5.25
        }


def test_what(path_with_sample_odimh5):
    """metadata 'what' attributes are extracted correctly"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        assert odim.what == {
            'date': '20170214', 'object': 'PVOL',
            'source': 'WMO:06477,RAD:BX41,PLC:Wideumont,NOD:bewid,CTY:605,CMT:VolumeScanZ',
            'time': '000016', 'version': 'H5rad 2.2'
        }


def test_where(path_with_sample_odimh5):
    """metadata 'what' attributes are extracted correctly"""
    with ODIMReader(path_with_sample_odimh5) as odim:
        assert odim.where == {'height': 590.0, 'lat': 49.9143, 'lon': 5.5056}

