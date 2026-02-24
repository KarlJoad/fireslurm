from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Union


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

    nodelist: List[str]
    """
    The set of nodes inside of the partition this Slurm job should be allowed
    to run on.
    """

    verbosity: int = 0
    """
    How verbosely to log, higher values produce more logs.
    """

    dry_run: bool = False
    """
    Should the run actually do anything or just print what would happen?
    """


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
class RunConfig(FireSlurmConfig):
    """
    FireSlurm configuration required to run a FireSim simulation through Slurm
    with "srun".
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
class BatchConfig(FireSlurmConfig):
    """
    FireSlurm configuration required to run a FireSim simulation through Slurm
    with "sbatch".
    """

    run_name: str = ""
    """
    The name that this run should have in Slurm.
    """

    cmd: Union[str, List[any]] = ""
    """
    The command the batch job should execute INSIDE the FireSim simulation.
    """

    slurm_output: Path = Path("slurm-log/%j.out")
    """
    File path where Slurm's sbatch's STDOUT should go.
    """

    slurm_error: Path = Path("slurm-log/%j.err")
    """
    File path where Slurm's sbatch's STDERR should go.
    """

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
