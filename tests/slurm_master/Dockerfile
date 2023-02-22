FROM kevinsawade/slurm-base

#####################
# SLURM
#####################
# Install slurm
ARG SLURM_VERSION
RUN mkdir -p /slurm_install
RUN wget https://download.schedmd.com/slurm/slurm-$SLURM_VERSION.tar.bz2 -O /slurm_install/slurm.tar.bz2
RUN if [ ! -f /slurm_install/slurm.tar.bz2 ] ; then echo "file is missing" ; exit ; fi
RUN ls /slurm_install
RUN tar -x -f /slurm_install/slurm.tar.bz2 -C /slurm_install
WORKDIR /slurm_install/slurm-$SLURM_VERSION
RUN ./configure
RUN make
RUN make install

# fix permissions on slurm stuff
RUN mkdir -p /etc/slurm-llnl
RUN chmod 777 /etc/slurm-llnl

# set up slurmdbd
RUN mkdir -p /var/spool/slurm/d
RUN mkdir -p /var/log/slurm
RUN chown slurm: /var/spool/slurm/d
RUN chown slurm: /var/log/slurm
RUN mkdir -p /var/spool/slurmd
COPY slurmdbd.conf /etc/slurm-llnl/slurmdbd.conf

# # set up slurmctld
RUN mkdir /var/spool/slurmctld
RUN chown slurm:slurm /var/spool/slurmctld
RUN chmod 755 /var/spool/slurmctld
RUN mkdir -p /var/log/slurm
RUN touch /var/log/slurmctld.log
RUN chown slurm: /var/log/slurmctld.log
RUN touch /var/log/slurm_jobacct.log /var/log/slurm_jobcomp.log
RUN chown slurm: /var/log/slurm*
RUN chown slurm: /var/log/slurm/
COPY slurm_base/slurm.conf /etc/slurm-llnl/slurm.conf