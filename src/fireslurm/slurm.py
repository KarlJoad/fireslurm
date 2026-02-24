from dataclasses import dataclass


@dataclass(frozen=True)
class JobInfo:
    """
    Class containing information about a submitted Slurm job.
    """

    slurm_job_id: int = -1
    """The numerical ID Slurm assigned this job."""
