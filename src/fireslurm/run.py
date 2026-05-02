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

import sys

if sys.version_info[0] < 3:
    raise RuntimeError("This script requires Python version 3!")

import logging
import os
from pathlib import Path
from typing import List
import stat
import textwrap
from datetime import datetime
import pty

from fireslurm.config import RunConfig
import fireslurm.utils as utils
from fireslurm.slurm import JobInfo


logger = logging.getLogger(__name__)


def write_firesim_sh(
    dest_dir: Path,
    cmd: str,
) -> Path:
    """
    Write the programs/scripts/whatever to run INSIDE the Firesim simulation.
    Returns the path to the "firesim.sh" script.
    """
    logger.debug("Building firesim.sh")
    FIRESIM_SH = (dest_dir / "firesim.sh").resolve()
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
    os.symlink(src=current_run_log.resolve(), dst=latest_log.resolve())
    logger.info(f"Marked {current_run_log.resolve()} as latest in {log_dir}")
    return latest_log


def flash_fpga(sim_config: Path) -> List[str]:
    """
    Flash the FPGA with the Firesim bitstream in SIM_CONFIG.
    """
    bitstream = sim_config / "xilinx_vcu118" / "firesim.bit"
    if not bitstream.exists():
        raise FileNotFoundError(f"{bitstream.resolve()} does not exist!")

    flash_queue = []
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

    flash_queue.append(
        textwrap.dedent(f"""\
    echo 'Flashing the FPGA. {FLASH_CMD=!s}'
    {" ".join(map(str, FLASH_CMD))}
    """)
    )

    flash_queue.append(
        textwrap.dedent(f"""\
    echo 'Changing PCIe FPGA Permissions. {PCIE_PERMS_CMD=!s}'
    {" ".join(map(str, PCIE_PERMS_CMD))}
    """)
    )
    return flash_queue


def overlay_disk_image(overlay_path: Path, sim_img: Path) -> List[str]:
    """
    Overlay the file system tree in OVERLAY_PATH to SIM_IMG.
    """
    overlay_queue = []
    with utils.mount_img(sim_img.resolve(), overlay_queue) as mountpoint:
        overlay_queue.append(
            textwrap.dedent(f"""\
        echo "Overlaying contents of {overlay_path} onto {sim_img}"
        cp -r "{overlay_path.resolve()!s}" "${mountpoint!s}"
        """)
        )
    return overlay_queue


def infrasetup(config: RunConfig) -> List[str]:
    """
    Perform the same steps as "firesim infrasetup".

    This flashes the FPGA with the design's bitstream stored in SIM_CONFIG and
    overlays all of the files that the user provided in OVERLAY_PATH to the
    SIM_IMG.
    """
    logger.info("Begin infrasetup")
    infrasetup_queue = []
    # We must block SIGINT during this process because this is a "delicate"
    # operation. Getting interrupted can leave the FPGA in such a borked state
    # that we have to reflash Firesim's controllers to the FPGA.
    with utils.block_sigint():
        infrasetup_queue += flash_fpga(config.sim_config)
        infrasetup_queue += overlay_disk_image(config.overlay_path, config.sim_img)

        # XXX: We need a little bit of grace time between flashing the FPGA,
        # overlaying the disk image; and actually launching the simulation.
        # The exact reasons for this sleep's necessity are unknown right now, but
        # removing it causes simulations that do not start.
        sleep_time = 1  # In seconds
        infrasetup_queue.append(
            textwrap.dedent(f"""\
        echo "Sleeping for {sleep_time} seconds to let things stabilize"
        sleep {sleep_time!s}
        """)
        )
    logger.debug("\n".join(infrasetup_queue))
    logger.info("Finished infrasetup")
    return infrasetup_queue


def build_firesim_cmd(
    config: RunConfig,
    sim_log_dir: Path,
) -> List[str]:
    """
    Return a command string to run the Firesim simulation.
    NOTE: This is the command that the host runs to run the Firesim simulation.
    """
    cmd = [
        "sudo",
        f"{config.sim_config.resolve()}/FireSim-xilinx_vcu118",
        "+permissive",
        f"+blkdev0={config.sim_img.resolve()}",
        f"+blkdev-log0={config.log_dir.resolve()}/blkdev-log0",
        # XXX: +permissive-off MUST be followed by the binary to run!
        "+permissive-off",
        f"+prog0={config.sim_prog.resolve()}",
        f"+dwarf-file-name={config.sim_prog.resolve()}-dwarf",
        # "+blkdev1=${HOME}/yukon/yukon-br0-yukon-br.img",
        # "+tracefile=TRACEFILE",
        # "+trace-select=3",
        # "+trace-start=ffffffff00008013",
        # "+trace-end=ffffffff00010013",
        # "+trace-output-format=0",
        "+autocounter-readrate=100000000",
        f"+autocounter-filename-base={config.log_dir.resolve()}/AUTOCOUNTERFILE",
        f"+print-start={config.print_start!s}",
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
    return [" ".join(cmd)]


def run_simulation(
    config: RunConfig,
    sim_log_dir: Path,
) -> List[str]:
    """
    The log directory is the directory where THIS simulation run's logs will go.
    """
    run_queue = []

    fsim_cmd = build_firesim_cmd(config, sim_log_dir)
    uartlog = sim_log_dir / "uartlog"

    # FIXME: When jobs are submitted with sbatch, the terminal's output is also
    # going to the slurm --output file. We can just redirect STDOUT to /dev/null
    # if batch was the cause for this.
    with (
        utils.change_sigint_key(run_queue),
        utils.change_path(
            "LD_LIBRARY_PATH",
            [
                config.sim_config.resolve(),
            ],
            run_queue,
        ),
    ):
        run_queue.append(
            textwrap.dedent(f"""\
        echo "Setting simulator's uartlog to {uartlog.resolve()}"
        script --command "{" ".join(fsim_cmd)!s}" "{uartlog.resolve()!s}"
        """)
        )
    return run_queue


def build_run_tasks(config: RunConfig) -> List[str]:
    logger.debug(f"Command to run INSIDE Firesim: {config.cmd=!s}")

    # If the user did not provide a command to us, then we assume that this
    # invocation was meant for an interactive run of FireSim and the user will
    # be connected to the prompt immediately. They are entirely responsible for
    # handling the simulation at this point.
    interactive_run = config.is_interactive()
    logger.info(f"Running this job as interactive?: {interactive_run}")

    run_queue = [textwrap.dedent("#!/usr/bin/env bash\n")]

    # If the user did not provide us with a command, then they want an
    # interactive simulation, which means we need to clean up the disk image.
    # We must remove /firesim.sh, since that is what is executed by FireSim's
    # boot process. If this is a non-interactive job, then we install the script
    # to /firesim.sh.
    # FIXME: For some reason, non-interactive are dumping me to a login.
    # FIXME: For some reason, I cannot log in to interactive jobs
    if interactive_run:
        logger.warning(
            "You did not provide a command to use in firesim.sh. Proceeding with INTERACTIVE simulation!"
        )
        with utils.mount_disk_img(config.sim_img.resolve()) as mountpoint:
            old_firesim_sh = mountpoint / "firesim.sh"
            os.unlink(old_firesim_sh, missing_ok=True)
    else:
        logger.info(
            "You provided a command to use in firesim.sh. Building firesim.sh for automatic execution."
        )
        firesim_sh = write_firesim_sh(config.sim_config, config.cmd)
        with utils.mount_img(config.sim_img.resolve(), run_queue) as mountpoint:
            run_queue.append(
                textwrap.dedent(f"""\
            cp "{firesim_sh.resolve()!s}" "$MOUNT_IMG_TMP_DIR"
            """)
            )

    log_dir_latest = update_log_files(config.log_dir, config.run_name)

    run_queue += infrasetup(config)
    run_queue += run_simulation(config, log_dir_latest)
    logger.debug(f"{run_queue=!s}")
    return run_queue


def run(config: RunConfig) -> JobInfo:
    """
    Run the Slurm job in an interactive "srun" session.
    """
    run_tasks = build_run_tasks(config)
    logger.info(f"Running this job as interactive?: {config.is_interactive()}")

    fireslurm_run = config.sim_config / f"fireslurm-run-{config.run_name!s}.sh"
    with open(fireslurm_run, "w") as s:
        s.write("\n".join(run_tasks))
        os.chmod(fireslurm_run, 0o775)

    job_name = config.run_name + "-interactive" if config.is_interactive() else config.run_name
    # fmt: off
    srun_cmd = [
        "srun",
        "--partition", config.partitions_flag(),
        "--nodelist", config.nodelist_flag(),
        "--job-name", job_name,
        # XXX: We make the srun run in a PTY and unbuffered so that we can
        # stream the simulator's output to the user live and correctly, making
        # this seem like a truly interactive process.
        "--pty",
        "--unbuffered",
        "--exclusive",
        fireslurm_run.resolve(),
    ]
    # fmt: on
    logger.debug(f"{srun_cmd=!s}")

    # We use PTY spawn because it just does "the right thing". Making
    # subprocess.Popen work with the PTY stack between Slurm and us, and then
    # again between Slurm and the simulation make things very difficult to get
    # right. If we _really_ need to slice-and-dice this output and not the
    # logged uartlog output, then we can rewrite this to use subprocess.Popen.
    pty.spawn(srun_cmd)

    # Since we srun above and do not capture the stdout of the srun (because
    # we are using pty.spawn), we never see Slurm's assigned job id. However,
    # because run hijacks the terminal for displaying the run as it is
    # happening, this is kind of a non-issue.
    return JobInfo(run_id=config._run_id)
