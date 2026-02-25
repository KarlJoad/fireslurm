from dataclasses import dataclass
import fireslurm.config as config


@dataclass(frozen=True)
class JobInfo:
    """
    Class containing information about a submitted Slurm job.
    """

    slurm_job_id: int = -1
    """The numerical ID Slurm assigned this job."""

    run_id: config.FireSlurmID = config.DEFAULT_FIRESLURM_ID
    """
    The FireSlurm ID assigned to this Slurm job because FireSlurm controls
    the job.
    This is linked to the FireSlurmConfig that is used to launch the Slurm job.
    """
