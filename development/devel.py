#%%

from __future__ import annotations
import shutil
from pathlib import Path
from click.testing import CliRunner
from simulation_attender import cli
from simulation_attender import get_db
from simulation_attender.simulation_attender import store_dfs_to_hdf5
import pandas as pd

# %%
files, sims = get_db("tests/sims.h5")
sims["state"] = "ENQUEUED"
store_dfs_to_hdf5("tests/sims.h5", files, sims)

# %% create runner

runner = CliRunner()

# %% call some clis

result = runner.invoke(cli, args=["--help"], catch_exceptions=False)
