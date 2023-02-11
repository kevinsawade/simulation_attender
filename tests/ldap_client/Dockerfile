FROM ubuntu:22.04

# some basics, which I need no matter what :p
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
    iproute2
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get -y install tzdata


#####################
# SSH
#####################
# ssh packages
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    openssh-server \
    sshpass

# create localadmin user which has sudo priviliges
RUN useradd -ms /bin/bash localadmin
RUN usermod -aG sudo localadmin
RUN echo "localadmin:localadminpassword" | chpasswd
RUN echo 'localadmin  ALL=(ALL:ALL) ALL' >> /etc/sudoers
RUN chown -R localadmin /home/localadmin

# make changes to openssh
RUN mkdir -p /var/run/sshd
RUN echo "PasswordAuthentication yes" >> /etc/ssh/sshd_config
RUN echo "PermitRootLogin no" >> /etc/ssh/sshd_config
RUN if [ ! -d /var/run/sshd ] ; then mkdir /var/run/sshd ; ssh-keygen -t rsa -f /etc/ssh/ssh_host_rsa_key -N '' ; fi
RUN chown localadmin /etc/ssh/ssh_host_rsa_key
RUN chown localadmin /etc/ssh/ssh_host_rsa_key.pub
COPY ssh/ssh_config /home/localadmin/.ssh/config
RUN mkdir -p /home/localadmin/.ssh \
    && chmod 0700 /home/localadmin/.ssh \
    && ssh-keygen -b 2048 -t rsa -f /home/localadmin/.ssh/id_rsa -q -N "" -C "localadmin@$(hostname)-$(date -I)" \
    && touch /home/localadmin/.ssh/authorized_keys \
    && cat /home/localadmin/.ssh/id_rsa.pub > /home/localadmin/.ssh/authorized_keys \
    && chmod 0640 home/localadmin/.ssh/authorized_keys \
    && chown -R localadmin /home/localadmin/.ssh \
    && chmod 0644 home/localadmin/.ssh/config


#####################
# LDAP
#####################
# ldap packages
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    dialog \
    ca-certificates \
    libpam-ldapd \
    ldap-utils \
    libnss-ldap \
    nscd

# set debian frontend
RUN export DEBIAN_FRONTEND=gtk

# copy files for ldap
COPY ldap_client/ldap.conf /etc/ldap.conf
COPY ldap_client/pam.d/common-password /etc/pam.d/common
COPY ldap_client/nsswitch.conf /etc/nsswitch.conf

# copy the certificat
COPY certs/ca.crt /usr/local/share/ca-certificates/ca.crt
RUN update-ca-certificates

#####################
# PORTS
#####################
# expose ssh port
EXPOSE 22

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