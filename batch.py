#!/usr/bin/env python3

import argparse
import inspect
import logging
from pathlib import Path
from dataclasses import dataclass
import subprocess
import re

import fireslurm.utils as utils


logger = logging.getLogger(__name__)


@dataclass
class JobInfo:
    """
    Class containing information about a submitted Slurm job.
    """

    id: int
    """The numerical ID Slurm assigned this job."""


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="batch.py",
        description="Batch up and submit Firesim jobs to Slurm",
        epilog="Lovingly made by NCW, Atmn, and KGH.",
        add_help=True,
    )
    parser.add_argument(
        "--fpga-config",
        dest="fpga_config",
        required=True,
        type=str,
        help=inspect.cleandoc("""The FPGA configuration that should be used
        by this job. This is given to run.py for running, so it should match
        that configuration."""),
    )
    parser.add_argument(
        "--run-name",
        dest="run_name",
        required=True,
        type=str,
        help=inspect.cleandoc("""Name to give to this run.
        NOTE: This value is also used in the logging directory!"""),
    )
    parser.add_argument(
        "--results-dir",
        dest="results_dir",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Path to where Slurm and run results should be
        put."""),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="count",
        default=0,
        help=inspect.cleandoc("""How verbosely to log. This flag can be included
        multiple times to increase the verbosity.
        This will also be passed to Slurm commands to increase the amount they
        log too."""),
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


def build_job_script_contents() -> str:
    """
    Assemble and return a string that will be used as the contents of the script
    that will be given to sbatch.
    """
    logger.debug("Building the sbatch submission script's contents!")
    return '#!/usr/bin/env bash\necho "Hello from $SLURM_JOB_ID"\nsleep 2'
    # return "#!/usr/bin/env python3"


def build_sbatch_script(run_dir: Path, run_name: str) -> Path:
    """
    Return the path to the generated script that will be given to sbatch.
    """
    assert run_dir.exists() and run_dir.is_dir(), (
        f"{run_dir=!s} must exist as a directory before use!"
    )

    script = (run_dir / f"run-{run_name}.py").resolve()
    logger.info(f"Placing the sbatch submission in {script=!s}")
    with open(script, "w") as s:
        s.write(build_job_script_contents())
    return script


def submit_slurm_job(
    job_name: str,
    job_file: Path,
    output_file: Path,
    verbosity_level: int = 0,
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
        "--partition", "firesim",
        "--nodelist", "pepperjack",
        "--job-name", f"{job_name!s}",
        "--output", f"{output_file.resolve()!s}",
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
    # Regex match on the STDOUT that sbatch produced to grab the job number.
    if not utils.dry_run and proc.returncode == 0:
        job_match = re.match(r"^Submitted batch job (\d+)$", proc.stdout)
        job.id = job_match[1]
    logger.info(f"Job submitted! Job Info {job=!s}")
    logger.info(f"STDOUT output will be in {output_file=!s}")
    return job


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()
    utils.dry_run = args.dry_run
    logging.basicConfig(
        format="%(levelname)s:%(name)s:%(funcName)s:%(lineno)d:%(message)s",
        level=logging.DEBUG if args.verbose > 0 else logging.INFO,
    )
    logger.debug(f"Running with {args=!s}")

    JOB_NAME = f"super-duper-quick-test-{args.run_name}"

    job_file = build_sbatch_script(args.results_dir, JOB_NAME)

    _job = submit_slurm_job(
        JOB_NAME,
        job_file,
        args.results_dir / "slurm-log/%j.out",
        args.verbose,
    )


if __name__ == "__main__":
    main()
