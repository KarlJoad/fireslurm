#!/usr/bin/env python3

# fmt: off
#SBATCH --error=slurm-%j.err
# fmt: on

import sys

if sys.version_info[0] < 3:
    raise RuntimeError("This script requires Python version 3!")

import argparse
import logging
import signal
import subprocess
import os
from pathlib import Path
from typing import List, Union
import stat
import inspect

import fireslurm.utils as utils
import fireslurm.validation as validate


logger = logging.getLogger(__name__)


def build_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        # TODO: Write custom usage thingy https://stackoverflow.com/a/75217910
        # Want to use programmatic usage, but want the "-- cmd [cmd ...]" to be generated
        usage="%(prog)s [-h] [-v] [options] sim_config overlay_path sim_img sim_prog log_dir run_log_name -- cmd [cmd ...]",
        description="Run a Firesim simulation",
        epilog="Lovingly made by NCW, Atmn, and KGH.",
        add_help=True,
        # NOTE: color= added by 3.14
        # color=utils.supports_color() and utils.wants_color(),
    )
    # TODO: This litany of positional flags should be replaced by long-arg flags.
    parser.add_argument(
        "sim_config",
        type=Path,
        help=inspect.cleandoc("""Path to the simulation's configuration
        directory. This should include both the FireSim host-side program, the
        FPGA bitstream, and all relevant libraries needed."""),
    )
    parser.add_argument(
        "overlay_path",
        type=Path,
        help=inspect.cleandoc("""Path to directory to overlay on top of
        simulation disk image."""),
    )
    parser.add_argument(
        "sim_img",
        type=Path,
        help=inspect.cleandoc("""Path to the simulation disk image."""),
    )
    parser.add_argument(
        "sim_prog",
        type=Path,
        help=inspect.cleandoc("""Path to the program to run at the top-level
        by Firesim."""),
    )
    parser.add_argument(
        "log_dir",
        type=Path,
        help=inspect.cleandoc("""Desired path for all log files to appear in."""),
    )
    parser.add_argument(
        "run_log_name",
        type=str,
        help=inspect.cleandoc("""Name that this run should be logged as.
        This log file will be created beneath the provided log_dir."""),
    )
    parser.add_argument(
        "cmd",
        nargs="+",
        help=inspect.cleandoc("""Commands & Flags (in shell syntax) to run
        inside Firesim."""),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help=inspect.cleandoc("""
                    How verbosely to log. This flag can be included multiple
                    times to increase the verbosity"""),
    )
    return parser


def validate_sim_config(sim_config: Path) -> bool:
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
            validate.path_is_readable_dir(sim_config),
            validate.path_is_readable_dir(sim_config / "xilinx_vcu118"),
            validate.path_is_executable_file(sim_config / "FireSim-xilinx_vcu118"),
            validate.path_is_readable_file(sim_config / "xilinx_vcu118" / "firesim.bit"),
        ]
    )


def validate_overlay(overlay_path: Path) -> bool:
    """
    Return True if the OVERLAY_PATH is a valid overlay to use with Firesim.
    """
    return validate.path_is_readable_dir(overlay_path)


def validate_sim_img(sim_img: Path) -> bool:
    """
    Return True if the SIM_IMG bare disk image is valid for Firesim & QEMU.
    Return False otherwise.
    """
    return all(
        [
            validate.path_is_readable_file(sim_img),
            # This ".img" check is somewhat brittle, but helps us catch what may
            # potentially be silly errors.
            sim_img.suffix == ".img",
            # TODO: Validate that sim_img is a block-device image
        ]
    )


def validate_sim_prog(sim_prog: Path) -> bool:
    """
    Return True if the SIM_PROG program for Firesim to run as the top-level
    program is in a valid configuration to use.
    """
    return all(
        [
            validate.path_is_readable_file(sim_prog),
            validate.path_is_executable_file(sim_prog),
        ]
    )


def validate_log_dir(log_dir: Path) -> bool:
    """
    Return True if LOG_DIR is a valid logging directory for FireSlurm and
    FireSim.
    Return False otherwise.
    """
    return all(
        [
            validate.path_is_readable_dir(log_dir),
            validate.path_is_writable_dir(log_dir),
        ]
    )


def validate_args(args: argparse.Namespace) -> bool:
    """
    Validate that the comand line arguments, ARGS, are well-formed for the rest
    so the rest of the program can just assume they are valid.
    Return True if all the ARGS are valid.
    """
    return all(
        [
            validate_sim_config(args.sim_config),
            validate_overlay(args.overlay_path),
            validate_sim_img(args.sim_img),
            validate_sim_prog(args.sim_prog),
            validate_log_dir(args.log_dir),
        ]
    )


def write_firesim_sh(overlay_path: Path, cmd: Union[List[str], List[Path]]) -> Path:
    """
    Write the programs/scripts/whatever to run INSIDE the Firesim simulation.
    Returns the path to the "firesim.sh" script.
    """
    logger.debug("Building firesim.sh")
    FIRESIM_SH = "firesim.sh"
    with open(FIRESIM_SH, "w") as f:
        f.write("#!/bin/sh")
    perms = stat.S_IFREG | stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH
    os.chmod(FIRESIM_SH, perms)
    return FIRESIM_SH


def update_log_files(log_dir: Path, log_name: str) -> None:
    """
    Update the log files in LOG_DIR for this Firesim run.
    """
    pass


def flash_fpga(sim_config: Path) -> None:
    """
    Flash the FPGA with the Firesim bitstream in SIM_CONFIG.
    """
    FLASH_CMD = [
        "sudo",
        "/usr/local/bin/firesim-xvsecctl-flash-fpga",
        "0x01",
        "0x00",
        "0x1",
        f"{sim_config}/xilinx_vcu118/firesim.bit",
    ]
    PCIE_PERMS_CMD = [
        "sudo",
        "/usr/local/bin/firesim-change-pcie-perms",
        "0000:01:00:0",
    ]


def overlay_disk_image(overlay_path: Path, sim_img: Path) -> None:
    """
    Overlay the file system tree in OVERLAY_PATH to SIM_IMG.
    """
    pass


def build_firesim_cmd(sim_config: Path, sim_img: Path, sim_prog: Path, log_dir: Path) -> List[str]:
    """
    Return a command string to run the Firesim simulation.
    NOTE: This is the command that the host runs to run the Firesim simulation.
    """
    return []


def main() -> None:
    parser = build_argparse()
    args = parser.parse_args()
    logging.basicConfig(
        format="%(levelname)s:%(name)s:%(funcName)s:%(lineno)d:%(message)s",
        level=logging.DEBUG if args.verbose > 0 else logging.INFO,
    )
    logger.debug(f"Running with {args=!s}")
    logger.debug(f"Command to run INSIDE Firesim: {args.cmd=!s}")

    if validate_args(args):
        logger.debug(f"{args=!s} are valid!")
    else:
        logger.error(f"{args=!s} are INVALID! ABORTING!")

    # XXX: Writing firesim.sh MUST come before doing the disk image overlay!
    # If you don't do it, then the simulation will NOT have a /firesim.sh script
    # to run when it finishes booting.
    write_firesim_sh(args.overlay_path, args.cmd)

    update_log_files(args.log_dir, args.run_log_name)

    logger.info("Begin infrasetup")
    # We must block SIGINT during this process because this is a "delicate"
    # operation. Getting interrupted can leave the FPGA in such a borked state
    # that we have to reflash Firesim's controllers to the FPGA.
    logger.info("Begin ignoring SIGINT! C-c will not work!")
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    flash_fpga(args.sim_config)
    overlay_disk_image(args.overlay_path, args.sim_img)

    logger.info("End ignoring SIGINT! C-c will now work!")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    logger.info("Finished infrasetup")

    fsim_cmd = build_firesim_cmd(
        args.sim_config,
        args.sim_img,
        args.sim_prog,
        args.log_dir,
    )
    (old_ld_library_path, _) = utils.extend_path("LD_LIBRARY_PATH", ["HOME/yukon/firesim"])
    logger.warning("Changing SIGINT key to C-]!")
    os.system("stty intr ^]")
    # subprocess.run(fsim_cmd)

    # Restore LD_LIBRARY_PATH to its previous value
    os.environ["LD_LIBRARY_PATH"] = old_ld_library_path
    os.system("stty intr ^c")
    logger.warning("SIGINT key changed back to to C-c!")


if __name__ == "__main__":
    main()
