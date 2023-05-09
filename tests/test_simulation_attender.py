"""Tests for simulation_attender.py"""

################################################################################
# Imports
################################################################################

from __future__ import annotations
import shutil
from pathlib import Path
from click.testing import CliRunner
from simulation_attender import cli


################################################################################
# Tests
################################################################################


class TestSimAttender:
    db_file = Path("/app/sims.h5")
    tpr_file = Path("/app/production.tpr")
    dir1 = Path("/work/simulation1")
    dir2 = Path("/work/simulation2")

    def teardown_method(self):
        if self.db_file.is_file():
            self.db_file.unlink()

    def setup_method(self):
        if self.db_file.is_file():
            self.db_file.unlink()
        if not self.dir1.is_dir():
            self.dir1.mkdir(parents=True, exist_ok=True)
        if not self.dir2.is_dir():
            self.dir2.mkdir(parents=True, exist_ok=True)
        self.runner = CliRunner()

    def test_help_message(self):
        result = self.runner.invoke(cli, ["--help"])
        assert "--help         Show this message and exit." in result.output, print(
            f"--help does not print a help message.")
        result = self.runner.invoke(cli, ["collect", "--help"])
        assert "--help         Show this message and exit." in result.output, print(
            f"collect --help does not print a help message.")

    def test_collect(self):
        shutil.copyfile(self.tpr_file, self.dir1 / "production.tpr")
        shutil.copyfile(self.tpr_file, self.dir2 / "topol.tpr")
        assert (self.dir1 / "production.tpr").is_file()
        result = None
        pass

    def test_assert_true(self):
        assert False