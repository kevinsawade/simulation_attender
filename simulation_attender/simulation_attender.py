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

import os
import warnings
from datetime import datetime, date
from enum import Enum
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
from imohash import hashfile
from pandas import DataFrame
from rich_dataframe import prettify

warnings.simplefilter(action="ignore", category=pd.errors.PerformanceWarning)

################################################################################
# Gobals
################################################################################


__version__ = "0.0.1"


__all__ = ["cli", "get_db"]


JOB_TEMPLATE="""\
#!/bin/bash
#SBATCH --chdir={{ directory }}
#SBATCH --export=NONE
#SBATCH --mail-user={{ email }}
#SBATCH --mail-type=BEGIN,END

{{ module_loads }}

cd {{ directory }}

{{ command }}

"""


################################################################################
# Helper Classes
################################################################################


@total_ordering
class SimState(Enum):
    CRASHED = -2
    SETUP = -1
    TEMPLATED = 0
    ENQUEUED = 1
    RUNNING = 2
    FINISHED = 3

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

    def __init__(
        self,
        *pathsegments,
        db_file: Optional[Path] = None,
        sim_hash: Optional[str] = None,
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
                if self.hash != files.loc[str(self)]["hash"]:
                    raise Exception(
                        f"File {self} has changed on disk since last "
                        f"checking on {self.df['last_checked_time']}. Use the "
                        f"parent simulation {self.df['sim_hash']} to update "
                        f"this file. Use `rr.Simulation.from_database("
                        f"{self.df['sim_hash']})` to reload this sim."
                    )
                else:
                    sim_hash = files.loc[str(self)]["sim_hash"]
                    if sim_hash != self.sim_hash:
                        raise Exception(f"This file was associated with a different sim: "
                                        f"{sim_hash[:7]}. Please use this sim to manipulate "
                                        f"this file")
                    self.sim_hash = sim_hash
        super().__init__()

    @classmethod
    def from_series(cls, series: pd.Series, db_file:Path):
        new_class = cls(series.name, db_file=db_file, sim_hash=series["sim_hash"])
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
                "time_last_checked": datetime.now(),
                "sim_hash": self.sim_hash
            }
        )
        series.name = str(self)
        series = series.to_frame().T
        files = pd.concat([files, series], axis="rows")
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

    def unlink(self):
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
            [int(i) for i in series["jobids"].split(", ")] if series["jobids"] != "" else None,
        )

    @property
    def directory(self) -> Path:
        return self.tpr_file.parent

    @property
    def in_database(self) -> bool:
        _, sims = get_db(self.db_file)
        return self.hash in sims.index

    def to_database(self) -> None:
        files, sims = get_db(self.db_file)
        series = pd.Series(
            {
                "tpr_file": str(self.tpr_file),
                "time_added": self.instantiation_time,
                "time_last_checked": datetime.now(),
                "state": str(self.state),
                "jobids": ", ".join(self.job_ids),
            }
        )
        series.name = self.hash
        series = series.to_frame().T
        sims = pd.concat([sims, series], axis="rows")
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
                "time_last_checked": [],
                "sim_hash": [],
            }
        )
        files = files.astype(
            {
                "file": str,
                "hash": str,
                "time_added": "datetime64[ns]",
                "time_last_checked": "datetime64[ns]",
                "sim_hash": str,
            }
        )
        files = files.set_index("file")
        sims = pd.DataFrame(
            {
                "tpr_file": [],
                "time_added": [],
                "time_last_checked": [],
                "state": [],
                "jobids": [],
            }
        )
        sims = sims.astype(
            {
                "tpr_file": str,
                "time_added": "datetime64[ns]",
                "time_last_checked": "datetime64[ns]",
                "state": str,
                "jobids": str,
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
                f"simulation_attender.py list can take IDENTIFIER arguments like: "
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
    if identifier == "tail":
        sims = sims.tail(int(n))
        sims.index = sims.index.str[:7]
        sims.index.name = "id"
    elif identifier == "head":
        sims = sims.head(int(n))
        sims.index = sims.index.str[:7]
        sims.index.name = "id"
    elif identifier == "slice":
        ind = slice(*map(lambda x: int(x.strip()) if x.strip() else None, n.split(':')))
        sims = sims.iloc[ind]
        sims.index = sims.index.str[:7]
        sims.index.name = "id"
    elif identifier in sims.index.str[:7] or identifier in sims.index.str[:7]:
        sims.index = sims.index.str[:7]
    else:
        try:
            identifier = magicdate.magicdate(identifier)
            if isinstance(identifier, date):
                identifier = datetime.combine(identifier, datetime.min.time())
            sims = sims[sims["time_added"] > identifier]
        except:
            click.echo(
                f"simulation_attender.py list can take IDENTIFIER arguments like: "
                f"'tail -n 20', or 'today', or '1 week ago'. The argument "
                f"you provided '{identifier}' could not be understood."
            )
            return pd.DataFrame({})
    if print_df:
        prettify(sims)
    return sims


@click.argument(
    "identifier",
    required=True,
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
    identifier = ("today",) if not identifier else identifier

    # get sims to template
    sims_to_template = _list_sims(ctx, identifier, n, db_file, print_df=False)
    if sims_to_template.size == 0:
        click.echo(
            f"simulation_attender.py template can take IDENTIFIER arguments like: "
            f"'tail -n 20', or 'today', or '1 week ago'. The argument "
            f"you provided '{identifier}' does not return any sims."
        )
        return 1

    # prepare the template
    if not template_file:
        template = jinja2.Template(JOB_TEMPLATE, undefined=jinja2.StrictUndefined)
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
        rendered_text = template.render(template_dict)
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
    for tpr_file in tpr_files:
        sim = Simulation(tpr_file, db_file)
        if not sim.in_database:
            sim.to_database()
            tpr_file.sim_hash = sim.hash
            tpr_file.db_file = db_file
            tpr_file.to_database()
            collected_sims += 1

    if collected_sims > 0:
        click.echo(f"Collected {collected_sims} new tpr files.")
    else:
        click.echo(f"There were no tpr files in the directory {start_dir}.")
    return 0


@cli.command(help="Checks currently running sims and prints info about them.")
@click.pass_context
def check(
        ctx: click.Context,
) -> int:
    raise NotImplementedError


################################################################################
# Execution
################################################################################


if __name__ == "__main__":
    raise SystemExit(cli())
