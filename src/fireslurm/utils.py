from typing import Iterator, List, Tuple, Union
from pathlib import Path
import os
import logging
import curses
import sys
import subprocess
from contextlib import contextmanager
import signal
import tempfile

# import stty  # Comes from 3rd party
import textwrap


logger = logging.getLogger(__name__)


# Perhaps pull in colorama or supports-color?
def supports_color() -> bool:
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
            return False
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
    # If we could not figure out that the user wants color, then we just assume
    # that they do not want color.
    return False


def extend_path(
    env_var: str,
    vals: List[Union[str, Path]],
    sep: str = os.pathsep,
) -> Tuple[str, str]:
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


@contextmanager
def mount_img(img: Path, work_queue: List[str]) -> Iterator[str]:
    """
    Attempt to mount IMG to a temporary mountpoint. If this is successful, then
    the dynamic context (the contents of the with-block) are run with IMG
    mounted to the yielded path.

    If the mount or the contents of the block throw an exception, then the image
    is sync-ed and unmounted, and the temporary mountpoint removed before
    exiting.
    """
    IMG_MOUNT_ENV_VAR = "MOUNT_IMG_TMP_DIR"
    work_queue.append(
        textwrap.dedent(f"""\
    {IMG_MOUNT_ENV_VAR!s}="$(mktemp --directory)"
    sudo mount -o loop {img.resolve()!s} "${IMG_MOUNT_ENV_VAR!s}"
    """)
    )
    yield IMG_MOUNT_ENV_VAR
    work_queue.append(
        textwrap.dedent(f"""\
    sudo umount "${IMG_MOUNT_ENV_VAR}"
    sync
    rmdir "${IMG_MOUNT_ENV_VAR!s}"
    """)
    )


@contextmanager
def mount_disk_img(img: Path) -> Iterator[Path]:
    """
    Attempt to mount IMG to a temporary mountpoint. If this is successful, then
    the dynamic context (the contents of the with-block) are run with IMG
    mounted to the yielded path.

    If the mount or the contents of the block throw an exception, then the image
    is sync-ed and unmounted, and the temporary mountpoint removed before
    exiting.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            subprocess.run(["sudo", "mount", "-o", "loop", img.resolve(), temp_dir], check=True)
            yield Path(temp_dir)
        finally:
            subprocess.run(["sync"])
            subprocess.run(["sudo", "umount", temp_dir])


@contextmanager
def block_sigint():
    logger.warning("Begin ignoring SIGINT! C-c will not work!")
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    yield
    logger.info("End ignoring SIGINT! C-c will now work!")
    signal.signal(signal.SIGINT, signal.SIG_DFL)


@contextmanager
def change_sigint_key(work_queue: List[str]):
    work_queue.append(
        textwrap.dedent(f"""\
    if test -t {sys.stdin.fileno()!s}; then
        echo "Changing SIGINT key to C-]!"
        stty intr ^]
    else
        echo "Not currently connected to TTY! Cannot change SIGINT key"
    fi
    """)
    )
    yield
    work_queue.append(
        textwrap.dedent(f"""\
    if test -t {sys.stdin.fileno()!s}; then
        stty intr ^c
        echo "SIGINT key changed back to to C-c!"
    else
        echo "Not currently connected to TTY! Cannot change SIGINT key"
    fi
    """)
    )


@contextmanager
def change_path(
    env_var: str, vals: List[Union[str, Path]], work_queue: List[str], sep: str = os.pathsep
):
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
    old_env_var = "OLD_" + env_var
    old_val = os.environ.get(env_var, "")
    vals_to_add = map(val_to_str, vals)
    final_path = sep.join(vals_to_add) + sep + old_val
    work_queue.append(
        textwrap.dedent(f"""\
    export {old_env_var}="${env_var}"
    export {env_var}="{final_path}"
    echo "New state of \${env_var}: \"${env_var}\""
    """)
    )
    yield
    work_queue.append(
        textwrap.dedent(f"""\
    export {env_var}="${old_env_var}"
    unset {old_env_var}
    """)
    )
