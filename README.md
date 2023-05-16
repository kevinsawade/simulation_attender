# simulation_attender
A comprehensive library attending Gromacs simulations on HPC clusters.

**Features:**
- Works with slurm, moab, gridengine and can also attend local simulations.
- Track simulations and files using easy to understand databases.
- One place to get status updates on all your runnung gromacs simulations.
- Undo-feature: Did an oopsie? Undo the last command using `python simulation_attender.py undo`

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

## Quickstart

```bash
# collect simulations
python simulation_attender.py collect /work

# template the simulations
python ../simulation_attender/simulation_attender.py template --module_loads "module load gromacs/2023.1" --command "gmx mdrun -deffnm {{ stem }}"

# list simulations
python ../simulation_attender/simulation_attender.py list

# submit
python ../simulation_attender/simulation_attender.py submit

# run and check
python ../simulation_attender/simulation_attender.py run
```

## Documentation

Visit: https://kevinsawade.github.io/simulation_attender/ to get to the full documentation./