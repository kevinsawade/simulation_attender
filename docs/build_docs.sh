#!/bin/bash

pdoc --html --output-dir build ../simulation_attender --force
mv build/simulation_attender/simulation_attender.html build/index.html