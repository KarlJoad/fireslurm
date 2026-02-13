import logging
import inspect
from pathlib import Path
import zipapp

logger = logging.getLogger(__name__)


def build_job_run_py(target) -> Path:
    """
    Build a submission zip of FireSlurm to run FireSim.
    Returns the path to the zipapp.

    This is a Python zipapp that does not use any 3rd-party dependencies, so you
    should be able to directly execute this on pretty much any machine,
    particularly any Cheese machine.
    """

    def exclude_dirs(to_include: Path) -> bool:
        """
        Determine if the path TO_INCLUDE should be included.
        Returns True if TO_INCLUDE should be included.
        """
        EXCLUDE_DIRS = [
            ".git",
            ".direnv",
            "__pycache__",
            ".ruff_cache",
            ".venv",
        ]
        should_include = not any(map(lambda exclude: exclude in str(to_include), EXCLUDE_DIRS))
        logger.debug(f"Should include {to_include}? {should_include}")
        return should_include

    # Grab the root of FireSlurm by walking 2 levels up from run.py.
    # The structure is fireslurm/fireslurm/run.py, so parents[1] brings us up to
    # the project root (fireslurm), which we can then pack together with zipapp.
    import fireslurm.run

    BATCH_SCRIPT = Path(inspect.getfile(fireslurm.run))
    FIRESLURM = BATCH_SCRIPT.parents[1]

    zipapp.create_archive(
        FIRESLURM,
        target,
        interpreter="/usr/bin/env python3",
        main="fireslurm.__main__:main",
        filter=exclude_dirs,
        compressed=True,
    )
    return target
