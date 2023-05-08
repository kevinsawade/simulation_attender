# Environment modules in docker

This is a testing docker container for testing how to set up environment modules in a docker container.

## Changes to the slurm_base packages
- apt install tcl tcl8.6-dev tk expect tclsh
- use ARG $ENVIRONMENT_MODULES_VERSION
- follow the installation instructions