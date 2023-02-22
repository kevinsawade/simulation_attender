FROM kevinsawade/ldap-client

#####################
# MUNGE
#####################
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
RUN chmod 0711 /var/lib/munge/ 
RUN chmod 0755 /var/run/munge/
RUN chmod a+x /run/munge

# expose some ports
EXPOSE 22 6817 6818 6819