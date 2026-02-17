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

import fireslurm.utils as utils
from fireslurm.slurm import JobInfo
import fireslurm.zipper as fzipper


logger = logging.getLogger(__name__)


def build_job_script_contents(
    config_dir: Path,
    overlay_path: Path,
    sim_img: Path,
    sim_prog: Path,
    log_dir: Path,
    run_name: str,
    run_py: Path,
    verbosity: int,
    cmd: str,
) -> str:
    """
    Assemble and return a string that will be used as the contents of the script
    that will be given to sbatch.
    """
    logger.debug("Building the sbatch submission script's contents!")

    verbose_flag = "-" + "v" * verbosity if verbosity > 0 else ""

    return textwrap.dedent(f"""\
    #!/usr/bin/env bash
    echo "Hello from $SLURM_JOB_ID"
    sleep 2
    echo "Running {run_py.resolve()!s}"
    python3 {run_py.resolve()!s} \\
            {verbose_flag!s} \\
            direct-run \\
            --run-name {run_name!s} \\
            --sim-config {config_dir.resolve()!s} \\
            --overlay-path {overlay_path.resolve()!s} \\
            --sim-img {sim_img.resolve()!s} \\
            --sim-prog {sim_prog.resolve()!s} \\
            --log-dir {log_dir.resolve()!s} \\
            -- '{cmd!s}'
    """)


def build_sbatch_script(
    config_dir: Path,
    overlay_path: Path,
    sim_img: Path,
    sim_prog: Path,
    log_dir: Path,
    results_dir: Path,
    run_name: str,
    verbosity: int,
    cmd: str,
) -> Path:
    """
    Return the path to the generated script that will be given to sbatch.
    """
    results_dir.mkdir(parents=True, exist_ok=True)

    script = (config_dir / f"run-{run_name}.sh").resolve()
    job_run_py = fzipper.build_job_run_py(config_dir / "fireslurm.pyz")
    assert job_run_py and job_run_py.exists(), (
        f"FireSlurm's runner must be in {config_dir.resolve()}"
    )
    logger.info(f"Writing the sbatch submission to {script=!s}")
    with open(script, "w") as s:
        s.write(
            build_job_script_contents(
                config_dir,
                overlay_path,
                sim_img,
                sim_prog,
                log_dir,
                run_name,
                job_run_py,
                verbosity,
                cmd,
            )
        )
    return script


def submit_slurm_job(
    job_name: str,
    job_file: Path,
    output_file: Path,
    verbosity_level: int,
    slurm_partitions: str,
    slurm_nodelist: str,
) -> JobInfo:
    """
    Submit JOB_FILE to Slurm with JOB_NAME, returning the job's information.

    Specify OUTPUT_FILE to name and send the job's stdout printing to another
    file.
    """

    job = JobInfo(-1)
    # fmt: off
    sbatch_cmd = [
        "sbatch",
        "--partition", slurm_partitions,
        "--nodelist", slurm_nodelist,
        "--job-name", f"{job_name!s}",
        "--output", f"{output_file.resolve()!s}",
        "--error", f"{output_file.with_suffix('.err').resolve()!s}",
        "--exclusive",
    ]
    # fmt: on
    # Now put the extra flags on
    if verbosity_level > 0:
        sbatch_cmd += ["-" + "v" * verbosity_level]
    if utils.dry_run:
        sbatch_cmd += ["--test-only"]
    # And lastly, the job script we just built.
    # XXX: The job script MUST come last! Flags to sbatch must be provided
    sbatch_cmd += [f"{job_file.resolve()!s}"]

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

    # Regex match on the STDOUT that sbatch produced to grab the job number.
    if not utils.dry_run:
        job_match = re.match(r"^Submitted batch job (\d+)$", proc.stdout)
        job.id = job_match[1]
        logger.info(f"Job submitted! Job Info {job=!s}")
        logger.info(f"STDOUT output will be in {output_file=!s}")

    return job


def batch(
    run_name: str,
    sim_config: Path,
    overlay_path: Path,
    sim_img: Path,
    sim_prog: Path,
    log_dir: Path,
    results_dir: Path,
    verbosity: int,
    slurm_partitions: str,
    slurm_nodelist: str,
    cmd: str,
    **kwargs,
) -> None:
    JOB_NAME = f"super-duper-quick-test-{run_name}"

    log_dir.mkdir(parents=True, exist_ok=True)

    job_file = build_sbatch_script(
        sim_config,
        overlay_path,
        sim_img,
        sim_prog,
        log_dir,
        results_dir,
        JOB_NAME,
        verbosity,
        cmd,
    )

    # XXX: Slurm will not create directories to the STDOUT/STDERR paths that we
    # specify with the --output/--error flags to sbatch. So we must do it
    # ourself.
    slurm_log_dir = log_dir / "slurm-log"
    slurm_log_dir.mkdir(parents=True, exist_ok=True)

    _job = submit_slurm_job(
        JOB_NAME,
        job_file,
        log_dir / "slurm-log/%j.out",
        verbosity,
        slurm_partitions,
        slurm_nodelist,
    )
