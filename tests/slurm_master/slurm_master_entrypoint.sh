#!/bin/bash

# turn on bash's job control
set -m

# write the password
echo $LDAP_ADMIN_PASSWORD > /etc/ldap.secret
echo $LDAP_ADMIN_PASSWORD > /etc/pam_ldap.secret
echo $LDAP_ADMIN_PASSWORD > /etc/libnss-ldap.secret
unset LDAP_ADMIN_PASSWORD

# wait for the nodes to spin up and create passwordless ssh
/wait-for-it.sh openldap:636 --strict -- echo "openldap.example.org 636 is up" && /etc/init.d/ssh start && /etc/init.d/nscd restart && /etc/init.d/nslcd restart

# bring up sshd
/usr/sbin/sshd

# print uid
id

# start the munge daemon
gosu munge service munge start

# fix stuff in the slurm configuration
sed -i "s/REPLACE_IT/CPUs=$(nproc)/g" /etc/slurm/slurm.conf

# wait for the slurmdb to become active
/wait-for-it.sh slurm-database.example.org:6819 --timeout=60 --strict -- echo "slurm-database.example.org 6819 is up"

# start the slurm control daemons
gosu root /usr/bin/sacctmgr --immediate add cluster name=linux
sleep 2s
gosu root /usr/sbin/slurmctld -Dvvv
# /wait-for-it.sh slurm-node1.local.dev:6818 --strict -- service slurmctld start

# use this, if the docker container automatically terminates, but you want to keep it running
# tail -f /dev/null