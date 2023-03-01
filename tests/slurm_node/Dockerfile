FROM slurm-base

#####################
# SLURM
#####################
# set up slurmctld
# RUN mkdir /var/spool/slurmctld
# RUN chown slurm:slurm /var/spool/slurmctld
# RUN chmod 755 /var/spool/slurmctld
# RUN mkdir -p /var/log/slurm
# RUN touch /var/log/slurmctld.log
# RUN chown slurm: /var/log/slurmctld.log
# RUN touch /var/log/slurm_jobacct.log /var/log/slurm_jobcomp.log
# RUN chown slurm: /var/log/slurm*
# RUN chown slurm: /var/log/slurm/
# RUN chown slurm:slurm /etc/slurm
COPY slurm_base/slurm.conf /etc/slurm/slurm.conf
COPY slurm_base/cgroup.conf /etc/slurm/cgroup.conf

# run the entrypoint
COPY slurm_node/slurm_node_entrypoint.sh slurm_node_entrypoint.sh
RUN chmod a+wrx slurm_node_entrypoint.sh
EXPOSE 6817 6818 6819
CMD ["/slurm_node_entrypoint.sh"]