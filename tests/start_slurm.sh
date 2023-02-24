#!/bin/bash

mkdir -p openldap_data
mkdir -p nfs_mount
chmod -R ugo+rwx openldap_data
chmod -r ugo+rwx certs
docker compose up --build
