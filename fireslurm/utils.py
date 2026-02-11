from typing import List, Union
from pathlib import Path
import os
import logging
import curses
import sys
import subprocess


logger = logging.getLogger(__name__)


# Perhaps pull in colorama or supports-color?
def supports_color() -> True:
    """
    Return True if the terminal supports color.
    """
    if sys.stdout.isatty() and "TERM" in os.environ:
        try:
            curses.setupterm()
            # tigetnum('colors') returns the number of colors supported, or -1 if not supported
            colors = curses.tigetnum("colors")
            return colors >= 8  # Check for at least 8 colors (basic ANSI)
        except curses.error:
            pass
    return False


def wants_color() -> bool:
    """
    Return True if the user's environment variables specify that they want
    ANSI escape code colors.
    """
    if os.getenv("PYTHON_COLORS", None) is not None:
        return True
    if os.getenv("NO_COLOR", None) is not None:
        return False
    if os.getenv("FORCE_COLOR", None) is not None:
        return True


def extend_path(env_var: str, vals: List[Union[str, Path]], sep: str = os.pathsep) -> str:
    """
    Extend the environment variable ENV_VAR with VALS.
    You may specify the path separator in SEP. By default, SEP will use the
    OS-specific path separator character.

    Returns the a tuple with the (old, new) states of the environment variable.
    """

    def val_to_str(v: Union[str, Path]) -> str:
        if isinstance(v, str):
            return v
        elif isinstance(v, Path):
            return str(v.resolve())

    logger.debug(f"Extending {env_var} with {vals}")
    old_val = os.environ.get(env_var, "")
    vals_to_add = map(val_to_str, vals)
    os.environ[env_var] = sep.join(vals_to_add) + sep + old_val
    logger.debug(f"New state of {env_var}: {os.environ.get(env_var, '')}")
    return (old_val, os.environ.get(env_var, ""))


# Should all subprocess commands be executed as "dry-run" commands or should
# they go through as real commands and actually do things?
dry_run: bool = False


def run_cmd(cmd) -> Union[subprocess.CompletedProcess, None]:
    """
    Potentially run CMD depending if the user requested a dry run.
    If the `dry_run` global flag is True, then the command that woul d be run is
    simply logged.
    If the `dry_run` is False, then actually run the program.
    """
    global dry_run
    if dry_run:
        logger.warning(f"Dry-Running {cmd=!s}")
        return None
    else:
        return subprocess.run(cmd, check=True)
