from pathlib import Path
import os
import logging


logger = logging.getLogger(__name__)


def path_is_readable_dir(dir: Path) -> bool:
    """
    Return True if DIR exists, is a directory, and readable.

    NOTE: This implementation has a TOCTOU "vulnerability". Be careful with
    multiple processes/threads accessing/working with these files!
    """
    logger.debug(f"Validating that {dir=!s} is a readable directory!")
    return all(
        [
            dir.exists(),
            dir.is_dir(),
            os.access(dir, os.R_OK),
        ]
    )
