#!/usr/bin/env python
# -*- coding: utf-8 -*-

################################################################################
# simulation_attender.py attends simulations on HPC clusters
#
# Copyright 2019-2022 University of Konstanz and the Authors
#
# Authors:
# Kevin Sawade
#
# cleanup_sims.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 2.1
# of the License, or (at your option) any later version.
# This package is distributed in the hope that it will be useful to other
# researches. IT DOES NOT COME WITH ANY WARRANTY WHATSOEVER; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU Lesser General Public License for more details.
#
# See <http://www.gnu.org/licenses/>.
################################################################################
"""# simulation_attender.py

Attends GROMACS simulations on HPC clusters.

Simulation attender works with these cluster management systems::

* slurm
* moab
* oracle gridengine

Can also be used to track local simulations.

Coverage and Unittest Report
----------------------------

Access the coverage report under:

https://kevinsawade.github.io/simulation_attender/htmlcov/index.html

Access the unittest report under:

https://kevinsawade.github.io/simulation_attender/htmlcov/html_report.html

"""

################################################################################
# Imports
################################################################################


from __future__ import annotations

import os
import shlex
import shutil
import warnings
from copy import deepcopy
from datetime import datetime, date
from enum import Enum, EnumMeta
from functools import total_ordering
from hashlib import md5
from io import StringIO
from pathlib import Path
from subprocess import PIPE, Popen, run
from time import sleep
from typing import Any, List, Optional, Sequence, Tuple, Union

import click
import jinja2
import magicdate
import numpy as np
import pandas as pd
import sys
from imohash import hashfile
from pandas import DataFrame
from rich_dataframe import prettify
from click.testing import CliRunner

warnings.simplefilter(action="ignore", category=pd.errors.PerformanceWarning)

################################################################################
# Gobals
################################################################################


__version__ = "0.0.1"
__all__ = ["cli", "get_db"]
_dryrun = True
_this_module = sys.modules[__name__]

MAX_UNDO = 5


JOB_TEMPLATE = """\
#!/bin/bash
#SBATCH --chdir={{ directory }}
#SBATCH --export=NONE
#SBATCH --mail-user={{ email }}
#SBATCH --mail-type=BEGIN,END

{{ module_loads }}

cd {{ directory }}

{{ command }}

"""

LOCAL_BATCH = """\
#!/bin/bash

cd {{ directory }}

{{ command }} 2> proc.err 1> proc.out &
CMD_PID=$!
echo $CMD_PID

"""


################################################################################
# Helper Classes
################################################################################



class Capturing(list):
    """Class to capture print statements from function calls.

    Examples:
        >>> # write a function
        >>> def my_func(arg='argument'):
        ...     print(arg)
        ...     return('fin')
        >>> # use capturing context manager
        >>> with Capturing() as output:
        ...     my_func('new_argument')
        >>> print(output)
        ['new_argument', "'fin'"]

    """

    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = StringIO()
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        del self._stringio  # free up some memory
        sys.stdout = self._stdout


class MetaEnum(EnumMeta):
    def __contains__(cls, item):
        try:
            cls(item)
        except ValueError:
            return False
        return True


class BaseEnum(Enum, metaclass=MetaEnum):
    pass


@total_ordering
class SimState(BaseEnum):
    CRASHED = -2
    SETUP = -1
    TEMPLATED = 0
    ENQUEUED = 1
    RUNNING = 2
    FINISHED = 3
    ORPHANED = 4

    def __str__(self):
        return self.name

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented


class LocalManager:
    @property
    def sims(self) -> pd.DataFrame:
        ps = Popen("ps -e | grep gmx", shell=True, stdout=PIPE)
        procs = ps.stdout.read().decode().splitlines()
        df = pd.DataFrame({}, columns=["jobid", "tty", "time", "cmd"])
        series = []
        for line in procs:
            data = line.split()
            series.append({
                "jobid": int(data[0]),
                "tty": data[1],
                "time": data[2],
                "cmd": data[3],
            })
        if len(series) == 0:
            return df
        df = pd.DataFrame.from_records(series)
        return df

    def submit(self, sim: Simulation) -> int:
        cmd = f"bash {sim.directory}/job.sh"
        proc = Popen(shlex.split(cmd), stdout=PIPE, stderr=PIPE)
        out, err = proc.communicate()
        pid = int(out.decode())
        sim.job_ids.append(pid)
        sim.state = SimState.ENQUEUED
        sim.to_database()
        return pid

    def cancel(self):
        raise NotImplementedError

    def out_file(self, sim: Simulation) -> str:
        return (Path(sim.directory) / "proc.out").read_text()

    def err_file(self, sim: Simulation) -> str:
        return (Path(sim.directory) / "proc.err").read_text()


class SlurmClusterManager:
    @property
    def sims(self) -> pd.DataFrame:
        cmd = "squeue"
        proc = run(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        out = proc.stdout.splitlines()[1:]
        df = pd.DataFrame({}, columns=['jobid', 'partition', 'name', 'user', 'state', 'time', 'nodes', 'nodelist'])
        if not out:
            return df
        series = []
        for line in out:
            data = line.split(None, 7)
            series.append({'jobid': int(data[0]),
                           'partition': data[1],
                           'name': data[2],
                           'user': data[3],
                           'state': data[4],
                           'time': data[5],
                           'nodes': data[6],
                           'nodelist': data[7],
                           })
        df = pd.DataFrame.from_records(series)
        return df

    def submit(self):
        cmd = "sbatch"
        raise NotImplementedError

    def cancel(self):
        cmd = "scancel"
        raise NotImplementedError

    def out_file(self, sim: Simulation) -> str:
        return (Path(sim.directory) / f"slurm-{sim.job_ids[-1]}.out").read_text()

    def err_file(self, sim: Simulation) -> str:
        return (Path(sim.directory) / f"slurm-{sim.job_ids[-1]}.err").read_text()


class GridEngineClusterManager:
    @property
    def sims(self) -> pd.DataFrame:
        import getpass
        username = getpass.getuser()
        cmd = f"qstat -u {username}"
        proc = run(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        df = pd.DataFrame({}, columns=['jobid', 'username', 'queue', 'jobname', 'sessId', 'NDS', 'TSK', 'req_memory',
                                       'req_time', 'S', 'elap_time'])
        #                                                                                   Req'd       Req'd       Elap
        # Job ID                  Username    Queue    Jobname          SessID  NDS   TSK   Memory      Time    S   Time
        if not proc.stdout:
            return df
        out = proc.stdout.splitlines()[5:]
        series = []
        for line in out:
            data = line.split(None, 10)
            series.append({'jobid': int(data[0]),
                           'username': data[1],
                           'queue': data[2],
                           'jobname': data[3],
                           'sessId': data[4],
                           'NDS': data[5],
                           'TSK': data[6],
                           'req_memory': data[7],
                           'req_time': data[8],
                           'S': data[9],
                           'elap_time': data[10],
                           })
        df = pd.DataFrame.from_records(series)
        return df

    def submit(self):
        cmd = "qsub"
        raise NotImplementedError

    def cancel(self):
        cmd = "qdel"
        raise NotImplementedError


class MOABClusterManager:
    @property
    def sims(self) -> pd.DataFrame:
        cmd = "showq"
        raise NotImplementedError

    def submit(self):
        cmd = "msub"
        raise NotImplementedError

    def cancel(self):
        cmd = "canceljob"
        raise NotImplementedError


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

    def __init__(
        self,
        *pathsegments,
        db_file: Optional[Path] = None,
        sim_hash: Optional[str] = None,
        update: bool = False,
    ):
        self.instantiation_time = datetime.now()
        self.db_file = db_file
        self.sim_hash = sim_hash

        # some checks
        if not self.exists():
            import errno

            raise FileNotFoundError(
                errno.ENOENT,
                os.strerror(errno.ENOENT),
                (
                    f"`running_rabbit."
                    f"{self.__class__.__name__}` only handles existing files. The "
                    f"file {Path(*pathsegments)} does not exist."
                ),
            )

        if self.is_dir():
            import errno

            raise IsADirectoryError(
                errno.EISDIR,
                os.strerror(errno.EISDIR),
                (
                    f"`running_rabbit."
                    f"{self.__class__.__name__}` only handles files. The "
                    f"path {Path(*pathsegments)} is a directory."
                ),
            )

        # check database for duplicate
        if self.db_file is not None:
            if self.in_database:
                files, _ = get_db(self.db_file)
                if self.hash != files.loc[str(self)]["hash"] and not update:
                    raise Exception(
                        f"File {self} has changed on disk since last checking. Use the "
                        f"parent simulation to update his file."
                    )
        super().__init__()

    @classmethod
    def from_series(cls, series: pd.Series, db_file: Path, update: bool = False):
        new_class = cls(series.name, db_file=db_file, sim_hash=series["sim_hash"], update=update)
        new_class.instantiation_time = series["time_added"]
        return new_class

    @property
    def hash(self):
        return hash_files(self)[0]

    @property
    def in_database(self):
        if self.db_file is None:
            raise Exception("Set the `db_file` attribute of this file to check.")
        files, _ = get_db(self.db_file)
        return str(self) in files.index

    def to_database(self):
        if self.sim_hash is None:
            raise Exception(
                "This file is not associated to a simulation and thus "
                "can't be pushed to the database."
            )
        files, sims = get_db(self.db_file)
        series = pd.Series(
            {
                "hash": self.hash,
                "time_added": self.instantiation_time,
                "last_time_checked": datetime.now(),
                "sim_hash": self.sim_hash
            }
        )
        series.name = str(self)
        if self.in_database:
            files.at[str(self)] = series
        else:
            files = pd.concat([files, series.to_frame().T], axis="rows")
        store_dfs_to_hdf5(self.db_file, files, sims)

    def rename(self, target, backup=False):
        self_basedir = self.parent
        if os.path.isdir(target):
            if self_basedir != os.path.dirname(target):
                raise Exception(
                    "Running_rabbit.File can't be moved beyond the "
                    "directory boundaries."
                )
        else:
            target = self.parent / target

        if target.exists():
            if not backup:
                raise Exception(
                    f"File at {target} already exists. Set `backup` "
                    f"to True to rename the file and keep a backup "
                    f"of {target}."
                )
            new_target = target.parent / (target.name + ".bak")
            new_target = advance_file_counter(new_target)
            shutil.move(target, new_target)

        # move in the database
        if self.in_database:
            rename_file(self, target)

        # execute super
        newclass = super().rename(target=target)
        newclass.sim_hash = self.sim_hash
        return newclass

    def replace(self, target):
        raise NotImplementedError(
            "Disallow movement beyond the sim_dir and check for updates."
        )
        # super().replace(target=target)

    def unlink(self, **kwargs):
        raise Exception(
            f"Can't unlink with `running_rabbit."
            f"{self.__class__.__name__}. Use `simulation.delete` instead."
        )

    def rmdir(self):
        raise Exception(f"Can't rmdir with `running_rabbit.{self.__class__.__name__}`.")

    def touch(self, mode=438, exist_ok=True):
        raise Exception(
            f"Touch not permitted with `running_rabbit." f"{self.__class__.__name__}`."
        )

    def symlink_to(self, target, target_is_directory=False):
        raise Exception("symlink and wait for finished download to unlink.")


class Simulation:
    def __init__(
        self,
        tpr_file: Path,
        db_file: Path,
        state: str = "SETUP",
        instantiation_time: Optional[datetime] = None,
        job_ids: Optional[list[int]] = None,
    ) -> None:
        self.tpr_file = tpr_file
        self.state = SimState[state]
        if instantiation_time is None:
            self.instantiation_time = datetime.now()
        else:
            self.instantiation_time = instantiation_time
        if job_ids is None:
            self.job_ids = []
        else:
            self.job_ids = job_ids
        self.db_file = db_file

    @classmethod
    def from_hash(cls, hash: str, db_file: Path):
        _, sims = get_db(db_file)
        series = sims.loc[hash]
        return cls.from_series(series, db_file)

    @classmethod
    def from_series(cls, series: pd.Series, db_file: Path):
        return cls(
            Path(series["tpr_file"]),
            db_file,
            series["state"],
            series["time_added"],
            [int(i) for i in series["job_ids"].split(", ")] if series["job_ids"] != "" else None,
        )

    @property
    def directory(self) -> Path:
        return self.tpr_file.parent

    @property
    def in_database(self) -> bool:
        _, sims = get_db(self.db_file)
        return self.hash in sims.index

    def update_files(self) -> None:
        files, _ = get_db(self.db_file)
        for i, row in files[files["sim_hash"] == self.hash].iterrows():
            file = LocalFile.from_series(row, self.db_file, update=True)
            file.to_database()

    def to_database(self) -> None:
        files, sims = get_db(self.db_file)
        series = pd.Series(
            {
                "tpr_file": str(self.tpr_file),
                "time_added": self.instantiation_time,
                "state": str(self.state),
                "last_time_checked": datetime.now(),
                "job_ids": ", ".join(map(str, self.job_ids)),
            }
        )
        series.name = self.hash
        if self.in_database:
            sims.at[self.hash] = series
        else:
            sims = pd.concat([sims, series.to_frame().T], axis="rows")
        store_dfs_to_hdf5(self.db_file, files, sims)

    @property
    def hash(self) -> str:
        return md5(str(self.tpr_file).encode()).hexdigest()

    @property
    def id(self) -> str:
        return self.hash[:7]

    @property
    def files(self) -> list[LocalFile]:
        files, _ = get_db(self.db_file)
        files_out = []
        for i, row in files[files["sim_hash"] == self.hash].iterrows():
            file = LocalFile.from_series(row, self.db_file)
            files_out.append(file)
        return files_out

    def __str__(self):
        return (
            f"Simulation using tpr_file: {self.tpr_file}, at state "
            f"{self.state}, with id {self.id}, "
            f"instantiated at "
            f"{self.instantiation_time.replace(microsecond=0).isoformat()}"
        )


################################################################################
# Helper Functions
################################################################################


def get_iso8601_datetime() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _get_cluster_manager() -> SlurmClusterManager | GridEngineClusterManager | MOABClusterManager:
    # decide on slurm or moab
    slurm_proc = run("squeue", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
    grid_engine_proc = run("qstat", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
    moab_proc = run("msub", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
    if "not found" not in slurm_proc.stderr:
        return SlurmClusterManager()
    elif "not found" not in grid_engine_proc.stderr:
        return GridEngineClusterManager()
    elif "not found" not in moab_proc.stderr:
        return MOABClusterManager()
    else:
        raise Exception("Could not determine the workload manager. Neither `squeue` (slurm) or `qstat` (moab) seems to work.")


def hash_files(*files):
    return [hashfile(str(file), hexdigest=True) for file in files]


def store_dfs_to_hdf5(
    hdf5_file: Path,
    files: pd.DataFrame,
    sims: pd.DataFrame,
) -> None:
    store = pd.HDFStore(hdf5_file)
    store["sims"] = sims
    store["files"] = files
    store.close()


def load_dfs_from_hdf5(hdf5_file: Path) -> tuple[DataFrame, DataFrame]:
    files = pd.read_hdf(hdf5_file, "files")
    sims = pd.read_hdf(hdf5_file, "sims")
    return files, sims


def get_db(db_file: Path) -> tuple[DataFrame, DataFrame]:
    if not Path(db_file).is_file():
        files = pd.DataFrame(
            {
                "file": [],
                "hash": [],
                "time_added": [],
                "last_time_checked": [],
                "sim_hash": [],
            }
        )
        files = files.astype(
            {
                "file": str,
                "hash": str,
                "time_added": "datetime64[ns]",
                "last_time_checked": "datetime64[ns]",
                "sim_hash": str,
            }
        )
        files = files.set_index("file")
        sims = pd.DataFrame(
            {
                "tpr_file": [],
                "time_added": [],
                "last_time_checked": [],
                "state": [],
                "job_ids": [],
            }
        )
        sims = sims.astype(
            {
                "tpr_file": str,
                "time_added": "datetime64[ns]",
                "last_time_checked": "datetime64[ns]",
                "state": str,
                "job_ids": str,
            }
        )
        sims.index.name = "hash"
        sims = sims.sort_values(by="time_added")
        store_dfs_to_hdf5(db_file, files, sims)
        return files, sims
    else:
        return load_dfs_from_hdf5(db_file)


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
@click.pass_context
def cli(
    ctx: click.Context,
    debug: bool,
) -> int:
    ctx.ensure_object(dict)
    ctx.obj["DEBUG"] = debug
    if debug:
        click.echo(f"Running in debug mode. Printing additional info.")
    return 1


################################################################################
# Commands
################################################################################


@click.argument(
    "identifier",
    required=False,
    nargs=-1,
    type=click.UNPROCESSED,
)
@click.option(
    "-n",
    required=False,
    default="10",
)
@click.option(
    "-db",
    "--database-file",
    "db_file",
    default="sims.h5",
    type=str,
    help="The database file to read or create",
)
@cli.command(name="files", help="List files in the database.")
@click.pass_context
def list_files(
        ctx: click.Context,
        identifier: Optional[list[str]] = None,
        n: str = "10",
        db_file: Path = Path("sims.h5"),
) -> pd.DataFrame:
    if identifier[0] == "-h" or identifier[0] == "--help":
        click.echo(ctx.get_help())
        return 0
    if not identifier:
        identifier = ("today", )
    db_file = Path(db_file)
    files, _ = get_db(db_file)
    identifier = " ".join(identifier)
    if identifier == "tail":
        files = files.tail(int(n))
    elif identifier == "head":
        files = files.head(int(n))
    elif identifier in files.index.str[:7]:
        pass
    else:
        try:
            identifier = magicdate.magicdate(identifier)
            if isinstance(identifier, date):
                identifier = datetime.combine(identifier, datetime.min.time())
            files = files[files["time_added"] > identifier]
        except:
            click.echo(
                f"simulation_attender.py files can take IDENTIFIER arguments like: "
                f"'tail -n 20', or 'today', or '1 week ago'. The argument "
                f"you provided '{identifier}' could not be understood."
            )
            return pd.DataFrame({})
    prettify(files)


@click.argument(
    "identifier",
    required=False,
    nargs=-1,
    type=click.UNPROCESSED,
)
@click.option(
    "-n",
    required=False,
    default="10",
)
@click.option(
    "-db",
    "--database-file",
    "db_file",
    default="sims.h5",
    type=str,
    help="The database file to read or create",
)
@cli.command(
    name="list",
    help="List simulations in the database.",
    context_settings=dict(
            ignore_unknown_options=True,
            allow_extra_args=True,
    )
)
@click.pass_context
def list_sims(
    ctx: click.Context,
    identifier: Optional[list[str]] = None,
    n: str = "10",
    db_file: Path = Path("sims.h5"),
) -> pd.DataFrame:
    if not identifier:
        identifier = ("today", )
    else:
        if identifier[0] == "-h" or identifier[0] == "--help":
            click.echo(ctx.get_help())
            return 0
        if identifier[0] == "slice":
            n = "".join(identifier[1:])
            identifier = ("slice", )
    return _list_sims(ctx, identifier, n, db_file, print_df=True)


def _list_sims(
    ctx: click.Context,
    identifier: tuple[str],
    n: str = "10",
    db_file: Path = Path("sims.h5"),
    print_df: bool = True,
) -> pd.DataFrame:
    db_file = Path(db_file)
    _, sims = get_db(db_file)
    identifier = " ".join(identifier)
    all_job_ids = [i for j in sims["job_ids"] for i in list(map(str, j.split(".")))]
    all_job_ids = list(filter(lambda x: bool(x), all_job_ids))
    if identifier == "tail":
        sims = sims.tail(int(n))
    elif identifier == "head":
        sims = sims.head(int(n))
    elif identifier == "slice":
        ind = slice(*map(lambda x: int(x.strip()) if x.strip() else None, n.split(':')))
        click.echo(ind)
        sims = sims.iloc[ind]
    elif identifier in sims.index.str[:7] or identifier in sims.index.str[:7]:
        sims.index = sims.index.str[:7]
    elif identifier.upper() in SimState.__members__:
        sims = sims[sims["state"] == identifier.upper()]
    elif identifier in all_job_ids:
        raise Exception("Accessing simulation by job_id currently not possible.")
    else:
        try:
            identifier = magicdate.magicdate(identifier)
            if isinstance(identifier, date):
                identifier = datetime.combine(identifier, datetime.min.time())
            sims = sims[sims["time_added"] > identifier]
        except:
            click.echo(f"{identifier}, {identifier}, {identifier in SimState}")
            click.echo(
                f"simulation_attender.py list can take IDENTIFIER arguments like: "
                f"'tail -n 20', 'today', '1 week ago', 'setup', 'running', or "
                f"'slice -n -5:'.The argument you provided '{identifier}' "
                f"could not be understood."
            )
            return pd.DataFrame({})
    if print_df:
        sims.index = sims.index.str[:7]
        sims.index.name = "id"
        prettify(sims)
    return sims


@click.argument(
    "identifier",
    required=False,
    nargs=-1,
    type=click.UNPROCESSED,
)
@click.option(
    "-n",
    required=False,
    default="10",
)
@click.option(
    "-db",
    "--database-file",
    "db_file",
    default="sims.h5",
    type=str,
    help="The database file to read or create",
)
@click.option(
    "-t",
    "--template-file",
    "template_file",
    default="",
    type=str,
    help="The template file to fill with values.",
)
@cli.command(
    help="Add job.sh files to sims using a template.",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    ),
)
@click.pass_context
def template(
    ctx: click.Context,
    identifier: Optional[tuple[str]] = None,
    n: str = "10",
    db_file: Path = Path("sims.h5"),
    template_file: str = "",
) -> int:
    # filter list arg
    extra_args = {
        k: v for k, v in zip(identifier[:-1], identifier[1:]) if k.startswith("--")
    }
    dropping_args = {
        k: v
        for k, v in zip(identifier[:-1], identifier[1:])
        if k.startswith("-") and not k.startswith("--")
    }
    if dropping_args:
        click.echo(
            f"Dropping these args, because templating args need two hypens (e.g. '--cmd'):\n"
            f"{dropping_args}"
        )
    args_to_delete = (
        list(extra_args.keys())
        + list(extra_args.values())
        + list(dropping_args.keys())
        + list(dropping_args.values())
    )
    identifier = tuple(filter(lambda x: x not in args_to_delete, identifier))
    extra_args = {k.lstrip("-"): v for k, v in extra_args.items()}
    if identifier == ("-h", ) or identifier == ("--help", ):
        click.echo(ctx.get_help())
        return 0
    identifier = ("setup",) if not identifier else identifier

    # get sims to template
    sims_to_template = _list_sims(ctx, identifier, n, db_file, print_df=False)
    if ctx.obj["DEBUG"]:
        click.echo(f"These sims will be templated: {sims_to_template}")
    if sims_to_template.size == 0:
        click.echo(
            f"simulation_attender.py template can take IDENTIFIER arguments like: "
            f"'tail -n 20', or 'today', or '1 week ago'. The argument "
            f"you provided '{identifier}' does not return any sims."
        )
        return 1

    # prepare the template
    if not template_file:
        try:
            _get_cluster_manager()
            TEMPLATE: str = JOB_TEMPLATE
        except Exception:
            TEMPLATE: str = LOCAL_BATCH
        template = jinja2.Template(TEMPLATE, undefined=jinja2.StrictUndefined)
    else:
        template = jinja2.Template(Path(template_file).read_text(), undefined=jinja2.StrictUndefined)

    for i, row in sims_to_template.iterrows():
        sim = Simulation.from_series(row, db_file)
        if sim.state >= SimState.TEMPLATED:
            continue

        #  prepare the template dict
        template_dict = {'directory': sim.directory.resolve()} | extra_args
        if "email" not in template_dict:
            template_dict["email"] = "no-one@example.com"
        for key, val in template_dict.items():
            if "{{ stem }}" in str(val):
                template_dict[key] = val.replace("{{ stem }}", sim.tpr_file.stem)
        try:
            rendered_text = template.render(template_dict)
        except jinja2.exceptions.UndefinedError as e:
            missing = str(e).split("'")[1]
            msg = (f"The placeholder '{missing}' in the template needs a definition "
                   f"Pass the argument --{missing} to the template call.")
            raise Exception(msg)
        job_file = Path(sim.directory) / "job.sh"
        job_file.write_text(rendered_text)
        job_file = LocalFile(job_file, db_file=db_file, sim_hash=sim.hash)
        job_file.to_database()
        sim.state = SimState["TEMPLATED"]
        sim.to_database()
    return 0


@click.argument(
    "start-dir",
    required=True,
)
@click.option(
    "-db",
    "--database-file",
    "db_file",
    default="sims.h5",
    type=str,
    help="The database file to read or create",
)
@click.option(
    "-s",
    "--skip-conflicts",
    "skip",
    is_flag=True,
    default=False,
    help=("Skip over otherwise conflicting tpr files. Simulation_attender.py can "
         "only track one simulation per directory. This means, that some tpr files won't "
         "be added to the database"),
)
@click.option(
    "-p",
    "--pattern",
    "pattern",
    default="",
    type=str,
    help="A pattern to match agains the files found",
)
@cli.command(help="Collect .tpr files from a starting_directory.")
@click.pass_context
def collect(
    ctx: click.Context,
    start_dir: str,
    pattern: str,
    db_file: str,
    skip: bool = False,
) -> int:
    db_file = Path(db_file)
    start_dir = Path(start_dir).resolve()
    click.echo(f"Collecting simulations in {start_dir}")
    tpr_files = [LocalFile(f) for f in start_dir.rglob(f"**/{pattern}*tpr")]
    click.echo(f"Found {len(tpr_files)} tpr files in {start_dir}")
    if ctx.obj['DEBUG']:
        click.echo("Here are the tpr files:")
        for tpr_file in tpr_files:
            click.echo(str(tpr_file))
    # track collected sims
    collected_sims = 0

    # iterate over tpr files and create simulation objects
    for i, tpr_file in enumerate(tpr_files):
        if ctx.obj['DEBUG']:
            click.echo(f"Adding {tpr_file} to database.")
        sim = Simulation(tpr_file, db_file)
        if not sim.in_database:
            files, _ = get_db(db_file)
            if files.size > 0:
                existing_tpr_files_dirs = set(files.index.str.split("/").str[:-1].str.join("/").tolist())
            else:
                existing_tpr_files_dirs = []
            if str(tpr_file.parent) in existing_tpr_files_dirs and not skip:
                click.echo(f"The database already tracks a tpr file in {tpr_file.parent} "
                           f"Please move {tpr_file} somewhere else; simulation_attender.py "
                           f"can only track one tpr_file per directory.")
                return 3
            elif str(tpr_file.parent) in existing_tpr_files_dirs and skip:
                click.echo(f"Skipping {tpr_file}, because a sim in that directory is already tracked.")
                continue
            sim.to_database()
            tpr_file.sim_hash = sim.hash
            tpr_file.db_file = db_file
            tpr_file.to_database()
            for file in tpr_file.parent.glob("*"):
                if file.is_file():
                    file = LocalFile(file)
                    file.db_file = db_file
                    file.sim_hash = sim.hash
                    file.to_database()
            collected_sims += 1
        else:
            if ctx.obj["DEBUG"]:
                click.echo(f"The file {tpr_file} is already tracked by {sim}.")

    if collected_sims > 0:
        click.echo(f"Collected {collected_sims} new tpr files.")
    else:
        click.echo(f"There were no (new) tpr files in the directory {start_dir}.")
    return 0


@cli.command(help=("Runs enqueued simulations and prints general info. "
                   "It is encouraged to call this function multiple times until "
                   "enqueued sims have concluded."))
@click.option(
    "-db",
    "--database-file",
    "db_file",
    default="sims.h5",
    type=str,
    help="The database file to read or create",
)
@click.option(
    "-cm",
    "--cluster-manager",
    "cluster_manager",
    default="auto",
    type=str,
    help=("The cluster manager to use. Can be 'auto' to detect either slurm, moab, gridengine."
          "Can be 'slurm', 'moab', 'gridengine', or 'local'. If 'local' is "
          "provided, the batch script will be executed as a background process and "
          "the pid will be used as jobid."),
)
@click.pass_context
def run(
    ctx: click.Context,
    db_file: str,
    cluster_manager: str = "auto",
) -> int:
    # get db files
    db_file = Path(db_file)
    check_file = db_file.parent / ("." + db_file.name + "_check.h5")

    # decide on cluster manager
    if cluster_manager == "auto":
        manager = _get_cluster_manager()
    elif cluster_manager == "slurm":
        manager = SlurmClusterManager()
    elif cluster_manager == "moab":
        manager = MOABClusterManager()
    elif cluster_manager == "gridengine":
        manager = GridEngineClusterManager()
    elif cluster_manager == "local":
        manager = LocalManager()
    else:
        raise Exception("cluster_manager must be one of: 'auto', 'slurm', "
                        "'moab', 'cluster_manager', or 'local'.")

    # load dbs
    current_files, current_sims = get_db(db_file)
    last_checked_files, last_checked_sims = get_db(check_file)

    # if new sims print
    added_sims = list(set(current_sims.index) - set(last_checked_sims.index))
    diff_sims = current_sims.loc[list(added_sims)]
    if diff_sims.size > 0:
        click.echo("Since last checking, these sims have been added:")
        for i, diff_sim in diff_sims.iterrows():
            click.echo(str(Simulation.from_series(diff_sim, db_file)))
    else:
        click.echo("Since last checking no sims have been added.")

    # iterate over all ENQUEUED sims and check their state print
    found = False
    resubmit = False
    for i, row in current_sims.iterrows():
        sim = Simulation.from_series(row, db_file=db_file)
        # check whether state has changed
        if i in last_checked_sims.index:
            if (old_state := last_checked_sims.loc[i, "state"]) != row["state"]:
                click.echo(f"Since last checking, the state of sim {i[:7]} has changed "
                           f"from {old_state} to {row['state']}.")
                found = True
        current_state = SimState[row["state"]]

        # do stuff with enqueued sims
        if current_state is SimState.ENQUEUED:
            # check for new files
            new_files = []
            for file in Path(row["tpr_file"]).parent.glob("*"):
                if not file.is_file():
                    continue
                if str(file) not in current_files:
                    file = LocalFile(file, db_file=db_file, sim_hash=sim.hash)
                    file.to_database()
                    new_files.append(file)
            if len(new_files) > 0:
                click.echo(f"In the directory of simulation {sim.id}, {len(new_files)} "
                           f"new files have been created. The simulation changed its "
                           f"state from ENQUEUED to RUNNING.")
                sim.state = SimState.RUNNING
                current_state = SimState.RUNNING
                sim.to_database()
                found = True
            else:
                click.echo(f"The simulation {sim.id} is still enqueued.")

        # do stuff with running
        if current_state is SimState.RUNNING:
            # check whether still running
            if np.isin(np.array(sim.job_ids), manager.sims["jobid"]):
                click.echo(f"Simulation {sim.id} is still running.")
            else:
                click.echo(f"Simulation {sim.id} not running anymore. Checking for completion.")
                # check for completion
                files_ = list(filter(lambda x: x.is_file(), Path(row["tpr_file"]).parent.glob("*")))
                if any([f.suffix == ".gro" for f in files_]):
                    click.echo(f"The simulation {sim.id} has produced a .gro file. "
                               f"It will be marked as finished.")
                    sim.state = SimState.FINISHED
                    sim.to_database()
                    sim.update_files()
                    # for file in files_:
                    #     file = LocalFile(file, db_file=db_file, sim_hash=sim.hash)
                    #     file.to_database()
                    found = True
                    resubmit = True
                else:
                    click.echo(f"Simulation {sim.id} with jobid {sim.job_ids[-1]} "
                               f"not in jobs anymore. Simulation could have crashed. "
                               f"Checking whether any files changed since last checking.")
                    files_, _ = get_db(db_file)
                    sleep(10)
                    for i, row in files_[files_["sim_hash"] == sim.hash].iterrows():
                        file = LocalFile.from_series(row, db_file)
                        if row['hash'] != file.hash:
                            click.echo(f"The files of the simulation are still written to. "
                                       f"I will mark this sim as orphaned. Maybe it will "
                                       f"conclude sometime.")
                            sim.state = SimState.ORPHANED
                            sim.to_database()
                            break
                    else:
                        sim.state = SimState.CRASHED
                        sim.to_database()
                        click.echo(f"The simulation has crashed. No files are written to.")

    if not found:
        click.echo("Since last checking no sims have changed their state.")
    # finally write the new files and sims to the check db
    store_dfs_to_hdf5(check_file, current_files, current_sims)

    if resubmit and cluster_manager == "local":
        click.echo("A local simulation has completed. Submitting the next simulation.")
        _submit(db_file=str(db_file), cluster_manager=cluster_manager)

@click.option(
    "-db",
    "--database-file",
    "db_file",
    default="sims.h5",
    type=str,
    help="The database file to read or create.",
)
@click.option(
    "-max",
    "--max-concurrent-sims",
    "max_concurrent_sims",
    default=50,
    type=int,
    help="The maximum number of concurrent simulations.",
)
@click.option(
    "-cm",
    "--cluster-manager",
    "cluster_manager",
    default="auto",
    type=str,
    help=("The cluster manager to use. Can be 'auto' to detect either slurm, moab, gridengine."
          "Can be 'slurm', 'moab', 'gridengine', or 'local'. If 'local' is "
          "provided, the batch script will be executed as a background process and "
          "the pid will be used as jobid."),
)
@cli.command(help="Submits templated jobs.")
@click.pass_context
def submit(
    ctx: click.Context,
    db_file: str = "sims.h5",
    cluster_manager: str = "auto",
    max_concurrent_sims: int = 50,
) -> int:
    return _submit(db_file, cluster_manager, max_concurrent_sims)


def _submit(
    db_file: str = "sims.h5",
    cluster_manager: str = "auto",
    max_concurrent_sims: int = 50,
) -> int:
    db_file = Path(db_file)
    if cluster_manager == "auto":
        manager = _get_cluster_manager()
    elif cluster_manager == "slurm":
        manager = SlurmClusterManager()
    elif cluster_manager == "moab":
        manager = MOABClusterManager()
    elif cluster_manager == "gridengine":
        manager = GridEngineClusterManager()
    elif cluster_manager == "local":
        manager = LocalManager()
    else:
        raise Exception("cluster_manager must be one of: 'auto', 'slurm', "
                        "'moab', 'cluster_manager', or 'local'.")

    files, sims = get_db(db_file)
    for i, row in sims[sims["state"] == "TEMPLATED"].iterrows():
        number_of_current_sims = len(manager.sims)
        if number_of_current_sims >= max_concurrent_sims:
            click.echo(f"Currently {number_of_current_sims} are submitted or "
                       f"running. I won't submit more than "
                       f"max_concurrent_sims={max_concurrent_sims} simulations.")
        sim = Simulation.from_series(row, db_file=db_file)
        jobid = manager.submit(sim)
        click.echo(f"Submitted sim in {sim.directory} with jobid {jobid}.")

        if isinstance(manager, LocalManager):
            sim.to_database()
            click.echo("I will not run more than one simulation on a local "
                       "machine. Call submit again, when this one is finished.")
            break

    return 0


################################################################################
# Documentation
################################################################################


# add the command line usage
_runner = CliRunner()
_general_help = _runner.invoke(cli, ["--help"]).output
_collect_help = _runner.invoke(cli, ["collect", "--help"]).output
_list_help = _runner.invoke(cli, ["list", "--help"]).output
_template_help = _runner.invoke(cli, ["template", "--help"]).output
_submit_help = _runner.invoke(cli, ["submit", "--help"]).output
_run_help = _runner.invoke(cli, ["run", "--help"]).output
_this_module.__doc__ += f"""# Command line usage:

```raw
{_general_help}
```

## Installation

simulation_attender.py is a monolithic script you just need two files:

- First install the requirements via:

```bash
$ pip install -r https://raw.githubusercontent.com/kevinsawade/simulation_attender/main/requirements.txt
```

- Then get the main file:

```bash
$ wget https://raw.githubusercontent.com/kevinsawade/simulation_attender/main/simulation_attender/simulation_attender.py
```

## Usage

You can call simulation attender from the command line by:

```bash
$ python simulation_attender.py --help
```

Simulation_attender.py stores states of simulations in a file called sims.h5.
This file tracks not only the status of simulations but also all files inside the simulation directories.
This means, that **a simulation needs to be alone in its directory**.

### Collecting simulations

Before you can start managing your simulations with simulation_attender, you need to add them
to the database. That's where the `collect` command comes in. The collect command recourses through
the directory provided as a positional argument (`START_DIR`) and looks for `.tpr` files. These files
are added to the database file, which is standard `sims.h5`, but you can maintain many of these database files.
Normally you only want to call:

```bash
$ python simulation_attender.py collect .
```

You can provide a grep pattern for `-p` to filter the `.tpr` files in `START_DIR`,
to only use certain tpr files (e.g. `"*test*"`, don't forget the quotation marks `"`, as
the bash shell will usually expand the wildcard characters `*` before calling the command):

```bash
$ python simulation_attender.py collect /work_fs/username/workspace -p "*test*"
```

Change the database with the `-db` option:

```bash
$ python simulation_attender.py collect . -db grant1_sims.h5
```

As **there can only be one `.tpr` file per directory** you could run into some
errors, if you have multiple in one directory. If you are sure what you are doing and
only want to run the simulation of one `.tpr` file in the directory, you can skip
these errors with the `-s` flag.

```raw
{_collect_help}
```

### Listing simulations

The `list` command helps you to interact with the simulation database. It can take
a wide variety of inputs to print only the rows you want from the database. The possibilities are::

* `tail`: Print the last 5 rows of the database.
* `tail -n 10`: Print the last 10 rows of the database.
* `head`: Print the first five rows of the database.
* `head -n 10`: Print the first 10 rows of the database.
* `slice ::5`: Print every 5th row of the database.
* `slice -20::3`: Print every 3rd row of the last 20 rows of the datbase.
* `today`: Print simulations, that have been added today.
* `1 week ago`: Print simulations that have been added in the last week.
* More time-selections are available.
* `running`: Print all running simulations.
* `setup`: Print all simulations, currently in the setup stage.
* `1asd4fg`: Print simulation with id `1asd4fg`.

```raw
{_list_help}
```

### Templating simulations

The next step is to create job scripts for the respective simulations. You can
provide a templated job script with the `-t` option. These job scripts should in general
adhere to your cluster's own documentation page and might look like this:

```bash
#!/bin/bash
#SBATCH --chdir=/path/to/sim_dir
#SBATCH --export=NONE
#SBATCH --mail-user=my_mail@university.com
#SBATCH --mail-type=BEGIN,END

module load gromacs/2023.1

gmx_mpi mdrun -deffnm sim
```

or:

```bash
#!/bin/bash
#PBS -l nodes=1:ppn=1
#PBS -l walltime=00:05:00
#PBS -l mem=1gb
#PBS -S /bin/bash
#PBS -N Simple_Script_Job
#PBS -j oe
#PBS -o LOG

cd /path/to/sim_dir

module load gromacs/2023.1

mpirun -n 1 gmx_mpi mdrun -deffnm production
```

However, simulation_attender.py uses the jinja2 templating engine to fill your
job scripts with appropriate values. This is especially because most job scripts contain
a directory that needs to be adjusted for every job. Templates can be written like normal
job scripts, but can contain `{{{{ placeholder }}}}` placeholders, in which the values will
be filled with appropriate values from the simulations. A template can look like this:

```bash
#!/bin/bash
#SBATCH --chdir={{{{ directory }}}}
#SBATCH --export=NONE
#SBATCH --mail-user={{{{ email }}}}
#SBATCH --mail-type=BEGIN,END

{{{{ module_loads }}}}

cd {{{{ directory }}}}

{{{{ command }}}}
```

The following placeholders are available by the simulation::

* `{{{{ directory }}}}`: The directory, where the `.tpr` file is in.
* `{{{{ stem }}}}`: The `stem` of the `.tpr` file (.i.e. for `production.tpr` the stem would be `production`).

If placeholders are not defined simulation_attender will raise an Exception (except for the `{{{{ email }}}}` placeholder).
Placeholder can be filled with arguments to the `template` call, like so:

```bash
$ python simulation_attender.py template --command "gmx mdrun -deffnm {{{{ stem }}}}" --module_loads "module load gromacs/2023.1"
```

The `template` command can also filter simulations like the `list` command. In that case, you could do:

```bash
$ python simulation_attender.py template today -t template_file.sh
```

The template command will create new files called `job.sh` in the respective simulation directories.

```raw
{_template_help}
```

### Submitting

The `submit` command submits templated simulations to the job manager. It can interact with::

* slurm
* moab
* gridengine

cluster management software. The argument `-max` makes `submit` stop, when this number is reached.
This can come in handy, if your cluster allows you to only have X amount of concurrent (pending and running) jobs.
The `submit` command adds the jobid of the simulations to the database.
You can also use simulation_attender.py to run simulations locally. In which
case you should provide `-cm local` ot the `submit` call. Running locally is special, because the maximum
number of concurrent simulations on a local system is 1. The `submit` command also writes a special job file
to the simulation directory (lacking the `SBATCH` or `PBS` declarations) and uses the process' PID as the
jobid of the simulation. Example:

```raw
{_submit_help}
```

### Running

The `run` command of simulation_attender.py is the jack of all trades. It looks through the database and
updates you on your simulations.
"""

################################################################################
# Execution
################################################################################


if __name__ == "__main__":
    raise SystemExit(cli())
