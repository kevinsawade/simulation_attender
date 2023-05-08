FROM ubuntu:22.04

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
    python3 \
    tcl \
    tcl8.6-dev \
    tk \
    expect \
    tclsh \
    openssl \
    libssl-dev

#####################
# GOSU
#####################
ARG GOSU_VERSION=1.11
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
ARG ENVIRONMENT_MODULES_VERSION=5.2.0
RUN set -ex \
    && mkdir -p /usr/local/environment_modules \
    && wget -O /usr/local/environment_modules/environment_modules.tar.gz https://sourceforge.net/projects/modules/files/Modules/modules-$ENVIRONMENT_MODULES_VERSION/modules-$ENVIRONMENT_MODULES_VERSION.tar.gz/download \
    && tar xfz /usr/local/environment_modules/environment_modules.tar.gz -C /usr/local/environment_modules \
    && cd /usr/local/environment_modules/modules-$ENVIRONMENT_MODULES_VERSION \
    && ./configure --prefix=/usr/share/Modules --modulefilesdir=/etc/modulefiles \
    && make \
    && make install \
    && ln -s /usr/share/Modules/init/profile.sh /etc/profile.d/modules.sh \
    && ln -s /usr/share/Modules/init/profile.csh /etc/profile.d/modules.csh

#####################
# CMAKE
#####################
ARG CMAKE_VERSION=3.26.3
RUN set -ex \
    && mkdir -p /usr/local/cmake \
    && wget -O /usr/local/cmake/cmake-${CMAKE_VERSION}.tar.gz https://github.com/Kitware/CMake/releases/download/v$CMAKE_VERSION/cmake-${CMAKE_VERSION}.tar.gz \
    && tar xfz /usr/local/cmake/cmake-${CMAKE_VERSION}.tar.gz -C /usr/local/cmake \
    && cd /usr/local/cmake/cmake-${CMAKE_VERSION} \
    && ./bootstrap \
    && make \
    && make install

#####################
# CREATE GMX MODULE
#####################
ARG GMX_VERSION=2023.1
RUN set -ex \
    && mkdir -p /usr/local/gromacs \
    && wget -O /usr/local/gromacs/gromacs-$GMX_VERSION.tar.gz https://ftp.gromacs.org/gromacs/gromacs-$GMX_VERSION.tar.gz \
    && tar xfz /usr/local/gromacs/gromacs-$GMX_VERSION.tar.gz -C /usr/local/gromacs \
    && cd /usr/local/gromacs/gromacs-$GMX_VERSION \
    && mkdir build \
    && cd build \
    && cmake .. -DGMX_BUILD_OWN_FFTW=ON -DREGRESSIONTEST_DOWNLOAD=ON \
    && make \
    && make check \
    && make install
RUN mkdir -p /etc/modulefiles/gromacs
COPY gromacs_modulefile /etc/modulefiles/gromacs/$GMX_VERSION
RUN sed -i "s/GMX_VERSION/$GMX_VERSION/g" /etc/modulefiles/gromacs/$GMX_VERSION

#####################
# SH LIBS
#####################

RUN mkdir -p /sh_libs
COPY liblog.sh /sh_libs/liblog.sh

#####################
# ENTRYPOINT
#####################

# add tini
ENV TINI_VERSION v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod a+rx /tini
ENTRYPOINT ["/tini", "--"]

COPY test_modules_entrypoint.sh /test_modules_entrypoint.sh
RUN chmod a+wrx /test_modules_entrypoint.sh
CMD ["/test_modules_entrypoint.sh"]