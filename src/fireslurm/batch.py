#!/usr/bin/env python3

"""
Batch up and submit multiple run.py jobs to Slurm.

This program sets up job submission directories for the jobs that are submitted
to Slurm, so each run is kept isolated from one another. Eventually, Slurm will
pick up the job and run the run.py script on a FireSim-enabled machine.
"""

import logging
from pathlib import Path
import subprocess
import re
import textwrap
import os

from fireslurm.config import BatchConfig
import fireslurm.utils as utils
from fireslurm.slurm import JobInfo
import fireslurm.zipper as fzipper


logger = logging.getLogger(__name__)


def build_job_script_contents(
    config: BatchConfig,
    run_py: Path,
) -> str:
    """
    Assemble and return a string that will be used as the contents of the script
    that will be given to sbatch.
    """
    logger.debug("Building the sbatch submission script's contents!")

    # We can get away with setting the verbosity this way and then just
    # inserting the empty string into the shell command because sbatch runs a
    # shell command. This means the empty string is effectively thrown away.
    verbose_flag = config.verbose_flag()

    return textwrap.dedent(f"""\
    #!/usr/bin/env bash
    echo "Hello from $SLURM_JOB_ID"
    sleep 2
    echo "Running {run_py.resolve()!s}"
    python3 {run_py.resolve()!s} \\
            {verbose_flag!s} \\
            direct-run \\
            --run-name {config.run_name!s} \\
            --sim-config {config.sim_config.resolve()!s} \\
            --overlay-path {config.overlay_path.resolve()!s} \\
            --sim-img {config.sim_img.resolve()!s} \\
            --sim-prog {config.sim_prog.resolve()!s} \\
            --log-dir {config.log_dir.resolve()!s} \\
            -- '{config.cmd!s}'
    """)


def build_sbatch_script(
    config: BatchConfig,
    results_dir: Path,
) -> Path:
    """
    Return the path to the generated script that will be given to sbatch.
    """
    results_dir.mkdir(parents=True, exist_ok=True)

    script = (config.sim_config / f"run-{config.run_name}.sh").resolve()
    job_run_py = fzipper.build_job_run_py(config.sim_config / "fireslurm.pyz")
    assert job_run_py and job_run_py.exists(), (
        f"FireSlurm's runner must be in {config.sim_config.resolve()}"
    )
    logger.info(f"Writing the sbatch submission to {script=!s}")
    with open(script, "w") as s:
        s.write(build_job_script_contents(config, job_run_py))
    os.chmod(script, 0o775)
    return script


def submit_slurm_job(
    config: BatchConfig,
    job_file: Path,
) -> JobInfo:
    """
    Submit JOB_FILE to Slurm with JOB_NAME, returning the job's information.

    Specify OUTPUT_FILE to name and send the job's stdout printing to another
    file.
    """

    # fmt: off
    sbatch_cmd = [
        "sbatch",
        "--partition", ",".join(config.partitions),
        "--nodelist", ",".join(config.nodelist),
        "--job-name", f"{config.run_name!s}",
        "--output", f"{config.slurm_output.resolve()!s}",
        "--error", f"{config.slurm_error.resolve()!s}",
        "--exclusive",
    ]
    # fmt: on
    # Now put the extra flags on
    if config.verbose():
        sbatch_cmd.append(config.verbose_flag())
    if utils.dry_run:
        sbatch_cmd += ["--test-only"]
    # And lastly, the job script we just built.
    # XXX: The job script MUST come last! Flags to sbatch must be provided
    sbatch_cmd += [f"{job_file.resolve()!s}"]

    logger.debug(f"{sbatch_cmd=!s}")

    # sbatch is unique because the sbatch command also has a dry-run flag to
    # help estimate when your job allocation might be run. So we ALWAYS run
    # the sbatch command, even if the user selected a dry-run.
    if utils.dry_run:
        utils.run_cmd(sbatch_cmd)

    proc = subprocess.run(
        sbatch_cmd,
        capture_output=True,
        text=True,
        check=True,
    )

    if proc.returncode != 0:
        logger.error(f"sbatch STDOUT: {proc.stdout}")
        logger.error(f"sbatch STDERR: {proc.stderr}")
        raise subprocess.CalledProcessError(proc.returncode, sbatch_cmd)
    else:
        logger.info(f"sbatch STDOUT: {proc.stdout}")
        logger.info(f"sbatch STDERR: {proc.stderr}")

    job = JobInfo()
    # Regex match on the STDOUT that sbatch produced to grab the job number.
    if not utils.dry_run:
        job_match = re.match(r"^Submitted batch job (\d+)$", proc.stdout)
        job = JobInfo(
            slurm_job_id=int(job_match[1]),
            run_id=config._run_id,
        )
        logger.info(f"Job submitted! Job Info {job=!s}")
        logger.info(f"STDOUT output will be in {config.slurm_output.resolve()=!s}")
        logger.info(f"STDERR output will be in {config.slurm_error.resolve()=!s}")

    return job


def batch(config: BatchConfig) -> JobInfo:
    config.log_dir.mkdir(parents=True, exist_ok=True)

    job_file = build_sbatch_script(
        config,
        Path("results"),  # Placeholder
    )

    # XXX: Slurm will not create directories to the STDOUT/STDERR paths that we
    # specify with the --output/--error flags to sbatch. So we must do it
    # ourself.
    config.slurm_output.mkdir(parents=True, exist_ok=True)
    config.slurm_error.mkdir(parents=True, exist_ok=True)

    job = submit_slurm_job(
        config,
        job_file,
    )
    return job
