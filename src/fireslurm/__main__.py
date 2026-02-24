#!/usr/bin/env python

import argparse
import inspect
import logging
from pathlib import Path
from dataclasses import replace, fields, asdict
import enum

import fireslurm.args as args
import fireslurm.config as config
import fireslurm.batch
import fireslurm.run
import fireslurm.sync


logger = logging.getLogger(__name__)


# StrEnum comes from Python 3.11
# class FireSlurmCommands(enum.StrEnum):
class FireSlurmCommands(enum.Enum):
    """
    The set of subcommands that FireSlurm accepts.
    """

    SYNC = "sync"
    DIRECT_RUN = "direct-run"
    RUN = "run"
    BATCH = "batch"


def sync(fireslurm_config: config.FireSlurmConfig, args: argparse.Namespace) -> None:
    sync_config = config.SyncConfig(
        **asdict(fireslurm_config),
        infrasetup_target=args.infrasetup_target,
        config_name=args.config_name,
        description=args.description,
    )
    logger.info(f"Synchronizing infrasetup target to FireSlurm {sync_config=!s}")
    logger.debug(f"{sync_config=!s}")
    return fireslurm.sync.sync(sync_config)


def direct_run(fireslurm_config: config.FireSlurmConfig, args: argparse.Namespace) -> None:
    run_config = config.RunConfig(
        **asdict(fireslurm_config),
        run_name=args.run_name,
        cmd=args.cmd,
    )
    logger.info(
        f"Running FireSim{' interactively' if run_config.is_interactive() else ' scripted'}"
    )
    logger.debug(f"{run_config=!s}")
    fireslurm.run._run(run_config)


def run(fireslurm_config: config.FireSlurmConfig, args: argparse.Namespace) -> None:
    run_config = config.RunConfig(
        **asdict(fireslurm_config),
        run_name=args.run_name,
        cmd=args.cmd,
    )
    logger.info(
        f"Running FireSlurm job with srun{' interactively' if run_config.is_interactive() else ' scripted'}"
    )
    logger.debug(f"{run_config=!s}")
    fireslurm.run.run(run_config)


def build_sync_parser(subparser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    sync_parser = subparser.add_parser(
        FireSlurmCommands.SYNC.value,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=inspect.cleandoc(
            """Synchronize your FireSlurm layout with a new FireSim environment"""
        ),
    )
    sync_parser.set_defaults(func=sync)
    sync_parser.add_argument(
        "--config-name",
        dest="config_name",
        required=True,
        type=str,
        help=inspect.cleandoc("""Name for this new FireSim configuration."""),
    )
    sync_parser.add_argument(
        "--description",
        type=str,
        help=inspect.cleandoc("""Description of the kind of Firechip simulation design this is."""),
    )
    args.sim_config(sync_parser)
    sync_parser.add_argument(
        "--infrasetup-target",
        dest="infrasetup_target",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Path to the directory that firesim's infrasetup
        command targeted.
        This directory should contain the driver-bundle.tar.gz and
        firesim.tar.gz."""),
    )
    return sync_parser


def build_direct_run_parser(subparser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    run_parser = subparser.add_parser(
        FireSlurmCommands.DIRECT_RUN.value,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=inspect.cleandoc("""Run a FireSim simulation directly. This
        bypasses Slurm entirely to run the simulation.
        WARNING: Do not use this unless you know what you are doing! This
        subcommand is primarily intended for internal use, not end-user
        command-line!"""),
    )
    run_parser.set_defaults(func=direct_run)
    args.sim_config(run_parser)
    args.overlay_path(run_parser)
    args.sim_img(run_parser)
    args.sim_prog(run_parser)
    args.log_dir(run_parser)
    args.run_name(run_parser)
    run_parser.add_argument(
        "-p",
        "--print-start",
        dest="print_start",
        action="store",
        default=-1,
        help=inspect.cleandoc("""Clock cycle to begin emitting trace printing
        from the core."""),
    )
    args.cmd(run_parser)
    args.dry_run(run_parser)
    return run_parser


def build_run_parser(subparser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    srun_parser = subparser.add_parser(
        FireSlurmCommands.RUN.value,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=inspect.cleandoc("""Run a FireSim simulation under Slurm with srun"""),
    )
    srun_parser.set_defaults(func=run)
    args.sim_config(srun_parser)
    args.overlay_path(srun_parser)
    args.sim_img(srun_parser)
    args.sim_prog(srun_parser)
    args.partition(srun_parser)
    args.nodelist(srun_parser)
    args.log_dir(srun_parser)
    args.run_name(srun_parser)
    srun_parser.add_argument(
        "-s",
        "--print-start",
        dest="print_start",
        action="store",
        default=-1,
        help=inspect.cleandoc("""Clock cycle to begin emitting trace printing
        from the core."""),
    )
    args.cmd(srun_parser)
    args.dry_run(srun_parser)
    return srun_parser


def build_batch_parser(subparser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    batch_parser = subparser.add_parser(
        FireSlurmCommands.BATCH.value,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=inspect.cleandoc("""Submit a FireSim simulation job to Slurm using sbatch"""),
    )
    batch_parser.set_defaults(func=fireslurm.batch.batch)
    args.sim_config(batch_parser)
    args.run_name(batch_parser)
    args.overlay_path(batch_parser)
    args.sim_img(batch_parser)
    args.sim_prog(batch_parser)
    args.partition(batch_parser)
    args.nodelist(batch_parser)
    args.log_dir(batch_parser)
    batch_parser.add_argument(
        "--results-dir",
        dest="results_dir",
        required=True,
        type=Path,
        help=inspect.cleandoc("""Path to where results extracted from FireSim's
        outputs should be placed."""),
    )
    args.cmd(batch_parser)
    return batch_parser


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fireslurm.py",
        description="Run and Batch (with Slurm's sbatch) FireSim simulation runs!",
        epilog="Lovingly made by NCW, Atmn, and KGH.",
        add_help=True,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="fireslurm_config_path",
        required=False,
        type=Path,
        default=Path("fireslurm.yaml"),
        help=inspect.cleandoc("""Path to a FireSlurm configuration file.
        If unspecified, FireSlurm looks for fireslurm.yaml in the directory
        FireSlurm was invoked from (the PWD)."""),
    )

    args.verbose(parser)
    args.dry_run(parser)

    subparsers = parser.add_subparsers(
        title="Commands",
        required=True,
        dest="command_str",
        help=inspect.cleandoc("""Available Commands"""),
    )
    _sync_parser = build_sync_parser(subparsers)
    _run_parser = build_direct_run_parser(subparsers)
    _srun_parser = build_run_parser(subparsers)
    _batch_parser = build_batch_parser(subparsers)

    return parser


def read_fireslurm_config(config_path: Path) -> config.FireSlurmConfig:
    """
    Read FireSlurm's configuration file from CONFIG_PATGH and return the
    configuration.
    """
    import yaml

    # Use the "!path" YAML tag to trigger a specialty constructor that we use
    # to do type conversion from bare string to a pathlib.Path object.
    def path_constructor(loader, node):
        value = loader.construct_scalar(node)
        return Path(value)

    # Register the constructor
    yaml.SafeLoader.add_constructor("!path", path_constructor)

    with open(config_path.resolve(), "r") as cfg:
        file_config = yaml.safe_load(cfg)

    cfg = config.FireSlurmConfig(**file_config)
    logger.debug(f"Found configuration options in config file: {cfg=!s}")

    return cfg


def config_with_cli_flags(
    config: config.FireSlurmConfig,
    cli_flags: argparse.Namespace,
) -> config.FireSlurmConfig:
    config_fields = {f.name for f in fields(config)}

    config_cli_flags = {
        k: v for k, v in vars(cli_flags).items() if k in config_fields and v is not None
    }
    new_cfg = replace(config, **config_cli_flags)
    logger.debug(f"Configuration options after overlaying CLI flags: {new_cfg=!s}")
    return new_cfg


def main():
    parser = build_argparser()
    args = parser.parse_args()
    logging.basicConfig(
        format="%(levelname)s:%(name)s:%(funcName)s:%(lineno)d:%(message)s",
        level=logging.DEBUG if args.verbosity > 0 else logging.INFO,
    )
    logger.debug(f"Running with {args=!s}")

    fireslurm_config = read_fireslurm_config(args.fireslurm_config_path)

    if vars(args).get("cmd", None) is not None:
        logger.debug(f"Consolidating {args.cmd=!s} to single string")
        args.cmd = " ; ".join(args.cmd)
        logger.debug(f"Consolidated {args.cmd=!r}")

    # "Overlay" arguments provided on the CLI so they take precedence over the
    # config file.
    fireslurm_config = config_with_cli_flags(fireslurm_config, args)

    args.func(**vars(args))


if __name__ == "__main__":
    main()
