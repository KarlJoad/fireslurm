from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Union, NewType
import uuid
import sys
from abc import ABC
import logging
import os

import fireslurm.validation as validate


logger = logging.getLogger(__name__)


FireSlurmID = NewType("FireSlurmID", uuid.UUID)
# The default value is the NIL UUID (uuid.NIL). The UUID with all 128 bits set
# to 0. Python 3.14+ has this defined as a special value. We must construct it
# ourselved on older Pythons.
if sys.version_info < (3, 14):
    DEFAULT_FIRESLURM_ID: FireSlurmID = uuid.UUID("00000000-0000-0000-0000-000000000000")
else:
    DEFAULT_FIRESLURM_ID: FireSlurmID = uuid.NIL


def _run_uuid() -> FireSlurmID:
    """
    Return a UUID for FireSlurm runs.

    On Python 3.14+, this is a UUID v7. On Python <3.14, this is a UUID v4.
    """
    f = None
    if sys.version_info < (3, 14):
        f = uuid.uuid4()
    else:
        f = uuid.uuid7()
    assert f is not None, "You must have a UUID function to generate run IDs"
    return f


@dataclass(frozen=True)
class FireSlurmConfig:
    """
    The basic configuration that FireSlurm needs to know about for generally
    running.
    """

    overlay_path: Path
    """Path to directory to overlay on top of simulation disk image."""

    sim_config: Path
    """
    Path to the configuration directory of the simulation.

    This should include the FPGA bitstream and the simulation driver.
    """

    sim_img: Path
    """Path to the simulation disk image."""

    sim_prog: Path
    """
    Path to the program to run at the top-level by Firesim.
    This should be the combined OpenSBI firmware and Linux kernel program.
    """

    log_dir: Path
    """Desired path for all log files to appear in."""

    partitions: List[str]
    """The Slurm partitions FireSlurm should run on."""

    def partitions_flag(self) -> str:
        """
        Format the partitions field for Slurm CLI use.
        """
        return ",".join(self.partitions)

    nodelist: List[str]
    """
    The set of nodes inside of the partition this Slurm job should be allowed
    to run on.
    """

    def nodelist_flag(self) -> str:
        """
        Format the nodelist field for Slurm CLI use.
        """
        return ",".join(self.nodelist)

    verbosity: int = 0
    """
    How verbosely to log, higher values produce more logs.
    """

    def verbose(self) -> bool:
        """
        Return True if there is any verbosity enabled. False otherwise.
        """
        return self.verbosity > 0

    def verbose_flag(self) -> str:
        """
        Return a verbose flag string with this configuration's specified
        verbosity. If verbosity is 0, then the empty string is returned.

        A verbose flag string looks like "-v".
        """
        return "-" + "v" * self.verbosity if self.verbosity > 0 else ""

    dry_run: bool = False
    """
    Should the run actually do anything or just print what would happen?
    """

    _run_id: FireSlurmID = field(default_factory=_run_uuid)
    """
    The ID of this FireSlurm configuration/run.

    This should be treated as opaque and is not meant for users to construct or
    manipulate. This is used by FireSlurm internally to track where everything
    is happening across multiple FireSlurm runs across time.
    """

    def __post_init__(self):
        """
        Validate that the FireSlurm configuration that was constructed is valid.
        """
        assert self.validate_sim_config(), "Simulator config directory invalid"
        assert self.validate_overlay(), "Overlay directory invalid"

        assert self.validate_sim_img(), "Simulation disk image invalid"
        assert self.validate_sim_prog(), "Simulation program (kernel) invalid"
        assert self.validate_log_dir(), "Log directory is invalid"

    def validate_sim_config(self) -> bool:
        """
        Return True if the SIM_CONFIG is a valid directory to use with fireslurm.
        Return False otherwise.

        A valid simulation configuration directory is one with the following
        hierarchy:
        stable
        ├── description.txt
        ├── FireSim-xilinx_vcu118
        ├── *.so.*
        └── xilinx_vcu118
           ├── firesim.bit
           ├── firesim.mcs
           ├── firesim_secondary.mcs
           └── metadata
        """
        return all(
            [
                validate.path_is_readable_dir(self.sim_config),
                validate.path_is_readable_dir(self.sim_config / "xilinx_vcu118"),
                validate.path_is_executable_file(self.sim_config / "FireSim-xilinx_vcu118"),
                validate.path_is_readable_file(self.sim_config / "xilinx_vcu118" / "firesim.bit"),
            ]
        )

    def validate_overlay(self) -> bool:
        """
        Return True if the OVERLAY_PATH is a valid overlay to use with Firesim.
        """
        return validate.path_is_readable_dir(self.overlay_path)

    def validate_sim_img(self) -> bool:
        """
        Return True if the SIM_IMG bare disk image is valid for Firesim & QEMU.
        Return False otherwise.
        """
        return all(
            [
                validate.path_is_readable_file(self.sim_img),
                # This ".img" check is somewhat brittle, but helps us catch what may
                # potentially be silly errors.
                self.sim_img.suffix == ".img",
                # TODO: Validate that sim_img is a block-device image
            ]
        )

    def validate_sim_prog(self) -> bool:
        """
        Return True if the SIM_PROG program for Firesim to run as the top-level
        program is in a valid configuration to use.
        """
        return all(
            [
                validate.path_is_readable_file(self.sim_prog),
                validate.path_is_executable_file(self.sim_prog),
            ]
        )

    def validate_log_dir(self) -> bool:
        """
        Return True if LOG_DIR is a valid logging directory for FireSlurm and
        FireSim.
        Return False otherwise.
        """
        return all(
            [
                validate.path_is_readable_dir(self.log_dir),
                validate.path_is_writable_dir(self.log_dir),
            ]
        )


@dataclass(frozen=True)
class SyncConfig(FireSlurmConfig):
    infrasetup_target: Path = None
    """
    The directory that "firesim infrasetup" targeted.
    """

    config_name: str = ""
    """
    The name to give to this configuration.
    """

    description: str = ""
    """
    The description to give to this configuration.
    This can be free-form text. It is NOT used by FireSlurm at all and intended
    for users to give themselves a descriptive reminder of what that particular
    configuration was built/configured as.
    """


@dataclass(frozen=True)
class SlurmJobConfig(ABC, FireSlurmConfig):
    """
    An abstract base class (ABC) to make having multiple types of Slurm
    interactions more DRY.
    """

    run_name: str = ""
    """
    The name that this run should have in Slurm.
    """

    cmd: Union[str, List[any], None] = None
    """
    The command the batch job should execute INSIDE the FireSim simulation.

    If None is specified, then this is considered an interactive job and users
    will be connected to the terminal presented by FireSim for interactive work.
    """

    def is_interactive(self):
        """
        Return True if this run configuration is an interactive job, i.e. a
        simulation job that should behave like a normal command line (be
        interactive).
        Returns False if this is a scripted job.
        """
        return self.cmd is None or self.cmd == ""

    print_start: int = 0
    """
    Clock cycle the FireSim simulation should start printing at.
    """

    slurm_output: Path = Path("slurm-log/%j.out")
    """
    File path where Slurm's sbatch's STDOUT should go.
    """

    slurm_error: Path = Path("slurm-log/%j.err")
    """
    File path where Slurm's sbatch's STDERR should go.
    """

    def validate_run_name(self) -> bool:
        """
        Return True if RUN_NAME is a valid name for a run.
        Return False otherwise.

        In particular, this function ensures that runs hav enames that are valid for
        POSIX file systems. Some special characters are disallowed, spaces are
        discouraged, etc.
        """
        logger.debug(f"Validating that {self.run_name=!r} is a valid POSIX file name")
        # Empty names and the bare path separator "/" are invalid run names.
        if not self.run_name or os.pathsep in self.run_name:
            return False
        # NOTE: The use of regexps here to perform a "POSIX match" on the log name
        # is not technically correct, nor robust. But it is good enough for our
        # limited Fireslurm usage.
        import re

        if re.fullmatch(r"[a-zA-Z0-9.\-_]+", self.run_name):
            return True
        else:
            return False

    def __post_init__(self):
        assert self.validate_run_name(), "Run name is invalid"


@dataclass(frozen=True)
class RunConfig(SlurmJobConfig):
    """
    FireSlurm configuration required to run a FireSim simulation through Slurm
    with "srun".
    """

    @classmethod
    def from_batch_config(cls: "RunConfig", config: "BatchConfig") -> "RunConfig":
        """
        Convert the provided batch configuration to one suitable for running.

        NOTE: The originally-provided config is NOT altered.
        """
        # Batch configs are strictly more strict than run configs. Batch configs
        # must always provide a command/script to run, since they must execute
        # without input from the user.
        return RunConfig(**asdict(config))


@dataclass(frozen=True)
class BatchConfig(SlurmJobConfig):
    """
    FireSlurm configuration required to run a FireSim simulation through Slurm
    with "sbatch".
    """

    def __post_init__(self):
        assert not self.is_interactive(), "Batch runs must have a command"

    # Sometimes it is useful to turn a RunConfig into a BatchConfig, especially
    # if you are using FireSlurm as a library and driving it with your own
    # Python code yourself.
    @classmethod
    def from_run_config(cls: "BatchConfig", config: RunConfig) -> "BatchConfig":
        """
        Attempt to convert the provided run configuration one suitable for
        batching.

        NOTE: The originally-provided config is NOT altered.
        """
        if config.cmd is not None and config.cmd != "":
            return BatchConfig(**asdict(config))
        else:
            raise ValueError(f"{config=!s} must provide a cmd!")
