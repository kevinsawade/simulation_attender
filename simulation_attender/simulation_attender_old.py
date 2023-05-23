#!/usr/bin/env python

# Copyright (C) Kevin Sawade
# GNU Lesser General Public License v3.0
"""Simulation Attender

attends simulations on HPC clusters.

"""


###########################################################
# Imports
###########################################################


from __future__ import annotations
from typing import Union, Optional, List, Sequence
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


###########################################################
# Helpers
###########################################################


JOB_TEMPLATE="""\
#!/bin/bash
#SBATCH --chdir={{ directory }}
#SBATCH --partition=single
#SBATCH --gres=gpu:4
#SBATCH --nodes=1
#SBATCH --time=120:00:00
#SBATCH --mem=50gb
#SBATCH --ntasks-per-node=16
#SBATCH --export=NONE
#SBATCH --mail-user=kevin.sawade@uni-konstanz.de
#SBATCH --mail-type=BEGIN,END

{{ module_loads }}


cd {{ directory }}

cmd="{{ command }} -cpo production.cpt"

# cmd="srun gmx_mpi mdrun -deffnm production -rdd 2.0 -c -maxh 23"

if compgen -G "*production*gro*" > /dev/null ; then
    echo "JOB FINISHED"
    exit
fi

# count the number of slurm out files
num=$( ls -1 *out* | wc -l )
if [ $num -gt {{ max_out_files}} ] ; then
    echo "Too many out files exiting."
    exit
fi


if [ ! -e production.cpt ]; then
cp production.cpt production-$( date --iso-8601=seconds ).cpt.back
echo " ### Initial submit. Starting job. ### "
$cmd
else
echo " ### Continuation ### "
$cmd -cpi production.cpt -noappend
fi

if ! compgen -G "*.gro*" > /dev/null ; then
echo "Job not finished."
echo "Submiting..."
sbatch job.sh
fi

"""


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


def _get_df_from_db_file(db_file: Union[str, Path]) -> pd.DataFrame:
    """Returns a pandas dataframe from a file. If the file
    does not exist, it is overwritten.

    Args:
        db_file (Union[str, Path]): The path.

    Returns:
        pd.DataFrame: The dataframe.

    """
    db_file = Path(db_file)
    if not db_file.is_file():
        sims = pd.DataFrame([], columns=['sim_dir', 'name', 'state', 'jobid'])
    else:
        sims = pd.read_hdf(db_file, key='sims')
    return sims


def _get_tpr_files_from_start_dir(start_dir: Union[Path, str],
                                  prefix: str = 'production*'
                                 ) -> List[Path]:
    """Uses Path.rglob(**.tpr) to find tpr files.

    Args:
        start_dir: Union[Path, str]: The path to start searching.

    Returns:
        list: A list of the tpr files.

    """
    start_dir = Path(start_dir)
    tpr_files = list(start_dir.rglob(f'**/{prefix}tpr'))
    return tpr_files


def _template_job(directory: str,
                  template: Optional[Union[str, Path]] = None,
                  module_loads: Optional[str, list[str]] = None,
                  command: Optional[str] = None,
                  **kwargs,
                 ) -> str:
    """Templates a job-submission file."""
    if template is None:
        template = jinja2.Template(JOB_TEMPLATE)
    else:
        template = jinja2.Template(Path(template).read_text())

    if module_loads is None:
        module_loads = []
        while True:
            try:
                print("Enter the command(s) to load the modules (e.g. `module load /chem/gromacs`). <Enter> to add multiple module loads. <Ctrl-D> to finish.")
                line = input("Enter the module load here:")
            except EOFError:
                break
            module_loads.append(line)
    if isinstance(module_loads, list):
        module_loads = '\n'.join(module_loads)

    if command is None:
        command = input("Please enter the command to be executed.")

    # combine the collected info with everything in kwargs
    template_dict = {'directory': directory.resolve(), 'module_loads': module_loads, 'command': command} | kwargs
    rendered_file = template.render(template_dict)
    return rendered_file


def _get_jobs_df(workload_manager) -> pd.DataFrame:
    """Uses `squeue` to get currently running jobs.

    Returns:
        pd.DataFrame: The jobs and more info.

    """
    if workload_manager == "slurm":
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
    elif workload_manager == "moab":
        import getpass
        username = getpass.getuser()
        cmd = f"qstat -u {username}"
        proc = run(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        df = pd.DataFrame({}, columns=['jobid', 'username', 'queue', 'jobname', 'sessId', 'NDS', 'TSK', 'req_memory', 'req_time', 'S', 'elap_time'])
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
    else:
        raise Exception("Argument `workload_manager` needs to be either 'slurm' or 'moab'.")


def submit_script(script_file: Union[str, Path],
                  workload_manager: str,
                 ) -> int:
    """Submits a script.

    Args:
        script_file (Union[str, Path]): The script to be submitted.

    Returns:
        int: The jobid.

    """
    assert Path(script_file).is_file()
    if workload_manager == "slurm":
        cmd = f"sbatch {script_file}"
    elif workload_manager == "moab":
        cmd = f"qsub {script_file}"
    else:
        raise Exception("Argument `workload_manager` needs to be either 'slurm' or 'moab'.")
    proc = run(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
    try:
        if workload_manager == "slurm":
            job_id = int(proc.stdout.split()[-1])
        else:
            job_id = int(proc.stdout.strip())
    except IndexError:
        print(script_file)
        print(proc.stdout)
        raise
    return job_id


def _sort_parts(file):
    return int(str(file).split('.')[1].lstrip('part'))


def check_simulation_state(directory: Union[str, Path], job_id: int, prefix: str) -> str:
    out_file = Path(directory) / f'slurm-{job_id}.out'
    if not out_file.is_file():
        msg = (f"The out file {out_file} does not exist. Simulation "
               f"will be marked as CRASHED. Reset the simulation with "
               f"`python simulation_attender.py -reset {job_id}.")
        print(msg)
        return 'crashed'
    content = out_file.read_text()
    if "CANCELLED AT" in content:
        return 'rerun'
    if "COMPLETED (exit code 0)" in content or 'Writing final coordinates' in content:
        return 'finished'
    if 'Error in user input' in content:
        print(f"Simulation in {directory} with id {job_id} crashed due to error in user input.")
        return 'error_in_user_input'
    log_file = list(Path(directory).glob('*.log'))
    log_file = sorted(log_file, key=_sort_parts)[-1]
    if 'Run time exceeded' in log_file.read_text():
        out_file = Path(directory) / f'slurm-{job_id}.out'
        if "Unable to open file" in out_file.read_text():
            print(f"Run time exceeded in {directory}. Resubmit failed due to wrong name.")
            return "resubmit"
        else:
            raise Exception(f"Resubmitting of job.sh in {directory} failed due to unkown reasons.")
    print(content)
    raise Exception


###########################################################
# Main
###########################################################


def reset_db_file(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    options = {p.name: p.default for p in ctx.command.params}
    sims = _get_df_from_db_file(options['db_file'])
    click.echo(f"Resetting simulation with job_id {value}")
    idx = (sims[sims['jobid'] == value]).index
    assert len(idx) == 1
    idx = idx[0]
    sims.at[idx, 'state'] = 'ENQUEUED'
    sims.at[idx, 'Jobid'] = None
    sims.to_hdf(options['db_file'], key='sims')
    ctx.exit()



def delete_job(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    options = {p.name: p.default for p in ctx.command.params}
    sims = _get_df_from_db_file(options['db_file'])
    click.echo(f"Deleting job_id {value}")
    idx = (sims[sims['jobid'] == value]).index
    assert len(idx) == 1, sims[sims['jobid'] == value]
    idx = idx[0]
    sims = sims.drop(idx, axis=0)
    sims.to_hdf(options['db_file'], key='sims')
    ctx.exit()


def print_df(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    options = {p.name: p.default for p in ctx.command.params}
    sims = _get_df_from_db_file(options['db_file'])
    with pd.option_context("display.max_rows", None):
        print(sims)
    ctx.exit()


def clear_crashed(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    options = {p.name: p.default for p in ctx.command.params}
    sims = _get_df_from_db_file(options['db_file'])
    sub_df = sims[sims['state'] == 'CRASHED']

    for i, row in sub_df.iterrows():
        sims = sims.drop(i, axis='rows')

    sims.to_hdf(options['db_file'], key='sims')
    ctx.exit()



def cancel_and_delete(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    options = {p.name: p.default for p in ctx.command.params}
    sims = _get_df_from_db_file(options['db_file'])
    sub_df = sims[sims['state'] == 'RUNNING']
    workload_manager = _get_workload_manager()

    # cancel the job
    for i, row in sub_df.iterrows():
        print(f"Canceling job {row['jobid']}.")
        if workload_manager == "slurm":
            cmd = f"scancel {row['jobid']}"
        else:
            cmd = f"qdel {row['jobid']}"
        proc = run(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        if proc.returncode != 0:
            raise Exception(f"Canceling job {row['jobid']} with command {cmd} did return a non-zero "
                            f"exit code ({proc.returncode}), which hints at something not working correctly. "
                            f"Here's the stdout: {proc.stdout} and stderr: {proc.stderr} .")

        # sleep to let the program process the sigint
        sleep(3)

        # make sure the job_id is truly not running anymore
        jobs = _get_jobs_df(workload_manager=workload_manager)

        # delete the row
        sims = sims.drop(i, axis='rows')

    sims.to_hdf(options['db_file'], key='sims')
    ctx.exit()


def _get_workload_manager() -> str:
    # decide on slurm or moab
    slurm_proc = run("squeue", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
    moab_proc = run("qstat", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
    if "command not found" in moab_proc.stderr and "command not found" not in slumr_proc.stderr:
        return "slurm"
    elif "command not found" in slurm_proc.stderr and "command not found" not in moab_proc.stderr:
        return "moab"
    else:
        print("Could not determine the workload manager. Neither `squeue` (slurm) or `qstat` (moab) seems to work.")
        raise SystemExit(2)


@click.command()
@click.option('-db', '--database-file','db_file', default='sims.h5', type=str,
              help='The database file to read or create')
@click.option('-p', '--prefix', default='production*', type=str,
              help="The prefix for the tpr files to be added/checked")
@click.option('-sd', '--start-directory','start_dir', required=True, type=str,
              prompt='Enter the directory to start the search.',
              help='The start directory to start searchin')
@click.option('-t', '--template', required=False, type=str, default=None,
              help=('If you have a templated job script, you can add it here.'
                    'More on templated job scripts in the docstring to `main`.')
              )
@click.option('-m', '--module-loads', required=False, default=None, type=str,
              help=('The `module load` commands to set up the environment. '
                    'Can be supplied how many times you like for loading more modules. ')
              )
@click.option('-c', '--command', required=False, default=None, type=str,
              help="The command to execute via slurm, e.g. gmx mdrun -deffnm production.")
@click.option('-max', '--max-sims', required=False, default=50, type=int,
              help="The maximum number of concurrent simulations.")
@click.option('-reset', required=False, default=None, type=int, callback=reset_db_file, is_eager=False, expose_value=True,
              help="Resets the state of the given job_id to ENQUEUED, so the sim can be rerun")
@click.option('-delete', required=False, default=None, type=int, callback=delete_job, is_eager=False, expose_value=True,
              help="Deletes the job from the database.")
@click.option('-print', required=False, is_flag=True, callback=print_df, is_eager=False, expose_value=True,
              help="Just prints the current database.")
@click.option('-cancel-and-delete', required=False, is_flag=True, callback=cancel_and_delete, is_eager=False,
              expose_value=True, help=("Know that feeling of 'I forgot something'? Setting this flag, cancels all simulations "
                  "currently running and deletes them from the database. Provide the path to the database file (e.g: sims.h5)."))
@click.option('-rerun-crashed', required=False, is_flag=True, default=False, type=bool,
              help="Reruns crashed simulations, if the reason to the crash is known.")
@click.option('-clear-crashed', required=False, is_flag=True, callback=clear_crashed, is_eager=False,
              help="Deletes all CRASHED simulations from the database.")
def main(start_dir: Union[str, Path],
         prefix: str = "production*",
         db_file: Union[str, Path] = 'sims.h5',
         template: Optional[Union[str, Path]] = None,
         module_loads: Optional[list[str]] = None,
         command: Optional[str] = None,
         max_sims: int = 50,
         rerun_crashed: bool = False,
         **kwargs,
        ) -> int:
    """simulation_attender.py handles your simulations

    Uses a pandas dataframe saved to .h5 file to save states and info about simulations.

    General Workflow:
        * Search for tpr-files in the given `start-directory`. This uses recursive glob and
            captures all such files. In every directory, there should only be one tpr-file
            present in every directory. To run multiple simulations in the same directory,
            you can use the `prefix` option, which matches the tpr files in the directories
            supplied as `start_dir`.
        * New simulations are started, existing ones are checked for completion, or crash, or resubmitted.

    Templating:
        As the `template` option, you can supply a file, that will be used as a job-submission script.
        This file uses the jinja2 templating syntax. Meaning an expression like this: {{ key_from_kwargs }}
        will be filled with the value of the argument `key_from_kwargs`. The `module_loads`, `directory`, and `command`
        arguments are autoamtically included in the template. Here's an example:
        
        \b
        #!/bin/bash
        #SBATCH --chdir={{ directory }}
        #SBATCH --partition=single
        #SBATCH --nodes=1
        #SBATCH --ntasks-per-node=64
        #SBATCH --time=120:00:00
        #SBATCH --mem=50gb
        #SBATCH --export=NONE
        \b 
        {{ module_loads }}
        \b
        {{ commands }}
        

    Args:
        db_file (Union[str, Path]): The .h5 file to read/write. Defaults to `./sims.h5`.
        start_dir (Union[str, Path]): The directory to start searching for sims.
        **kwargs: Arbitrary arguments for your template.

    """
    # get the workload manager
    workload_manager = _get_workload_manager()


    # get the database
    sims = _get_df_from_db_file(db_file)

    # get the tpr_files
    tpr_files = _get_tpr_files_from_start_dir(start_dir, prefix)
    if len(tpr_files) != len(set([f.parent for f in tpr_files])):
        print("There seems to be some .tpr files in the same directory.")
        return 1

    # get currently running jobs
    jobs = _get_jobs_df(workload_manager=workload_manager)
    if len(jobs) > max_sims:
        print(f"Exceeded maximum number of {max_sims} concurrent simulations.")
        return 2

    # collect sims
    print(f"Collecting sims in {start_dir}.")
    for i, tpr_file in enumerate(tpr_files):
        test = sims[(sims['sim_dir'] == str(tpr_file.parent)) & (sims['name'] == tpr_file.stem)]
        if test.size == 0:
            print(f"The sim with tpr_file {tpr_file} is new and will be added to the database")
            sims = pd.concat([sims, pd.DataFrame.from_records([{'sim_dir': str(tpr_file.parent), 'name': str(tpr_file.stem), 'state': 'ENQUEUED'}])], axis='rows', ignore_index=True)
        elif test.size != 0 and test['state'].values[0] == "CRASHED" and rerun_crashed:
            sims = pd.concat([sims, pd.DataFrame.from_records([{'sim_dir': str(tpr_file.parent), 'name': str(tpr_file.stem), 'state': 'ENQUEUED'}])], axis='rows', ignore_index=True)
    sims.to_hdf(db_file, key='sims')

    # iterate over the simulations
    for i, row in sims.iterrows():
        state = getattr(SimState, row['state'])
        sim_dir = Path(row['sim_dir'])
        if state is SimState.CRASHED:
            continue
        if not sim_dir.is_dir():
            print(f"The directory for  the simulation in {sim_dir} was deleted. I will mark this sim as crashed.")
            sims.at[i, 'state'] = 'CRASHED'
            continue
        job_script_file = sim_dir / 'job.sh'
        if state is SimState.ENQUEUED:
            # create a templated job script
            job_script = _template_job(Path(row['sim_dir']), template, module_loads, command, **kwargs)
            job_script_file.write_text(job_script)
            job_id = submit_script(job_script_file, workload_manager=workload_manager)
            print(f"Submitted sim in {row['sim_dir']} with jobid {job_id}")
            sims.at[i, 'jobid'] = job_id
            sims.at[i, 'state'] = 'RUNNING'
        elif state is SimState.RUNNING:
            if any(jobs['jobid'] == row['jobid']):
                print(f"Simulation in {row['sim_dir']} with jobid {row['jobid']} is still running.")
                continue
            result = check_simulation_state(row['sim_dir'], row['jobid'], prefix)
            if result == 'finished':
                sims.at[i, 'state'] = 'FINISHED'
            elif result == 'crashed':
                sims.at[i, 'state'] = 'CRASHED'
            elif result == 'error_in_user_input':
                sims.at[i, 'state'] = 'CRASHED'
                if rerun_crashed:
                    job_script = _template_job(Path(row['sim_dir']), template, module_loads, command, **kwargs)
                    job_script_file.write_text(job_script)
                    job_id = submit_script(job_script_file, workload_manager=workload_manager)
                    print(f"Submitted sim in {row['sim_dir']} with jobid {job_id}")
                    # sim_dir        name     state   jobid
                    sims.append({"sim_dir": row["sim_dir"],
                                 "name": row["name"],
                                 "state": "RUNNING",
                                 "jobid": job_id,
                                }, ignore_index=True)
                else:
                    print("This crashed simulation can be resubmitted, using the `-rerun-crashed` flag.")
            elif result == "resubmit":
                job_script = _template_job(Path(row['sim_dir']), template, module_loads, command, **kwargs)
                job_script_file.write_text(job_script)
                job_id = submit_script(job_script_file, workload_manager=workload_manager)
                print(f"RESUBMITTED sim in {row['sim_dir']} with jobid {job_id}")
                sims.at[i, 'jobid'] = job_id
                sims.at[i, 'state'] = 'RUNNING'
            else:
                raise Exception("Don't know how I ended up here.")
        elif state is SimState.CRASHED:
            pass
            # print(f"Simulation in directory {sim_dir} was marked as CRASHED and will be ignored.")

        sims.to_hdf(db_file, key='sims')
        jobs = _get_jobs_df(workload_manager=workload_manager)
        if len(jobs) > max_sims:
            print(f"Exceeded maximum number of {max_sims} concurrent simulations.")
            return 2

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
