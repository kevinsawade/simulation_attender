FROM kevinsawade/ldap-client

#####################
# MUNGE
#####################
# set up munge for slurm following this tutorial:
# https://southgreenplatform.github.io/trainings/hpc/slurminstallation/
ENV MUNGEUSER=1001
RUN groupadd -g $MUNGEUSER munge
RUN useradd -M -c "Munge Uid 'N' Gid Emporium" -d /var/lib/munge -u $MUNGEUSER -g munge -s /sbin/nologin munge
ENV SLURMUSER=1002
RUN groupadd -g $SLURMUSER slurm
RUN useradd -M -c "SLURM workload manager" -d /var/lib/slurm -u $SLURMUSER -g slurm -s /bin/bash slurm

# install munge packages
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get -y install tzdata
RUN apt-get update && apt-get install -y \
    munge \
    git \
    wget \
    mysql-client \
    libmunge-dev \
    libpam0g-dev \
    perl \
    python3 \
    python3-dev \
    libreadline-dev \
    bzip2 \
    lbzip2 \
    make \
    gcc

# copy the munge-key
COPY munge/munge.key /etc/munge/munge.key

# fix permissions on munge stuff
RUN mkdir -p /run/munge
RUN chown -R munge: /etc/munge/ /var/log/munge/ /var/lib/munge/ /run/munge/
RUN chmod 0700 /etc/munge/ /var/log/munge/
RUN chmod 0644 /etc/munge/munge.key
RUN chmod 0711 /var/lib/munge/ 
RUN chmod 0755 /var/run/munge/
RUN chmod a+x /run/munge

# expose some ports
EXPOSE 22 6817 6818 6819