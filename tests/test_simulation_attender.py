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

    def teardown_method(self):
        if self.db_file.is_file():
            self.db_file.unlink()

    def setup_method(self):
        if self.db_file.is_file():
            self.db_file.unlink()
        self.runner = CliRunner()

    def test_help_message(self):
        result = self.runner.invoke(cli, ["--help"])
        assert "--help         Show this message and exit." in result.output, print(f"--help does not print a help message.")

    def test_collect(self):


    def test_assert_true(self):
        assert False