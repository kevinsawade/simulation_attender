FROM ubuntu:22.04

#####################
# BASICS
#####################
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    sudo \
    vim \
    git \
    wget \
    netcat \
    iputils-ping \
    apt-utils \
    curl \
    iproute2 \
    lsb-release \
    ca-certificates
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get -y install tzdata

#####################
# NFS
#####################
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y \
    nfs-kernel-server
RUN chown -R nobody:nogroup /nfs
RUN chmod 777 /nfs
RUN echo "/nfs 172.17.0.0/16(rw,sync,no_subtree_check)" >> /etc/exports
RUN exportfs -a


#####################
# PORTS
#####################
# expose ssh port
EXPOSE 22

#####################
# Wait for it and tini
#####################
# add wait for it to allow waiting in docker containers
ADD https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh /wait-for-it.sh
RUN chmod a+rx /wait-for-it.sh

# add tini
ENV TINI_VERSION v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod a+rx /tini
ENTRYPOINT ["/tini", "--"]

COPY ldap_client/ldap_client_entrypoint.sh /ldap_client_entrypoint.sh
RUN chmod a+wrx /ldap_client_entrypoint.sh
CMD ["/ldap_client_entrypoint.sh"]