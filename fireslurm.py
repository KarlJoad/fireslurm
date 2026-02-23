#!/usr/bin/env python3

import os
import sys
from pathlib import Path

# Add fireslurm's src directory to PYTHONPATH
src_path = str(Path(__file__).parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from fireslurm.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
else:
    print(f"You must use {__file__} as a script!", file=sys.stderr)
    exit(os.EX_USAGE)
