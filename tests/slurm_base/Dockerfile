FROM ldap-client
ARG SLURM_VERSION=slurm-22-05-8-1
ARG GOSU_VERSION=1.11

#####################
# NEEDED PACKAGES
#####################
# install munge packages
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get -y install tzdata
RUN apt-get update && apt-get install -y \
    wget \
    bzip2 \
    perl \
    gcc \
    build-essential\
    git \
    gnupg \
    make \
    munge \
    libmunge-dev \
    libpython3-dev \
    python3-pip \
    python3 \
    psmisc \
    mysql-client \
    libmysqlclient-dev \
    cgroup-tools
RUN pip3 install Cython nose

#####################
# GOSU
#####################
RUN set -ex \
    && wget -O /usr/local/bin/gosu "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-amd64" \
    && wget -O /usr/local/bin/gosu.asc "https://github.com/tianon/gosu/releases/download/$GOSU_VERSION/gosu-amd64.asc" \
    && export GNUPGHOME="$(mktemp -d)" \
    && gpg --batch --keyserver hkps://keys.openpgp.org --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 \
    && gpg --batch --verify /usr/local/bin/gosu.asc /usr/local/bin/gosu \
    && rm -rf "${GNUPGHOME}" /usr/local/bin/gosu.asc \
    && chmod +x /usr/local/bin/gosu \
    && gosu nobody true

#####################
# SLURM
#####################
# Install slurm
RUN mkdir -p /slurm_install
RUN set -x \
    && git clone -b ${SLURM_VERSION} --single-branch --depth=1 https://github.com/SchedMD/slurm.git /slurm_install/slurm \
    && cd /slurm_install/slurm \
    && ./configure --enable-debug --prefix=/usr --sysconfdir=/etc/slurm \
        --with-mysql_config=/usr/bin  --libdir=/usr/lib64 --with-cgroup \
    && make install \
    && install -D -m644 etc/cgroup.conf.example /etc/slurm/cgroup.conf.example \
    && install -D -m644 etc/slurm.conf.example /etc/slurm/slurm.conf.example \
    && install -D -m644 etc/slurmdbd.conf.example /etc/slurm/slurmdbd.conf.example \
    && install -D -m644 contribs/slurm_completion_help/slurm_completion.sh /etc/profile.d/slurm_completion.sh \
    && cd .. \
    && groupadd -r --gid=990 slurm \
    && useradd -r -g slurm --uid=990 slurm \
    && mkdir -p /etc/sysconfig/slurm \
        /var/spool/slurmd \
        /var/run/slurmd \
        /var/run/slurmdbd \
        /var/lib/slurmd \
        /var/log/slurm \
        /data \
    && touch /var/lib/slurmd/node_state \
        /var/lib/slurmd/front_end_state \
        /var/lib/slurmd/job_state \
        /var/lib/slurmd/resv_state \
        /var/lib/slurmd/trigger_state \
        /var/lib/slurmd/assoc_mgr_state \
        /var/lib/slurmd/assoc_usage \
        /var/lib/slurmd/qos_usage \
        /var/lib/slurmd/fed_mgr_state \
    && chown -R slurm:slurm /var/*/slurm* 

# copy the munge-key
COPY munge/munge.key /etc/munge/munge.key

# another try at fixing munge permissions
RUN mkdir -p /etc/munge/ /var/log/munge/ /var/lib/munge/ /run/munge/
RUN chown -R munge: /etc/munge/
RUN chown -R munge: /var/log/munge/
RUN chown -R munge: /var/lib/munge/
RUN chown -R munge: /run/munge/
RUN chmod 0700 /etc/munge/
RUN chmod 0700 /var/log/munge/
RUN chmod 0700 /var/lib/munge/
RUN chmod -R 0711 /run
RUN chown 105:103 /etc/munge/munge.key
RUN chmod 600 /etc/munge/munge.key

# expose some ports
EXPOSE 22