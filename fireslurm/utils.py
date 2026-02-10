from typing import List, Union
from pathlib import Path
import os
import logging


logger = logging.getLogger(__name__)


def extend_path(env_var: str, vals: List[Union[str, Path]], sep: str = os.pathsep) -> str:
    """
    Extend the environment variable ENV_VAR with VALS.
    You may specify the path separator in SEP. By default, SEP will use the
    OS-specific path separator character.

    Returns the a tuple with the (old, new) states of the environment variable.
    """
    logger.debug(f"Extending {env_var} with {vals}")
    old_val = os.environ.get(env_var, "")
    os.environ[env_var] = sep.join(vals) + sep + old_val
    logger.debug(f"New state of {env_var}: {os.environ.get(env_var, '')}")
    return (old_val, os.environ.get(env_var, ""))
