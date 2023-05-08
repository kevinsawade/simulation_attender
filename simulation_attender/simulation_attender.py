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
# Helper Classes
################################################################################


@total_ordering
class SimState(Enum):
    ENQUEUED = 0
    RUNNING = 2
    FINISHED = 3
    CRASHED = -1

    def __str__(self):
        return self.name

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented


class LocalFile(type(Path())):
    """Representation of a file in running_rabbit.

    Generally, it is not advised to use this class, as it just is a helper class
    for the larger Simulation and Stage classes.

    Files need to be stored in the database to associate them with their
    respective simulations and check if they have changed by external programs
    like `gmx mdrun` or SLURM, MOAB job schedulers.

    This is a subclass of pathlib.Path and can be used accordingly. Some changes
    need to be considered:
        * A running_rabbit File can not be moved beyond its parent simulation
            directory. Use simulation.move for that operation.
        * Renaming a running_rabbit File with the `rename()` method doesn't take
            a full path specifier, but just the new filename. The `rename()`
            method also makes sure not to overwrite existing files but rather
            move them to a back-upped copy.
        * Files can be pushed and rebuilt from the database.

    """
    def __init__(self,
                 *pathsegments,
                 sim_hash=None,
                 notes=None,
                 parent_sim=None,
                 stdout="",
                 stderr="",
                 ):
        self.instantiation_time = get_iso8601_datetime()
        self.notes = Notes(notes, parent_class=self)
        self.stdout = stdout
        self.stderr = stderr
        self.sim_hash = sim_hash
        self.parent_sim = parent_sim

        # some checks
        if not self.exists():
            import errno
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), (f"`running_rabbit."
                f"{self.__class__.__name__}` only handles existing files. The "
                f"file {Path(*pathsegments)} does not exist."))

        if self.is_dir():
            import errno
            raise IsADirectoryError(
                errno.EISDIR, os.strerror(errno.EISDIR), (f"`running_rabbit."
                f"{self.__class__.__name__}` only handles files. The "
                f"path {Path(*pathsegments)} is a directory."))

        # check database for duplicate
        if self.in_database:
            if self.hash != self.df['hash']:
                raise Exception(f"File {self} has changed on disk since last "
                                f"checking on {self.df['last_checked_time']}. Use the "
                                f"parent simulation {self.df['sim_hash']} to update "
                                f"this file. Use `rr.Simulation.from_database("
                                f"{self.df['sim_hash']})` to reload this sim.")
            else:
                logger.info(f"Reloading the file {self} form the database.")
                self._notes = self.df['notes'] + self.notes
                self.sim_hash = self.df['sim_hash']
        super().__init__()

    @property
    def hash(self):
        return hash_files(self, force_imohash=True)[str(self)]['imohash']

    @property
    def in_database(self):
        return False
        # return file_in_db(self)

    @property
    def df(self):
        return pd.Series({'hash': '123'})
        # return series_from_filename(str(self))

    def to_database(self):
        raise Exception("LocalFile does not talk to the database")
        if self.sim_hash is None:
            raise Exception("This file is not associated to a simulation and thus "
                            "can't be pushed to the database.")
        self.last_checked_time = get_iso8601_datetime()
        add_file_to_db(self)

    def rename(self, target, backup=False):
        self_basedir = self.parent
        if os.path.isdir(target):
            if self_basedir != os.path.dirname(target):
                raise Exception("Running_rabbit.File can't be moved beyond the "
                                "directory boundaries.")
        else:
            target = self.parent / target

        if target.exists():
            if not backup:
                raise Exception(f"File at {target} already exists. Set `backup` "
                                f"to True to rename the file and keep a backup "
                                f"of {target}.")
            new_target = target.parent / (target.name + '.bak')
            new_target = advance_file_counter(new_target)
            shutil.move(target, new_target)

        # move in the database
        if self.in_database:
            rename_file(self, target)

        # execute super
        newclass = super().rename(target=target)
        newclass.sim_hash = self.sim_hash
        newclass.notes = self.notes
        return newclass

    def replace(self, target):
        raise NotImplementedError("Disallow movement beyond the sim_dir and check for updates.")
        super().replace(target=target)

    def unlink(self):
        raise Exception(f"Can't unlink with `running_rabbit."
                        f"{self.__class__.__name__}. Use `simulation.delete` instead.")

    def rmdir(self):
        raise Exception(f"Can't rmdir with `running_rabbit.{self.__class__.__name__}`.")

    def touch(self, mode=438, exist_ok=True):
        raise Exception(f"Touch not permitted with `running_rabbit."
                        f"{self.__class__.__name__}`.")

    def symlink_to(self, target, target_is_directory=False):
        raise Exception("symlink and wait for finished download to unlink.")


################################################################################
# Helper Functions
################################################################################


def get_db(db_file: str) -> tuple(pd.DataFrame):
    if not Path(db_file).is_file():
        files = pd.DataFrame({
            "file": [],
            "hash": [],
            "sim_hash": [],
        })
        sims = pd.DataFrame({
            'sim_dir': [],
            'name': [],
            'state': [],
            'jobid': [],
        })
        return files, sims


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
def cli(
        debug: bool,
        start_dir: str,
) -> int:
    click.echo(f"Debug mode is {'on' if debug else 'off'}")
    return 1


################################################################################
# Commands
################################################################################


@cli.command(help="Collect .tpr files from a starting_directory.")
@click.argument(
    "start-dir",
    required=False,
)
@click.option(
    '-db',
    '--database-file',
    'db_file',
    default='sims.h5',
    type=str,
    help='The database file to read or create',
)
def collect(
        start_dir: str,
        db_file: str,
) -> int:
    click.echo(f'Collecting simulations in {start_dir}')
    files, sims = get_db(db_file)
    return 0


################################################################################
# Execution
################################################################################


if __name__ == '__main__':
    raise SystemExit(cli())