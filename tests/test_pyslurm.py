import pytest


# NOTE: These tests are dependent on their order of appearance in this file!
# You MUST do test_pyslurm_available first!


def test_pyslurm_available():
    try:
        import pyslurm  # noqa: F401
    except Exception:
        pytest.fail("Cannot import pyslurm")


def test_pyslurm_version():
    import pyslurm

    assert pyslurm.version() is not None
