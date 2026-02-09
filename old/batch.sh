#!/usr/bin/env bash


# this script is used to run benchmarks using slurm on the fpga.


# -- The bitstream configuration to use -- #
# FPGA_CONFIG=yukon-large-simple
FPGA_CONFIG=yukon-small-debug-simple-20260112
# FPGA_CONFIG=boom-large-2
# -- The suffix for the run name -- #
RUN_CONFIG=yukon
# -- The series name for the runs -- #
# SERIES=redis-ycsb-phys-debug
SERIES=${FPGA_CONFIG} # htlb-simplification-large


function run () {

  local runtime_name=$1
  local program_name=$2

  local name=${program_name}.${runtime_name}.${RUN_CONFIG}.${FPGA_CONFIG}
  LOGFILE=results/slurm-log/%j.out
  shift
  shift

  sbatch -w pepperjack -p firesim              \
    -J ${program_name}.${runtime_name}         \
    --output $LOGFILE                          \
    --exclusive <<EOF
#!/usr/bin/env bash
# /tank/project/yukon/send-message "Yukon run ${name} Starting"
python3 bench.py --hue ${name} --name ${program_name} --config configs/${FPGA_CONFIG} --series ${SERIES} $@
EOF
}


# run localize  echo     /test/cycles -y echo "Hello, World!"
# exit


# # # Graphbig KCORE
KCORE_COUNT=20 # default: 20
# run stub        graphbig-kcore                   NODUMP=yes /test/cycles    /benchmarks/handrolled-GraphBIG/kcore_b ${KCORE_COUNT}
# run localize    graphbig-kcore                              /test/cycles -y /benchmarks/handrolled-GraphBIG/kcore_b ${KCORE_COUNT}
# run libc        graphbig-kcore                   NODUMP=yes /test/cycles -b /benchmarks/handrolled-GraphBIG/kcore_b ${KCORE_COUNT}
# run yukon       graphbig-kcore                   NODUMP=yes /test/cycles -y /benchmarks/handrolled-GraphBIG/kcore_b ${KCORE_COUNT}
# exit


# # # Graphbig SSSP
# SSSP_COUNT=10 # default: 32
# run libc      graphbig-sssp NODUMP=yes /test/cycles -b /benchmarks/handrolled-GraphBIG/sssp_b 31 ${SSSP_COUNT}
# run stub      graphbig-sssp NODUMP=yes /test/cycles    /benchmarks/handrolled-GraphBIG/sssp_b 31 ${SSSP_COUNT}
# run localize  graphbig-sssp            /test/cycles -y /benchmarks/handrolled-GraphBIG/sssp_b 31 ${SSSP_COUNT}
# exit


# -----------------------------------------------------------------------
PYTHONBENCHMARKS=(
    "bipartition"
    "breadth_first_search"
    "community_detection"
    # "connected_components"
    # "degree_centrality"
    # "independent_set"
    # "k_truss"
    # "kcore"
    # "minimum_spanning_tree"
    # "pagerank"
    # "shortest_paths"
    # "triangle_counting"
    # "betweenness_centrality"
)
PYTHON_GRAPHS=(
  # "small"
  "KnowledgeRepo"
)
# /atmn/python-benchmarks/datasets
# for graph in "${PYTHON_GRAPHS[@]}"; do
#   echo "Running graph $graph..."
#   graphfile="/atmn/python-benchmarks/datasets/${graph}.csv"
#   for benchmark in "${PYTHONBENCHMARKS[@]}"; do
#     echo "Running $benchmark..."
#     pyfile="/atmn/python-benchmarks/${benchmark}.py"
# 
#     # run stub      python-${benchmark}       NODUMP=yes /test/cycles    python3 ${pyfile} ${graphfile} --runs 10
#     # run libc      python-${benchmark}-${graph}       NODUMP=yes /test/cycles -b python3 ${pyfile} ${graphfile} --runs 15
#     # run yukon     python-${benchmark}-${graph}       NODUMP=yes /test/cycles -y python3 ${pyfile} ${graphfile} --runs 15
#   done
# done
# exit
# -----------------------------------------------------------------------




# -----------------------------------------------------------------------
# Python
# run yukon     python-networkx NODUMP=yes      /test/cycles -y python3 /test/python/networkx_test.py
# run localize  python-networkx                 /test/cycles -y python3 /test/python/networkx_test.py
# run stub      python-networkx NODUMP=yes      /test/cycles    python3 /test/python/networkx_test.py
# run libc      python-networkx NODUMP=yes      /test/cycles    python3 /test/python/networkx_test.py
# exit
# -----------------------------------------------------------------------



# run baseline-stub   compiler-test   NODUMP=y LD_LIBRARY_PATH=/compiler /test/cycles    /compiler/baseline
# run compiler   compiler-test   NODUMP=y LD_LIBRARY_PATH=/compiler /test/cycles -b /compiler/alaska
# run yukon      compiler-test   NODUMP=y LD_LIBRARY_PATH=/compiler /test/cycles -y /compiler/baseline


# exit




# -----------------------------------------------------------------------
# -- The list of workloads to run -- #
# workloads=(small)
# workloads=(workloada-quickinit)
workloads=(workloadd)

# workloads=(workloada workloadb workloadc workloadd workloadf)
# workloads=(debug)
# workloads=(itty)
# workloads=(workloadb)


# fire off ycsb runs
for workload in ${workloads[@]}; do
  echo "YCSB Workload $workload"
  # run libc                 ycsb-$workload              bash /test/ycsb.sh $workload -b
  run yukon                ycsb-$workload   NODUMP=yes bash /test/ycsb.sh $workload -y
  # run localize             ycsb-$workload              bash /test/ycsb.sh $workload -y
  # run stub                 ycsb-$workload   NODUMP=yes bash /test/ycsb.sh $workload

  # run stub-no-handles        ycsb-$workload   NODUMP=yes bash /test/ycsb.sh $workload
  # run localize           ycsb-$workload              bash /test/ycsb.sh $workload -y
  # run yukon-newalloc-phys       ycsb-$workload   YUKON_PHYS=1 NODUMP=yes bash /test/ycsb.sh $workload -y
  # run mimalloc             ycsb-$workload  LD_PRELOAD=/libmimalloc.so bash /test/ycsb.sh $workload -b
  # run jemalloc             ycsb-$workload  LD_PRELOAD=/libjemalloc.so bash /test/ycsb.sh $workload -b

  # run localize-newalloc       ycsb-$workload              bash /test/ycsb.sh $workload -y
  # run localize-relocalize-phony       ycsb-$workload              bash /test/ycsb.sh $workload -y
  # run stub-with-handles  ycsb-$workload   NODUMP=yes bash /test/ycsb.sh $workload
done
# -----------------------------------------------------------------------
