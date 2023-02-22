#!/bin/bash

mkdir -p openldap_data
mkdir -p nfs_mount
docker compose up --build
