#!/usr/bin/env bash

set -e



ROOT_IMG=${HOME}/yukon/yukon-smoke0-yukon-smoke.img
PROGRAM=${HOME}/yukon/nick-kernel-bin
CONFIG_DIR="${HOME}/yukon/configs"
CONFIG=""

# ROOT_IMG=${HOME}/yukon/yukon-br0-yukon-br.img

PRINT_START="-1"

LOGNAME=""

# Process flags using getopts
while getopts "c:S:L:" opt; do
  case $opt in
    c) CONFIG=${OPTARG};;
    S) PRINT_START=${OPTARG};;
    L) LOGNAME="${OPTARG}"
  esac
done

# Shift off the options and their arguments
shift $((OPTIND - 1))


# Define the path for the firesim.sh file
FIRESIM_PATH="${HOME}/yukon/overlay/firesim.sh"
sudo mkdir -p ${HOME}/yukon/overlay/etc/firesim/
# Check if there are any remaining arguments
if [ "$#" -eq 0 ]; then
    sudo bash -c "cat << EOF > $FIRESIM_PATH
#!/bin/sh
exit 0
EOF"
    echo "firesim.sh has been set to do nothing"
else
    COMMAND="$@"
    sudo bash -c "cat << EOF > $FIRESIM_PATH
#!/bin/sh
set -x
# Disable ASLR
echo 0 | tee /proc/sys/kernel/randomize_va_space
sleep 1

cat /boot/config-$(uname -r) | grep TRANSPARENT_HUGEPAGE


# export PYTHONMALLOC=malloc
# export ALASKA_INFO=yes
firesim-start-trigger
$COMMAND # || true
firesim-end-trigger
# sync
poweroff -f
EOF"
    echo "File $FIRESIM_PATH has been created or overwritten successfully."
fi
sudo chmod +x ${FIRESIM_PATH}



if [ -z "$CONFIG" ]; then
	configs=$(ls -t ${CONFIG_DIR} | grep '.bit')
	options=()
	for file in $configs; do
	    options+=("$file" "" )  # Each file with an empty description
	done

	CONFIG=${CONFIG_DIR}/$(dialog --menu "Pick a configuration:" 20 60 15 \
				  "${options[@]}" \
				  3>&1 1>&2 2>&3 || clear)
	clear
fi



LOG="${HOME}/yukon/logs/${LOGNAME}$(date +%Y-%m-%d-%H%M%S)"

CONFIG=$(realpath ${CONFIG})

mkdir -p $LOG
rm -f ${HOME}/yukon/logs/latest
ln -s ${LOG} ${HOME}/yukon/logs/latest

echo "config=${CONFIG}" >> $LOG/config


# This is "infrasetup"

# Block SIGINT
echo "Flashing the FPGA..."
trap '' INT # ignore SIGINT
sudo /usr/local/bin/firesim-xvsecctl-flash-fpga 0x01 0x00 0x1 ${CONFIG}/xilinx_vcu118/firesim.bit
sudo /usr/local/bin/firesim-change-pcie-perms 0000:01:00:0


# Copy the files over
# cp ../yukon_runs/sim_slot_0/yukon-smoke0-yukon-smoke* .
mkdir -p mountpoint/
sudo mount -o loop ${ROOT_IMG} mountpoint/
sudo rsync -Ia overlay/ mountpoint/
sudo sync -f mountpoint
sudo umount mountpoint/
# Give the above commands time to do their work in the background
sleep 0.5
# Allow SIGINT
trap - INT


# Make it so ^c doesn't cause a SIGINT, but ^] does. This is so we can send ^c to firesim.
stty intr ^] || true


# Make it so we can run firesim w/ it's libraries
export LD_LIBRARY_PATH="${HOME}/yukon/firesim/:$LD_LIBRARY_PATH"

# This may look annoying, but its easier to build up a multiline command as a big string
CMD="sudo ${CONFIG}/FireSim-xilinx_vcu118 +permissive +macaddr0=00:12:6D:00:00:02 +niclog0=niclog0 +blkdev-log0=$LOG/blkdev-log0"
CMD+=" +blkdev0=${ROOT_IMG}"
CMD+=" +blkdev1=${HOME}/yukon/yukon-br0-yukon-br.img"

# CMD+=" +tracefile=TRACEFILE"
# CMD+=" +trace-select=3 +trace-start=ffffffff00008013 +trace-end=ffffffff00010013 +trace-output-format=0"

CMD+=" +autocounter-readrate=100000000 +autocounter-filename-base=$LOG/AUTOCOUNTERFILE"
CMD+=" +dwarf-file-name=${PROGRAM}-dwarf"
CMD+=" +print-start=${PRINT_START} +print-end=-1"
CMD+=" +linklatency0=6405 +netbw0=200 +shmemportname0=default  +domain=0x0000 +bus=0x01 +device=0x00 +function=0x0 +bar=0x0 +pci-vendor=0x10ee +pci-device=0x903f"
CMD+=" +permissive-off +prog0=${PROGRAM}"
CMD+=" +disable-asserts"


pushd $LOG
  script --command "${CMD}" $LOG/uartlog || echo "Exited with nonzero"

  # Check if the TRACEFILE-C0 exists and run an extra command if it does
  if [ -f "TRACEFILE-C0" ]; then
    echo "Found trace file. Processing into a histogram. Please wait..."
    /tank/project/yukon/instruction_hist TRACEFILE-C0
    echo "TRACE LOCATION: $LOG"
  fi
popd

# Now, make it so ^c sends SIGINT again. Bash will do this for us, but who cares.
stty intr ^c || true
