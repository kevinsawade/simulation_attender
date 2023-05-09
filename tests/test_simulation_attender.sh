#!/bin/bash

# exit when any command fails
set -m

# load libs
. sh_libs/liblog.sh

# print infos
info "Welcome to the simulation_attender.py test suite."
cp ../simulation_attender/simulation_attender.py simulation_attender.py
info "Spooling up docker containers."
info "For a first-time build, this can take up to a few hours. I need to compile cmake, environment-modules and gromacs from source."
info "To view the build progress, Ctrl^C this script and execute start_slurm.sh manually."
./start_slurm.sh &> /dev/null
docker compose run c1 bash test_in_docker.sh
info "Tearing down docker containers."
./teardown.sh &> /dev/null