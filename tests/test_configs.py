import pytest

import fireslurm.config as configs


@pytest.fixture(scope="session")
def fireslurm_layout(tmp_path_factory):
    test_layout = tmp_path_factory.mktemp("fireslurm-test")
    overlay = test_layout / "overlay"
    overlay.mkdir()
    configs = test_layout / "configs"
    configs.mkdir()
    sim_config = "latest"
    test_dir = {
        "overlay_path": overlay,
        "config_dir": configs,
        "sim_config": sim_config,
        "sim_img": test_layout / "root.img",
        "sim_prog": test_layout / "kernel.bin",
        "log_dir": test_layout / "logs",
        "results_dir": test_layout / "results",
    }
    return test_dir


def test_cmd_convert(fireslurm_layout):
    cfg = configs.RunConfig(
        partitions=["none"],
        nodelist=["none"],
        cmd="echo from srun; ls -lah",
        skip_validation=True,
        **fireslurm_layout,
    )

    assert cfg.cmd_script() == "echo from srun; ls -lah"
