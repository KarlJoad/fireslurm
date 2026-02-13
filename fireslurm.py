#!/usr/bin/env python3

import os
import sys

from fireslurm.__main__ import main

if __name__ == "__main__":
    main()
else:
    print(f"You must use {__file__} as a script!", file=sys.stderr)
    exit(os.EX_USAGE)
