#!/usr/bin/env python

import argparse
import inspect
import logging
from pathlib import Path

import fireslurm.args as args
import fireslurm.batch
import fireslurm.run
import fireslurm.sync


logger = logging.getLogger(__name__)


def build_sync_parser(subparser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    sync_parser = subparser.add_parser(
        "sync",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=inspect.cleandoc(
            """Synchronize your FireSlurm layout with a new FireSim environment"""
        ),
    )
    sync_parser.set_defaults(func=fireslurm.sync.sync)
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
        "direct-run",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=inspect.cleandoc("""Run a FireSim simulation directly. This
        bypasses Slurm entirely to run the simulation.
        WARNING: Do not use this unless you know what you are doing! This
        subcommand is primarily intended for internal use, not end-user
        command-line!"""),
    )
    run_parser.set_defaults(func=fireslurm.run._run)
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
        "run",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=inspect.cleandoc("""Run a FireSim simulation under Slurm with srun"""),
    )
    srun_parser.set_defaults(func=fireslurm.run.run)
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
        "batch",
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
    args.verbose(parser)
    args.dry_run(parser)

    subparsers = parser.add_subparsers(
        title="Commands",
        required=True,
        help=inspect.cleandoc("""Available Commands"""),
    )
    _sync_parser = build_sync_parser(subparsers)
    _run_parser = build_direct_run_parser(subparsers)
    _srun_parser = build_run_parser(subparsers)
    _batch_parser = build_batch_parser(subparsers)

    return parser


def main():
    parser = build_argparser()
    args = parser.parse_args()
    logging.basicConfig(
        format="%(levelname)s:%(name)s:%(funcName)s:%(lineno)d:%(message)s",
        level=logging.DEBUG if args.verbosity > 0 else logging.INFO,
    )
    logger.debug(f"Running with {args=!s}")

    if vars(args).get("cmd", None) is not None:
        logger.debug(f"Consolidating {args.cmd=!s} to single string")
        args.cmd = " ; ".join(args.cmd)
        logger.debug(f"Consolidated {args.cmd=!r}")

    args.func(**vars(args))


if __name__ == "__main__":
    main()
