"""
Provides a uniform way to build argparse Arguments for common command-line
flags that FireSlurm needs.
"""

import argparse
import inspect
from pathlib import Path


def sim_config(parser: argparse.ArgumentParser) -> None:
    """
    Add the --sim-config flag to PARSER.
    """
    parser.add_argument(
        "--sim-config",
        dest="sim_config",
        required=False,
        type=Path,
        help=inspect.cleandoc("""Path to the simulation's configuration
        directory. This will/should include both the FireSim host-side program,
        the FPGA bitstream, and all relevant libraries needed.
        This is the target directory for synchronizing."""),
    )


def run_name(parser: argparse.ArgumentParser) -> None:
    """
    Add the --run-name flag to PARSER.
    """
    parser.add_argument(
        "--run-name",
        dest="run_name",
        required=True,
        type=str,
        help=inspect.cleandoc("""Name to give to this run.
        This log file will be created beneath the provided log_dir."""),
    )


def log_dir(parser: argparse.ArgumentParser) -> None:
    """
    Add the --log-dir flag to PARSER.
    """
    parser.add_argument(
        "--log-dir",
        dest="log_dir",
        required=False,
        type=Path,
        help=inspect.cleandoc("""Desired path for all log files to appear in."""),
    )


def overlay_path(parser: argparse.ArgumentParser) -> None:
    """
    Add the --overlay-path flag to PARSER.
    """
    parser.add_argument(
        "--overlay-path",
        dest="overlay_path",
        required=False,
        type=Path,
        help=inspect.cleandoc("""Path to directory to overlay on top of
        simulation disk image."""),
    )


def sim_img(parser: argparse.ArgumentParser) -> None:
    """
    Add the --sim-img flag to PARSER.
    """
    parser.add_argument(
        "--sim-img",
        dest="sim_img",
        required=False,
        type=Path,
        help=inspect.cleandoc("""Path to the simulation disk image."""),
    )


def sim_prog(parser: argparse.ArgumentParser) -> None:
    """
    Add the --sim-prog flag to PARSER.
    """
    parser.add_argument(
        "--sim-prog",
        dest="sim_prog",
        required=False,
        type=Path,
        help=inspect.cleandoc("""Path to the program to run at the top-level
        by Firesim.
        This should be the combined OpenSBI firmware and Linux kernel program."""),
    )


def cmd(parser: argparse.ArgumentParser) -> None:
    """
    Add support for -- cmd [cmd ...] to PARSER.
    """
    parser.add_argument(
        "cmd",
        nargs="*",
        help=inspect.cleandoc("""Commands & Flags (in shell syntax) to run
        inside Firesim."""),
    )


def verbose(parser: argparse.ArgumentParser) -> None:
    """
    Add the -v/--verbose flag to PARSER.
    """
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbosity",
        action="count",
        default=0,
        help=inspect.cleandoc("""How verbosely to log. This flag can be included
        multiple times to increase the verbosity.
        This will also be passed to Slurm commands to increase the amount they
        log too."""),
    )


def dry_run(parser: argparse.ArgumentParser) -> None:
    """
    Add the -n/--dry-run flag to PARSER.
    """
    parser.add_argument(
        "-n",
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help=inspect.cleandoc("""
        Should all subcommands this program invokes be "dry-run"?
        If set, the sub-commands will do nothing, but will be logged."""),
    )


def partition(parser: argparse.ArgumentParser) -> None:
    """
    Add the -p/--partition flag to PARSER to specify which Slurm partition(s)
    to run on.
    """
    parser.add_argument(
        "-p",
        "--partition",
        dest="slurm_partitions",
        required=False,
        default="firesim",
        type=str,
        help=inspect.cleandoc("""The Slurm partition that this job should run on.
        Like Slurm, this can accept a comma-delimited list of partitions to run
        on. The first partition that is available will run the job.

        NOTE: This is passed through to Slurm DIRECTLY! FireSlurm does NOTHING
        with this flag!"""),
    )


def nodelist(parser: argparse.ArgumentParser) -> None:
    """
    Add the -w/--nodelist flag to PARSER to specify which Slurm nodes in the
    selected Slurm partition should run this program.
    """
    parser.add_argument(
        "-w",
        "--nodelist",
        dest="slurm_nodelist",
        required=False,
        type=str,
        help=inspect.cleandoc("""The Cheese Cluster node in Slurm (*jack) that
        this simulation should be run on. Like Slurm, this is a comma-delimited
        list/range of hosts that are allowed to/should run this job.

        NOTE: This is passed through to Slurm DIRECTLY! FireSlurm does NOTHING
        with this flag!"""),
    )
