#!/usr/bin/env python3

"""
Run a FireSim simulation.

This program sets up FireSim and runs it. This involves:
  1. Copying files to a configuration directory.
  2. Overlaying custom binaries into the FireSim disk image.
  3. Flashing the FPGA.
  4. Running the top-level FireSim simulation, which connects to the FPGA, does
     all the host-side simulation (disks, networking, etc.), along with the
     logging and assertion handling.

NOTE: This script does ***NOT*** run inside the simulation!
"""

# fmt: off
#SBATCH --error=slurm-%j.err
# fmt: on

import sys

if sys.version_info[0] < 3:
    raise RuntimeError("This script requires Python version 3!")

import argparse
import logging
import signal
import os
from pathlib import Path
from typing import List, Union
import stat
import inspect
import textwrap
from datetime import datetime
import subprocess
import shutil
import time
# import stty  # Comes from 3rd party

import fireslurm.utils as utils
import fireslurm.validation as validate


logger = logging.getLogger(__name__)


def build_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        # TODO: Write custom usage thingy https://stackoverflow.com/a/75217910
        # Want to use programmatic usage, but want the "-- cmd [cmd ...]" to be generated
        description="Run a Firesim simulation",
        epilog="Lovingly made by NCW, Atmn, and KGH.",
        add_help=True,
        # NOTE: color= added by 3.14
        # color=utils.supports_color() and utils.wants_color(),
    )
    # TODO: This litany of positional flags should be replaced by long-arg flags.
    parser.add_argument(
        "--sim-config",
        dest="sim_config",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Path to the simulation's configuration
        directory. This should include both the FireSim host-side program, the
        FPGA bitstream, and all relevant libraries needed."""),
    )
    parser.add_argument(
        "--overlay-path",
        dest="overlay_path",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Path to directory to overlay on top of
        simulation disk image."""),
    )
    parser.add_argument(
        "--sim-img",
        dest="sim_img",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Path to the simulation disk image."""),
    )
    parser.add_argument(
        "--sim-prog",
        dest="sim_prog",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Path to the program to run at the top-level
        by Firesim.
        This should be the combined OpenSBI firmware and Linux kernel program."""),
    )
    parser.add_argument(
        "--log-dir",
        dest="log_dir",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Desired path for all log files to appear in."""),
    )
    parser.add_argument(
        "--run-log-name",
        dest="run_log_name",
        required=True,
        type=str,
        help=inspect.cleandoc("""Name that this run should be logged as.
        This log file will be created beneath the provided log_dir."""),
    )
    parser.add_argument(
        "-p",
        "--print-start",
        dest="print_start",
        action="store",
        default=-1,
        help=inspect.cleandoc("""Clock cycle to begin emitting trace printing
        from the core."""),
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
        dest="verbose",
        action="count",
        default=0,
        help=inspect.cleandoc("""
                    How verbosely to log. This flag can be included multiple
                    times to increase the verbosity"""),
    )
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


def validate_run_log_name(run_log_name: str) -> bool:
    """
    Return True if RUN_LOG_NAME is a valid name for a run.
    Return False otherwise.

    In particular, this function ensures that runs hav enames that are valid for
    POSIX file systems. Some special characters are disallowed, spaces are
    discouraged, etc.
    """
    logger.debug(f"Validating that {run_log_name=!r} is a valid POSIX file name")
    # Empty names and the bare path separator "/" are invalid run names.
    if not run_log_name or os.pathsep in run_log_name:
        return False
    # NOTE: The use of regexps here to perform a "POSIX match" on the log name
    # is not technically correct, nor robust. But it is good enough for our
    # limited Fireslurm usage.
    import re

    if re.fullmatch(r"[a-zA-Z0-9.\-_]+", run_log_name):
        return True
    else:
        return False


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
            validate_run_log_name(args.run_log_name),
        ]
    )


def write_firesim_sh(overlay_path: Path, cmd: Union[List[str], List[Path]]) -> Path:
    """
    Write the programs/scripts/whatever to run INSIDE the Firesim simulation.
    Returns the path to the "firesim.sh" script.
    """
    logger.debug("Building firesim.sh")
    FIRESIM_SH = overlay_path / "firesim.sh"
    perms = stat.S_IFREG | stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH
    cmd = " ".join(cmd)
    logger.debug(f"Command to run as seen by firesim.sh: {cmd=!r}")
    contents = textwrap.dedent(f"""\
    #!/bin/sh
    set -x
    sleep 1
    cat \"/bin/config-$(uname -r)\"

    firesim-start-trigger
    {cmd}
    firesim-end-trigger

    poweroff
    """)
    logger.debug(f"Writing Firesim init script to {FIRESIM_SH}")
    with open(FIRESIM_SH, "w") as f:
        f.write(contents)
    os.chmod(FIRESIM_SH, perms)
    return FIRESIM_SH


def update_log_files(log_dir: Path, log_name: str) -> Path:
    """
    Update the log files in LOG_DIR for this Firesim run.
    Return the path to the latest log directory.
    """
    logger.debug("Updating log files for current run")
    if not log_dir.exists():
        log_dir.mkdir(parents=True, exist_ok=True)

    # Create a new log file
    dt = datetime.now()
    log_name = log_name + dt.strftime("%Y-%m-%d%H%M%S")
    current_run_log = log_dir / log_name
    current_run_log.mkdir(exist_ok=False)

    # Remove the previous "latest" run, because we are about to do a new run
    # If latest did not exist before, then we don't need to do anything.
    latest_log = log_dir / "latest"
    try:
        os.remove(latest_log)
    except FileNotFoundError as e:
        logger.info(f"{e} {latest_log}. Not removing.")

    # Register the now-current run as the latest log
    os.symlink(src=current_run_log, dst=latest_log)
    logger.info(f"Marked {current_run_log} as latest in {log_dir}")
    return latest_log


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
    logger.debug(f"Flashing the FPGA. {FLASH_CMD=!s}")
    utils.run_cmd(FLASH_CMD)
    logger.debug(f"Changing PCIe FPGA Permissions. {PCIE_PERMS_CMD=!s}")
    utils.run_cmd(PCIE_PERMS_CMD)


def overlay_disk_image(overlay_path: Path, sim_img: Path) -> None:
    """
    Overlay the file system tree in OVERLAY_PATH to SIM_IMG.
    """
    logger.info(f"Overlaying contents of {overlay_path} onto {sim_img}")
    assert (overlay_path / "firesim.sh").exists(), (
        "Firesim.sh script must be made before overlaying disk image"
    )
    # XXX: mountpoint is relative to CWD of the script!
    mountpoint = Path("mountpoint")
    mountpoint.mkdir(exist_ok=True)
    with utils.mount_img(sim_img.resolve(), mountpoint.resolve()):
        shutil.copytree(overlay_path.resolve(), mountpoint.resolve(), dirs_exist_ok=True)


def build_firesim_cmd(
    sim_config: Path, sim_img: Path, sim_prog: Path, log_dir: Path, print_start: int
) -> List[str]:
    """
    Return a command string to run the Firesim simulation.
    NOTE: This is the command that the host runs to run the Firesim simulation.
    """
    cmd = [
        "sudo",
        f"{sim_config.resolve()}/FireSim-xilinx_vcu118",
        "+permissive",
        f"+blkdev0={sim_img.resolve()}",
        f"+blkdev-log0={log_dir.resolve()}/blkdev-log0",
        # XXX: +permissive-off MUST be followed by the binary to run!
        "+permissive-off",
        f"+prog0={sim_prog.resolve()}",
        f"+dwarf-file-name={sim_prog.resolve()}-dwarf",
        # "+blkdev1=${HOME}/yukon/yukon-br0-yukon-br.img",
        # "+tracefile=TRACEFILE",
        # "+trace-select=3",
        # "+trace-start=ffffffff00008013",
        # "+trace-end=ffffffff00010013",
        # "+trace-output-format=0",
        "+autocounter-readrate=100000000",
        f"+autocounter-filename-base={log_dir.resolve()}/AUTOCOUNTERFILE",
        f"+print-start={print_start}",
        "+print-end=-1",
        # This NIC information is mandatory, even if it is not used
        "+macaddr0=00:12:6D:00:00:02",
        "+niclog0=niclog0",
        "+linklatency0=6405",
        "+netbw0=200",
        "+shmemportname0=default",
        "+domain=0x0000",
        "+bus=0x01",
        "+device=0x00",
        "+function=0x0",
        "+bar=0x0",
        "+pci-vendor=0x10ee",
        "+pci-device=0x903f",
        "+disable-asserts",
    ]
    logger.debug(f"Firesim command to run on host: {cmd=!s}")
    return cmd


def main() -> None:
    parser = build_argparse()
    args = parser.parse_args()
    utils.dry_run = args.dry_run
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

    log_dir_latest = update_log_files(args.log_dir, args.run_log_name)

    logger.info("Begin infrasetup")
    # We must block SIGINT during this process because this is a "delicate"
    # operation. Getting interrupted can leave the FPGA in such a borked state
    # that we have to reflash Firesim's controllers to the FPGA.
    logger.info("Begin ignoring SIGINT! C-c will not work!")
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    flash_fpga(args.sim_config)
    overlay_disk_image(args.overlay_path, args.sim_img)

    # XXX: We need a little bit of grace time between flashing the FPGA,
    # overlaying the disk image; and actually launching the simulation.
    # The exact reasons for this sleep's necessity are unknown right now, but
    # removing it causes simulations that do not start.
    sleep_time = 1
    logger.info(f"Sleeping for {sleep_time} seconds to let things stabilize")
    time.sleep(sleep_time)

    logger.info("End ignoring SIGINT! C-c will now work!")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    logger.info("Finished infrasetup")

    fsim_cmd = build_firesim_cmd(
        args.sim_config,
        args.sim_img,
        args.sim_prog,
        args.log_dir,
        args.print_start,
    )

    # tty = stty.Stty(fd=0)
    logger.warning("Changing SIGINT key to C-]!")
    os.system("stty intr ^]")
    # XXX: You must change the SIGINT keychord with os.system BEFORE
    # you extend $LD_LIBRARY_PATH! If you don't, you will end up with
    # glibc errors from libc and the dynamic loader!
    # stty: .../libc.so.6: version `GLIBC_2.38' not found (required by stty)
    (old_ld_library_path, _) = utils.extend_path(
        "LD_LIBRARY_PATH",
        [
            args.sim_config.resolve(),
        ],
    )
    # tty.intr = "^]"
    # All of this hoopla is to make uartlog go to both stdout and a file.
    uartlog = log_dir_latest / "uartlog"
    with (
        open(uartlog, "w") as uartlog,
        subprocess.Popen(
            fsim_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            bufsize=1,
        ) as proc,
    ):
        for line in proc.stdout:
            n_line = line.replace("\r\n", "\n")
            sys.stdout.write(n_line)
            uartlog.write(n_line)
        # Raise this error, which matches what subprocess.run(check=True) would
        # do.
        if proc.returncode != 0:
            raise subprocess.CalledProcessError

    # Restore LD_LIBRARY_PATH to its previous value
    # XXX: Similarly, we must restore $LD_LIBRARY_PATH BEFORE we call stty!
    os.environ["LD_LIBRARY_PATH"] = old_ld_library_path
    # tty.intr = "^c"
    os.system("stty intr ^c")
    logger.warning("SIGINT key changed back to to C-c!")


if __name__ == "__main__":
    main()
