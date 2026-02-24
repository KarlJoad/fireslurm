from dataclasses import dataclass


@dataclass
class JobInfo:
    """
    Class containing information about a submitted Slurm job.
    """

    slurm_job_id: int
    """The numerical ID Slurm assigned this job."""
