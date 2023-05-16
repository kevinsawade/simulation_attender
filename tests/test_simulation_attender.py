"""Tests for simulation_attender.py"""

################################################################################
# Imports
################################################################################

from __future__ import annotations
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from simulation_attender import cli
from simulation_attender import get_db


################################################################################
# Tests
################################################################################


class TestSimAttender:
    db_file = Path("/app/sims.h5")
    tpr_file = Path("/app/production.tpr")
    tpr_file_fails = Path("/app/production_fails.tpr")
    dir1 = Path("/work/simulation1")
    dir2 = Path("/work/simulation2")

    def teardown_method(self):
        if self.db_file.is_file():
            self.db_file.unlink()
        del self.runner

    def setup_method(self):
        if self.db_file.is_file():
            self.db_file.unlink()
        for dir_ in Path("/work").glob("*/"):
            if dir_.is_dir():
                shutil.rmtree(dir_)
        self.runner = CliRunner()

    def test_help_message(self):
        """Checks, whether the CLI prints a help message and then exits."""
        result = self.runner.invoke(cli, ["--help"])
        assert "--help" in result.output, print(
            f"--help does not print a help message.")
        result = self.runner.invoke(cli, ["collect", "--help"])
        assert "--help" in result.output, print(
            f"collect --help does not print a help message.")

    def test_collect(self):
        """Tests, whether CLI collect /work is able to find all tpr files and then add them to the database"""
        self.dir1.mkdir(parents=True, exist_ok=True)
        self.dir2.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.tpr_file, self.dir1 / "production.tpr")
        shutil.copyfile(self.tpr_file, self.dir2 / "topol.tpr")
        assert (self.dir1 / "production.tpr").is_file()
        result = self.runner.invoke(cli, ["-D", "collect", "/work", "-db", str(self.db_file)], catch_exceptions=False)
        assert "2" in result.output, print("There should be some printing here, informing the user about the new files")
        _, sims = get_db(self.db_file)
        assert len(sims) == 2, print("After adding 2 .tpr files, the sims dataframe should be len == 2.")

    def test_list(self):
        """Tests whether CLI list understands tail, head, slice, today on lists sims and files."""
        dirs = []
        for i in range(12):
            dir_ = Path(f"/work/simulation{i}")
            dir_.mkdir(parents=True, exist_ok=True)
            dirs.append(dir_)
            shutil.copyfile(self.tpr_file, dir_ / "production.tpr")
        result = self.runner.invoke(cli, ["collect", "/work", "-db", str(self.db_file)], catch_exceptions=False)
        _, sims = get_db(self.db_file)
        assert len(sims) == 12, print("After adding 12 .tpr files, the sims dataframe should be len == 12.")
        result = self.runner.invoke(cli, ["list", "tail", "-n", "10"])
        assert result.output.count("SETUP") == 10

    def test_check_also_change_state(self):
        """Tests, whether check works through the running sims and prints some info."""
        self.dir1.mkdir(parents=True, exist_ok=True)
        self.dir2.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.tpr_file, self.dir1 / "production.tpr")
        shutil.copyfile(self.tpr_file, self.dir2 / "topol.tpr")
        result = self.runner.invoke(cli, ["-D", "collect", "/work", "-db", str(self.db_file)], catch_exceptions=False)
        result = self.runner.invoke(cli, ["run"], catch_exceptions=True)
        assert result.output.count("Simulation") == 2, print("Adding 2 sims and then checking, should also print two sims.")
        result = self.runner.invoke(cli, ["run"], catch_exceptions=True)
        assert "no sims" in result.output, print("A second call to check should inform about no changes.")
        with pytest.raises(Exception):
            self.runner.invoke(cli, ["template"], catch_exceptions=False)
        result = self.runner.invoke(cli, ["template", "--module-loads", "\"module load gromacs/2023.1\""])
        _, sims = get_db(self.db_file)
        assert (sims["state"] == "TEMPLATED").all(None)

    def test_overwriting_tpr_file_raises_error(self):
        """Tests, whether changing a tpr file on disk and reloading the sim breaks it."""
        assert False

    def test_templating(self):
        """Tests whether a custom template file can be provided and whether missing arguments raise Errors"""
        assert False

    def test_submit(self):
        """Tests whether submit starts jobs and monitors their progression."""
        assert False

    def test_check(self):
        """Tests whether monitoring of simulations works."""
        assert False

    def test_undo(self):
        """Tests whether the last action can be undone."""
        assert False

    def test_doctests(self):
        """Gets the examples from the top-level docstring and tests them."""
        assert False

    def test_assert_true(self):
        assert False