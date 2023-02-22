#!/bin/bash

# turn on bash's job control
set -m

# print uid
id

# write the password
echo $LDAP_ADMIN_PASSWORD > /etc/ldap.secret
echo $LDAP_ADMIN_PASSWORD > /etc/pam_ldap.secret
echo $LDAP_ADMIN_PASSWORD > /etc/libnss-ldap.secret
unset LDAP_ADMIN_PASSWORD

# wait for the nodes to spin up and create passwordless ssh
/wait-for-it.sh openldap:636 --strict -- echo "openldap.local.dev 636 is up" && /etc/init.d/ssh start && /etc/init.d/nscd restart && /etc/init.d/nslcd restart

# start the munge daeomon
service munge start
su -u munge /sbin/munged
munge -n
munge -n | unmunge
remunge

# fix stuff in the slurm configuration
sed -i "s/REPLACE_IT/CPUs=$(nproc)/g" /etc/slurm-llnl/slurm.conf


# start the slurm control daemons
sacctmgr -i add_cluster "cluster"
sleep 2s
/wait-for-it.sh slurm-node1.local.dev:6818 --strict -- service slurmctld start

# use this, if the docker container automatically terminates, but you want to keep it running
tail -f /dev/null