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
import os
from pathlib import Path
from typing import List
import stat
import textwrap
from datetime import datetime
import subprocess
import shutil
import time
import pty

import fireslurm.utils as utils
import fireslurm.validation as validate


logger = logging.getLogger(__name__)


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


def validate_run_name(run_name: str) -> bool:
    """
    Return True if RUN_NAME is a valid name for a run.
    Return False otherwise.

    In particular, this function ensures that runs hav enames that are valid for
    POSIX file systems. Some special characters are disallowed, spaces are
    discouraged, etc.
    """
    logger.debug(f"Validating that {run_name=!r} is a valid POSIX file name")
    # Empty names and the bare path separator "/" are invalid run names.
    if not run_name or os.pathsep in run_name:
        return False
    # NOTE: The use of regexps here to perform a "POSIX match" on the log name
    # is not technically correct, nor robust. But it is good enough for our
    # limited Fireslurm usage.
    import re

    if re.fullmatch(r"[a-zA-Z0-9.\-_]+", run_name):
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
            validate_run_name(args.run_name),
        ]
    )


def write_firesim_sh(
    dest_dir: Path,
    cmd: str,
) -> Path:
    """
    Write the programs/scripts/whatever to run INSIDE the Firesim simulation.
    Returns the path to the "firesim.sh" script.
    """
    logger.debug("Building firesim.sh")
    FIRESIM_SH = dest_dir / "firesim.sh"
    perms = stat.S_IFREG | stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH

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
    bitstream = sim_config / "xilinx_vcu118" / "firesim.bit"
    if not bitstream.exists():
        raise FileNotFoundError(f"{bitstream.resolve()} does not exist!")

    # XXX: The flash FPGA command is dangerous! It will silently fail if you
    # do not give it a bitstream to flash. If you give it something wrong, a
    # directory for instance, xvsecctl (and this script) will still have an
    # exit code of 0 and say it configured the FPGA successfully!
    FLASH_CMD = [
        "sudo",
        "firesim-xvsecctl-flash-fpga",
        "0x01",
        "0x00",
        "0x1",
        bitstream.resolve(),
    ]
    PCIE_PERMS_CMD = [
        "sudo",
        "firesim-change-pcie-perms",
        "0000:01:00:0",
    ]

    logger.debug(f"Flashing the FPGA. {FLASH_CMD=!s}")
    if not utils.dry_run:
        proc = subprocess.run(FLASH_CMD, check=True, capture_output=True, text=True)
        logger.info(f"FPGA flashing STDOUT: {proc.stdout}")
        logger.debug(f"FPGA flashing STDERR: {proc.stdout}")

    logger.debug(f"Changing PCIe FPGA Permissions. {PCIE_PERMS_CMD=!s}")
    if not utils.dry_run:
        proc = subprocess.run(PCIE_PERMS_CMD, check=True, capture_output=True, text=True)
        logger.info(f"FPGA permissions STDOUT: {proc.stdout}")
        logger.debug(f"FPGA permissions STDERR: {proc.stdout}")


def overlay_disk_image(overlay_path: Path, sim_img: Path) -> None:
    """
    Overlay the file system tree in OVERLAY_PATH to SIM_IMG.
    """
    logger.info(f"Overlaying contents of {overlay_path} onto {sim_img}")

    # XXX: mountpoint is relative to CWD of the script!
    mountpoint = Path("mountpoint")
    mountpoint.mkdir(exist_ok=True)
    with utils.mount_img(sim_img.resolve(), mountpoint.resolve()):
        shutil.copytree(overlay_path.resolve(), mountpoint.resolve(), dirs_exist_ok=True)


def infrasetup(sim_config: Path, overlay_path: Path, sim_img: Path) -> None:
    """
    Perform the same steps as "firesim infrasetup".

    This flashes the FPGA with the design's bitstream stored in SIM_CONFIG and
    overlays all of the files that the user provided in OVERLAY_PATH to the
    SIM_IMG.
    """
    logger.info("Begin infrasetup")
    # We must block SIGINT during this process because this is a "delicate"
    # operation. Getting interrupted can leave the FPGA in such a borked state
    # that we have to reflash Firesim's controllers to the FPGA.
    with utils.block_sigint():
        flash_fpga(sim_config)
        overlay_disk_image(overlay_path, sim_img)

        # XXX: We need a little bit of grace time between flashing the FPGA,
        # overlaying the disk image; and actually launching the simulation.
        # The exact reasons for this sleep's necessity are unknown right now, but
        # removing it causes simulations that do not start.
        sleep_time = 1
        logger.info(f"Sleeping for {sleep_time} seconds to let things stabilize")
        time.sleep(sleep_time)
    logger.info("Finished infrasetup")


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


def run_simulation(
    sim_config: Path,
    sim_img: Path,
    sim_prog: Path,
    log_dir: Path,
    print_start: int,
) -> None:
    fsim_cmd = build_firesim_cmd(
        sim_config,
        sim_img,
        sim_prog,
        log_dir,
        print_start,
    )

    with utils.change_sigint_key(sys.stdout.isatty()):
        # Create a pseudo-terminal
        (master, slave) = pty.openpty()

        # XXX: You must change the SIGINT keychord with os.system BEFORE
        # you extend $LD_LIBRARY_PATH! If you don't, you will end up with
        # glibc errors from libc and the dynamic loader!
        # stty: .../libc.so.6: version `GLIBC_2.38' not found (required by stty)
        (old_ld_library_path, _) = utils.extend_path(
            "LD_LIBRARY_PATH",
            [
                sim_config.resolve(),
            ],
        )
        # tty.intr = "^]"
        # All of this hoopla is to make uartlog go to both stdout and a file.
        uartlog = log_dir / "uartlog"
        logger.info(f"Setting simulator's uartlog to {uartlog.resolve()}")
        with (
            open(uartlog, "w") as uartlog,
            subprocess.Popen(
                fsim_cmd,
                stdout=slave,
                stderr=slave,
                stdin=slave,
                start_new_session=True,
                # text=True,
                bufsize=0,
            ) as proc,
        ):
            # Close slave in parent process
            os.close(slave)

            # Read from master
            while True:
                try:
                    output = os.read(master, 1024)
                    if not output:
                        break
                    line = output.decode()
                    n_line = line.replace("\r\n", "\n")
                    print(n_line, end="")
                    uartlog.write(n_line)
                except OSError:
                    break

            os.close(master)

            proc.wait()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, fsim_cmd)

        # Restore LD_LIBRARY_PATH to its previous value
        # XXX: Similarly, we must restore $LD_LIBRARY_PATH BEFORE we call stty!
        os.environ["LD_LIBRARY_PATH"] = old_ld_library_path


def run(
    run_name: str,
    sim_config: Path,
    overlay_path: Path,
    sim_img: Path,
    sim_prog: Path,
    log_dir: Path,
    print_start: int,
    cmd: str,
    **kwargs,
) -> None:
    logger.debug(f"Command to run INSIDE Firesim: {cmd=!s}")

    # If the user did not provide a command to us, then we assume that this
    # invocation was meant for an interactive run of FireSim and the user will
    # be connected to the prompt immediately. They are entirely responsible for
    # handling the simulation at this point.
    interactive_run = cmd is None or cmd == ""

    mountpoint = Path("mountpoint")
    mountpoint.mkdir(exist_ok=True)

    # If the user did not provide us with a command, then they want an
    # interactive simulation, which means we need to clean up the disk image.
    # We must remove /firesim.sh, since that is what is executed by FireSim's
    # boot process. If this is a non-interactive job, then we install the script
    # to /firesim.sh.
    if interactive_run:
        logger.warning(
            "You did not provide a command to use in firesim.sh. Proceeding with INTERACTIVE simulation!"
        )
        with utils.mount_img(sim_img.resolve(), mountpoint.resolve()):
            old_firesim_sh = mountpoint / "firesim.sh"
            old_firesim_sh.unlink(missing_ok=True)
            del old_firesim_sh
    else:
        logger.info(
            "You provided a command to use in firesim.sh. Building firesim.sh for automatic execution."
        )
        firesim_sh = write_firesim_sh(sim_config, cmd)
        logger.debug(f"Overlaying {firesim_sh=!s} to {mountpoint=!s}")
        with utils.mount_img(sim_img.resolve(), mountpoint.resolve()):
            shutil.copy(firesim_sh.resolve(), mountpoint.resolve())

    log_dir_latest = update_log_files(log_dir, run_name)

    infrasetup(sim_config, overlay_path, sim_img)
    run_simulation(sim_config, sim_img, sim_prog, log_dir_latest, print_start)
