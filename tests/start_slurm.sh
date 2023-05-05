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

# build containers
docker build -t ldap-client -f ldap_client/Dockerfile .
docker build -t slurm-base --build-arg SLURM_VERSION="slurm-22-05-8-1" -f slurm_base/Dockerfile .
docker build -t slurm-db -f slurm_db/Dockerfile .
docker build -t slurm-master -f slurm_master/Dockerfile .
docker build -t slurm-node -f slurm_node/Dockerfile .

# start the swarm
docker compose build
docker compose up
