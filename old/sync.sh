#!/bin/bash


# take the first argument and use it as a name
if [ -z "$1" ]; then
  echo "No name provided. usage: ./sync.sh <name> <description>"
  exit
else
  name=$1
fi

shift


if [ -z "$1" ]; then
  echo "No description provided. usage: ./sync.sh <name> <description>"
  exit
else
  description=$1
fi

# format the date as YYYYMMDD
date=$(date +%Y%m%d)

DIR=${PWD}/configs/$name-$date

# create a symlink to DIR named latest
ln -sfn $DIR ${PWD}/configs/$name

mkdir -p $DIR

tar xvf /home/generic/yukon_runs/sim_slot_0/driver-bundle.tar.gz -C $DIR
tar xvf /home/generic/yukon_runs/sim_slot_0/firesim.tar.gz -C $DIR

echo $description > $DIR/description.txt
