#!/usr/bin/env python

# Copyright (C) Kevin Sawade
# GNU Lesser General Public License v3.0
"""Simulation Attender

attends simulations on HPC clusters.

"""


################################################################################
# Imports
################################################################################


from __future__ import annotations
from typing import Union, Optional, List, Sequence, Any
import numpy as np
from pathlib import Path
import pandas as pd
from time import sleep
import click
import jinja2
from enum import Enum
from functools import total_ordering
from subprocess import Popen, PIPE, run
from io import StringIO
import warnings

warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)


################################################################################
# Gobals
################################################################################


__version__ = "0.0.1"


################################################################################
# Helper Functions
################################################################################


def get_db(db_file: str) -> tuple(pd.DataFrame):
    pass


################################################################################
# Main
################################################################################


@click.group()
@click.option(
    "-D",
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug mode",
)
@click.version_option(__version__, "-v", "--version")
@click.argument(
    "start-dir",
    required=False,
    type=str,
)
def cli(
        debug: bool,
        start_dir: int,
) -> int:
    click.echo(f"Debug mode is {'on' if debug else 'off'}")
    return 1


################################################################################
# Commands
################################################################################


@cli.command(help="Collect .tpr files from a starting_directory.")
def collect(start_dir: str) -> int:
    click.echo(f'Collecting simulations in {start_dir}')
    return 0


################################################################################
# Execution
################################################################################


if __name__ == '__main__':
    raise SystemExit(cli())