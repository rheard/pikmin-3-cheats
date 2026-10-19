"""The command line: `python -m cheats <Pikmin 3 Deluxe RomFS> <Pikmin 3 Deluxe ExeFS>`."""

from __future__ import annotations

import argparse
import logging
import sys

from pathlib import Path

import cheats

OUT = Path("build")  # the folder the two mod folders are written into when none is named


def main() -> None:
    """Build the mod from the files named on the command line."""
    parser = argparse.ArgumentParser(prog="python -m cheats", description=cheats.__doc__.strip().splitlines()[0])
    parser.add_argument("romfs", type=Path, help="the RomFS extracted from your copy of Pikmin 3 Deluxe")
    parser.add_argument("exefs", type=Path, help="the ExeFS extracted from it (or the file main in it)")
    parser.add_argument("-o", "--out", type=Path, default=OUT, help=f"where to write the mod folders (default: {OUT})")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        cheats.build(args.romfs, args.exefs, args.out)
    except (OSError, ValueError) as error:  # a file that is missing, or is not what it should be
        sys.exit(f"The mod could not be built: {error}")


if __name__ == "__main__":
    main()
