FROM ubuntu:22.04
ARG GOSU_VERSION=1.11
ARG ENVIRONMENT_MODULES_VERSION=5.2.0

#####################
# BASIC PACKAGES
#####################
# RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get -y install tzdata
RUN apt-get update && DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get install -y \
    tzdata \
    wget \
    bzip2 \
    perl \
    gcc \
    build-essential\
    git \
    gnupg \
    make \
    vim \
    netcat \
    libpython3-dev \
    python3-pip \
    python3

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
# MODULES
#####################
RUN set -ex \
    && mkdir -p /usr/local/environment_modules \
    && wget -O /usr/local/environment_modules/environment_modules.tar.bz2 https://sourceforge.net/projects/modules/files/Modules/modules-$ENVIRONMENT_MODULES_VERSION/modules-$ENVIRONMENT_MODULES_VERSION.tar.bz2/download