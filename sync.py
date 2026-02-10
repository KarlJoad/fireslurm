#!/usr/bin/env python3

"""
Synchronize a FireSim simulation directory for later FireSlurm use.

By default, FireSim replaces its files on every "infrasetup". This can lead to
issues when you want to check out older versions of everything the simulation is
using (hardware, firmware, software).

This tool takes the contents that FireSim installs on the simulation host with
"infrasetup" and copies it to a simulation configuration directory that is
versioned. This prevents FireSlurm from losing previous configurations.
"""

import argparse
import inspect
import logging
import os
from pathlib import Path
from datetime import datetime

import fireslurm.utils as utils


logger = logging.getLogger(__name__)


def build_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync.py",
        description="Synchronize a Firesim simulation directory for later use",
        epilog="Lovingly made by NCW, Atmn, and KGH.",
        add_help=True,
    )
    parser.add_argument(
        "name",
        type=str,
        help=inspect.cleandoc("""Name for this Firesim configuration."""),
    )
    parser.add_argument(
        "description",
        type=str,
        help=inspect.cleandoc("""Description of the kind of Firechip simulation design this is."""),
    )
    parser.add_argument(
        "--config-dir",
        dest="config_dir",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Path to the configuration directory for Firesim
        and FireSlurm."""),
    )
    parser.add_argument(
        "--config-name",
        dest="config_name",
        required=True,
        type=str,
        help=inspect.cleandoc("""Name for this new configuration."""),
    )
    parser.add_argument(
        "--infrasetup-target",
        dest="infrasetup_target",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Path to the directory that firesim's infrasetup
        command targeted.
        This directory should contain the driver-bundle.tar.gz and
        firesim.tar.gz."""),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="count",
        default=0,
        help=inspect.cleandoc("""
                    How verbosely to log. This flag can be included multiple
                    times to increase the verbosity"""),
    )
    return parser


def build_config_dir(config_dir: Path, config_name: str) -> Path:
    """
    Build a configuration directory. Return the path to the latest
    configuration directory.
    """
    logger.debug("Synchronizing configuration files for current run")
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)

    dt = datetime.now()
    config_name = config_name + dt.strftime("%Y-%m-%d%H%M%S")
    current_config_dir = config_dir / config_name
    current_config_dir.mkdir(exist_ok=False)
    logger.info(f"Created {current_config_dir}")

    # Remove the previous "latest" run, because we are about to do a new run
    # If latest did not exist before, then we don't need to do anything.
    latest_config = config_dir / "latest"
    try:
        os.remove(latest_config)
    except FileNotFoundError as e:
        logger.info(f"{e} {latest_config}. Not removing.")

    # Register the now-current run as the latest log
    os.symlink(src=current_config_dir, dst=latest_config)
    logger.info(f"Marked {current_config_dir} as latest in {config_dir}")
    return latest_config


def unzip_firesim_libs(compressed_tarball: Path, decompress_target: Path) -> None:
    """
    Unzip/Decompress the contents of COMPRESSED_TARBALL to DECOMPRESS_TARGET.
    """
    logger.info(f"Unzipping {compressed_tarball.resolve()} to {decompress_target.resolve()}")
    compression_flag = ""
    compression_suffix = compressed_tarball.suffixes[-1]
    match compression_suffix:
        case ".gz" | ".gzip":
            compression_flag = "--gzip"
        case ".bz2":
            compression_flag = "--bzip2"
        case ".xz":
            compression_flag = "--xz"
        case ".tar":
            compression_flag = ""
        case _:
            logger.fatal(f"Unknown compression suffix: {compression_suffix}")
            raise RuntimeError(f"Unknown compression suffix: {compression_suffix}")

    # fmt: off
    tar_cmd = [
        "tar",
        # XXX: -C MUST come before any other flags!
        "-C", decompress_target.resolve(),
        "-x",
        compression_flag,
        "-v",
        "-f", compressed_tarball.resolve(),
    ]
    # fmt: on
    logger.debug(f"{tar_cmd=!s}")
    utils.run_cmd(tar_cmd)


def main() -> None:
    parser = build_argparse()
    args = parser.parse_args()
    logging.basicConfig(
        format="%(levelname)s:%(name)s:%(funcName)s:%(lineno)d:%(message)s",
        level=logging.DEBUG if args.verbose > 0 else logging.INFO,
    )
    logger.debug(f"Running with {args=!s}")

    config_dir = build_config_dir(args.config_dir, args.config_name)

    unzip_firesim_libs(args.infrasetup_target / "driver-bundle.tar.gz", config_dir)
    unzip_firesim_libs(args.infrasetup_target / "firesim.tar.gz", config_dir)

    with open(config_dir / "description.txt", "w") as desc_file:
        desc_file.write(args.description)


if __name__ == "__main__":
    main()
