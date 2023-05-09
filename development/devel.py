#%%

from __future__ import annotations
import shutil
from pathlib import Path
from click.testing import CliRunner
from simulation_attender import cli
from simulation_attender import get_db

# %% create runner

runner = CliRunner()

# %% call some clis

result = runner.invoke(cli, args=["--help"], catch_exceptions=False)
