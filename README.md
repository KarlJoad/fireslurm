# FireSlurm: FireSim and Slurm Play Together! 💘

## Dependencies
FireSlurm was written to have as few dependencies as possible.
This is because only some of the nodes you are sending FireSim jobs to may have all the dependencies you need.

Our dependencies right now:
  - [pyslurm 21.08](https://pyslurm.github.io/21.8/)
      - The PySlurm version must match the version of Slurm the cluster is using.

## Intended Workflow
The intended workflow for FireSlurm is as follows:
  1. Run `firesim infrasetup` once on the orchestration host to build and copy the simulator binaries, disk image, and bitstream to the simulation host.
  2. Run `sync.py` on the simulation host to synchronize a configuration directory with the FireSim-copied pieces.
  3. Run `run.py` on the simulation host to set up the FPGA, build a working/results directory, and run the simulator.
     Note that this script takes similar actions as `firesim infrasetup`, but it does it entirely **locally**.
      It is included to make `run.py` idempotent.
  4. Use `batch.py` on an Slurm- and NFS-enabled host to submit many `run.py` jobs to Slurm for queued running.

**Only Step 1 needs to be done on the orchestration host!**
This is a significant departure from how FireSim normally works, which requireds a constant connection between the orchestration and simulation host for FireSim to behave nicely.

## Usage
All FireSlurm operations can be started in the usual ways:
  - `python3 -m fireslurm <cmd>`, if the `src/` directory is in your `PYTHONPATH` environment variable.
  - `/path/to/fireslurm.py <cmd>`, for global usage, but is not recommended.
  - `uv run fireslurm`, for local usage with `uv` handling all the complicated path stuff.

These should be identical.
All examples below use the small `fireslurm.py` wrapper script.

### Syncing a Configuration
Before you can use FireSlurm, you must synchronize the output of FireSim's `infrasetup` command with FireSlurm.
This copies the simulation driver, bitstream, and necessary libraries to a location that FireSlurm can manage.

```sh
$ fireslurm.py sync \
  --config-name fireslurm-unified \
  --description 'My own fancy and special Firechip core to simulate with FireSim' \
  --sim-config "$(pwd)/configs" \
  --infrasetup-target /tank/generic/fparch/FIRESIM_RUNS_DIR/sim_slot_0/
```

You only need to do this step once for each change you make to:
  - The hardware (Changed a core)
  - The simulation platform (Enabled `WithPrintfSynthesis`)
  - Midas

You do **NOT** need to do this for changes to the following:
  - The kernel
  - The programs run inside the simulation
  - Adding programs to the overlay

### Running a Job
Running a job is a synchronous operation.
This means that running a FireSlurm job will take over and start printing to your terminal.
You will not get the terminal back unless you power off the simulation or you cancel the job.

```sh
$ fireslurm.py run \
  -p firesim \
  -w colbyjack \
  --sim-config "$(pwd)/configs/latest" \
  --overlay-path "$(pwd)/overlay" \
  --sim-img "$(pwd)/root.img" \
  --sim-prog "$(pwd)/kernel.bin" \
  --log-dir "$(pwd)/logs/latest" \
  --run-name 'test-fireslurm-srun-uartlog' \
  -- 'echo Hello from srun and uartlog testing; ls -lah'
```

If you want an interactive run, just leave off the command.

```sh
$ fireslurm.py run \
  -p firesim \
  -w colbyjack \
  --sim-config "$(pwd)/configs/latest" \
  --overlay-path "$(pwd)/overlay" \
  --sim-img "$(pwd)/root.img" \
  --sim-prog "$(pwd)/kernel.bin" \
  --log-dir "$(pwd)/logs/latest" \
  --run-name 'test-fireslurm-srun-uartlog'
```

### Batching a Job
Running a job is an asynchronous operation.
This means that batching u a FireSlurm job may not run immediately.
You can still cancel these jobs with `scancel`.
Note that unlike running a job, you **must** provide a command for the batched job/simulation to execute.

```sh
$ /tank/karl/buoyancy/firesim-slurm/fireslurm.py run \
  -p firesim \
  -w colbyjack \
  --sim-config "$(pwd)/configs/latest" \
  --overlay-path "$(pwd)/overlay" \
  --sim-img "$(pwd)/root.img" \
  --sim-prog "$(pwd)/kernel.bin" \
  --log-dir "$(pwd)/logs/latest" \
  --run-name 'test-fireslurm-srun-uartlog' \
  --results-dir "$(pwd)/results" \
  -- 'echo Hello from sbatch and uartlog testing; ls -lah'
```

## Thanks
Originally based on a set of scripts Nick Wanninger and Atmn Patel put together for testing Yukon.
