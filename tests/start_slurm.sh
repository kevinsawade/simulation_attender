#!/bin/bash

. sh_libs/liblog.sh

# exit on error
set -e

# check for persistent directories and access rights
SHOULD_EXIT=0
if [ ! -d openldap_data ] ; then
	info "Run this command to make a persistent directory for the openldap server:\n$ mkdir -p openldap_data"
	SHOULD_EXIT=1
fi
if [ ! -d nfs_mount ] ; then
	info "Run this command to make a persistent directory for the home folder in the slurm nodes:\n$ mkdir -p nfs_mount"
	SHOULD_EXIT=1
fi
if [ ! -d work ] ; then
	info "Run this command to make a persistent directory for the home folder in the slurm nodes:\n$ mkdir -p work"
	SHOULD_EXIT=1
fi
openldap_access_rights=$( ls -ald openldap_data | awk '{print $1'} )
certs_access_rights=$( ls -ald certs | awk '{print $1'} )
if [ $openldap_access_rights != drwxrwxrwx ] ; then
	SHOULD_EXIT=1
	error "Until I figure out how to make the openldap container use the files in openldap_data/ without this command, you need to run this as sudo:\n$ sudo chmod -R ugo+rwx openldap_data"
fi
if [ $certs_access_rights != drwxrwxrwx ] ; then
	SHOULD_EXIT=1
	error "Until I figure out how to make the openldap container use the files in certs/ without this command, you need to run this as sudo:\n$ sudo chmod -R ugo+rwx certs"
fi

if [ ! $SHOULD_EXIT -eq 0 ] ; then
	error "Follow the instructions and then start the script again."
	exit
fi

docker build --pull -t kevinsawade/modules-gmx-base:latest -f modules/Dockerfile \
  --build-arg GOSU_VERSION="1.11" \
  --build-arg ENVIRONMENT_MODULES_VERSION="5.2.0" \
  --build-arg GMX_VERSION="2023.1" \
  --build-arg CMAKE_VERSION="3.26.3" .
# docker push kevinsawade/modules-gmx-base:latest
docker build --pull -t kevinsawade/ldap-client:latest -f ldap_client/Dockerfile .
# docker push kevinsawade/ldap-client:latest
docker build --pull -t kevinsawade/slurm-base:latest --build-arg SLURM_VERSION="slurm-22-05-8-1" -f slurm_base/Dockerfile .
# docker push kevinsawade/slurm-base:latest
docker build --pull -t kevinsawade/slurm-db:latest -f slurm_db/Dockerfile .
# docker push kevinsawade/slurm-db:latest
docker build --pull -t kevinsawade/slurm-master:latest -f slurm_master/Dockerfile .
# docker push kevinsawade/slurm-master:latest
docker build --pull -t kevinsawade/slurm-node:latest -f slurm_node/Dockerfile .
# docker push kevinsawade/slurm-node:latest
docker build --pull -t kevinsawade/run-simulation-attender-tests:latest .
# docker push kevinsawade/run-simulation-attender-tests:latest

# start the swarm
docker compose up
