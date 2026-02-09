import pandas as pd
import subprocess
import re
import hashlib
import sys
import datetime
import os
import shutil
import argparse
import time
from pathlib import Path
from dataclasses import dataclass
import seaborn as sns
import matplotlib.pyplot as plt


START_TIME=datetime.datetime.now()
START_DATE=START_TIME.strftime("%Y-%m-%d-%H%M%S")


parser = argparse.ArgumentParser(
                    prog='bench.py',
                    description='Runs benchmarks on the FPGA')

parser.add_argument('--config', metavar="XXX", type=str, help='Path to the config folder', required=True)
parser.add_argument('--series', metavar="XXX", type=str, help='A name for the series of benchmarks', required=True)
parser.add_argument('--name', metavar="XXX", type=str, help='A name for the benchmark', required=True)
parser.add_argument('--hue', metavar="XXX", type=str, help='Hue for this run (yukon, baseline)', required=True)
parser.add_argument('--dir', type=str, help='Hue for this run (yukon, baseline)', default="/")

# get the rest as arguments
parser.add_argument('command', nargs=argparse.REMAINDER, help='Command to run')

args = parser.parse_args()

command = ' '.join(args.command)
CONFIG_PATH = args.config
BITSTREAM_DESC_PATH = Path(CONFIG_PATH) / 'description.txt'
print(BITSTREAM_DESC_PATH)

def get_uart_info(logdir):
  info = {}
  pattern = re.compile(r'YUKON_\w+=\d+')

  with open(f'{logdir}/uartlog') as f:
    for line in f:
      matches = pattern.findall(line)
      for match in matches:
        parts = match.split('=')
        name = parts[0].split('_')[1].lower()
        info[name] = float(parts[1])
  return info

def parse_autocounter(logdir):
  path = f'{logdir}/AUTOCOUNTERFILE0.csv'

  df = pd.read_csv(path, skiprows=[0, 1, 2, 4, 5, 6])
  print(df)
  # remove the 'description' column
  df = df.drop(columns=['description'])

  final = {}
  rawdata = {}

  # iterate over the columns of the df
  for col in df.columns:
    if col == 'description':
      continue
    data = list(df[col].iloc[6:].reset_index(drop=True).astype(int))
    final[col] = data[-1]
    rawdata[col] = data

  return final, pd.DataFrame(rawdata)




def hash_file(path):
  BUF_SIZE = 65536  # lets read stuff in 64kb chunks!
  md5 = hashlib.md5()
  sha1 = hashlib.sha1()
  with open(path, 'rb') as f:
    while True:
        data = f.read(BUF_SIZE)
        if not data:
            break
        md5.update(data)
  return md5.hexdigest()




def run_command(name, cmd, dir="/", hue=None):
  print(f"Running command: {cmd} in hue {hue}")
  start = time.time()
  p = subprocess.Popen(f"./run.sh -L {args.series} -c {CONFIG_PATH} 'cd {dir}; firesim-start-trigger; PYTHONMALLOC=malloc {cmd}'", shell=True)
  p.wait()
  end = time.time()
  host_walltime = end - start
  print(f"Command took {host_walltime} seconds")

  log = 'logs/latest/'


  hue_parts = hue.split('.')
  benchmark_name = hue_parts[0]
  runtime_config = hue_parts[1]
  run_name       = hue_parts[2]
  fpga_config    = hue_parts[3]




  ac, rawac = parse_autocounter(log)

  uartinfo = get_uart_info(log)
  print(uartinfo)
  res = uartinfo | ac
  res['host_walltime'] = host_walltime
  res['name'] = name
  res['command'] = cmd
  res['config'] = hue
  res['dir'] = dir
  # hash overlay/libyukon.so.2
  res['libyukon_md5'] = hash_file('overlay/libyukon.so.2')
  res['date'] = START_DATE
  res['timestamp'] = datetime.datetime.now()
  res['bitstream info'] = 'Unk.'



  try:
    res['bitstream info'] = BITSTREAM_DESC_PATH.read_text().strip()
  except:
    pass

  try:
    ki = uartinfo['instructions'] / 1000
    res['l1_htlb_mpki'] = res['l1_htlb_miss'] / ki
    res['l2_htlb_mpki'] = res['l2_htlb_miss'] / ki
    res['l1_tlb_mpki'] = res['l1_tlb_miss'] / ki
    res['l2_tlb_mpki'] = res['l2_tlb_miss'] / ki
  except:
    print('failed to calculate mpki')
    pass

  df = pd.DataFrame([res])

  result_dir = f"results/{args.series}/{name}/{res['config']}/"
  runtime_config_dir = f"results/{args.series}/{name}/{runtime_config}"
  print('result dir:', result_dir)
  print('runtime config dir:', runtime_config_dir)
  os.makedirs(result_dir, exist_ok=True)

  print('res config:', res['config'])


  rawac['seconds'] = rawac['Clock cycles elapsed in the local domain.'] / 1e9

  shutil.copyfile('overlay/libyukon.so.2', f'{result_dir}/libyukon.so.2')
  shutil.copyfile(f'{log}/uartlog', f'{result_dir}/uartlog')
  shutil.copyfile(f'{log}/AUTOCOUNTERFILE0.csv', f'{result_dir}/AUTOCOUNTERFILE0.csv')
  df.to_csv(f'{result_dir}/results.csv', header=True, index=False)
  rawac.to_csv(f'{result_dir}/rawac.csv', header=True, index=False)



  # make a symlink from runtime_config_dir to result_dir
  shutil.rmtree(runtime_config_dir, ignore_errors=True)
  try:
    os.makedirs(os.path.dirname(runtime_config_dir), exist_ok=True)
  except:
    print("Directory already exists, skipping creation")

  src = './' + res['config']
  dst = runtime_config_dir

  if os.path.lexists(dst):  # True for broken symlinks too
    if os.path.isdir(dst) and not os.path.islink(dst):
        print('removing directory', dst)
        shutil.rmtree(dst)
    else:
        print('unlinking', dst)
        os.unlink(dst)

  print(f"Creating symlink from {dst} to {src}")
  os.symlink(src, dst)

  try:
    ki = uartinfo['instructions'] / 1000

    rawac['mpki_l1_htlb'] = rawac['l1_htlb_miss'] / ki
    rawac['mpki_l2_htlb'] = rawac['l2_htlb_miss'] / ki
    rawac['mpki_l1_tlb'] = rawac['l1_tlb_miss'] / ki
    rawac['mpki_l2_tlb'] = rawac['l2_tlb_miss'] / ki
  except:
    pass

  # create a version of rawac where each row is the delta from the previous row
  diff = rawac.diff().fillna(0)
  diff['seconds'] = rawac['seconds']
  diff['Clock cycles elapsed in the local domain.'] = rawac['Clock cycles elapsed in the local domain.']
  diff.to_csv(f'{result_dir}/diff.csv', header=True, index=False)

  for col in diff.columns:
    if col == 'Clock cycles elapsed in the local domain.' or col == 'seconds':
      continue
    g = sns.lineplot(x=diff['seconds'], y=diff[col])
    g.set_title(col)
    g.set_xlabel('Time (s)')
    g.set_ylabel(col)
    print(f"Saving plot to {result_dir}/{col}.png")
    plt.savefig(f'{result_dir}/{col}.png')
    plt.clf()


  telegram_message = f"""
*Yukon run {name} finished:*
- Config:
  - Benchmark: {benchmark_name}
  - Runtime Config: {runtime_config}
  - Run Name: {run_name}
  - FPGA Config: {fpga_config}
- Host walltime: {host_walltime:.2f}s
- Sim walltime: {rawac['seconds'].iloc[-1]}s
- Date: {START_DATE}
- Log Dir: {result_dir}

Command:
```
{cmd}
```
  """
  subprocess.Popen(["/tank/project/yukon/send-message", telegram_message], shell=False).wait()

  return df





run_command(args.name, command, args.dir, hue=args.hue)

exit()