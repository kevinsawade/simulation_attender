# Simulation Attender Tests

These tests build a complete HPC network with SLURM/LDAP/SSH/ENVIRONMENT MODULES

## Quickstart

Start the container network with

```bash
$ docker compose up --build
```

ssh into the client machine

```bash
$ ssh -p localadmin@localhost
```

with the password `localadminpassword`

from there, you can login into an ssh-machine which has gromacs installed:

```bash
$ ssh gromacs@gromacs
```

with password `gromacs`

or you can ssh into the SLURM cluster with

```bash
$ ssh user01@cluster
```

with password `password`.


## LDAP PHP server

Acces via: https://127.0.0.1:10443
User: cn=admin,dc=example,dc=org
Password: adminpassword

**Useful LDAP coomands**

On the LDAP server:

List everything:

```bash
slapcat
ldapsearch -H ldapi:/// -Y EXTERNAL -b "cn=config" -LLL -Q
```

List organizational units:

```bash
ldapsearch -H ldapi:/// -Y EXTERNAL -b "dc=example,dc=org" -LLL -Q
```

List users:

```bash
ldapsearch -H ldapi:/// -Y EXTERNAL -b "ou=users,dc=example,dc=org" -LLL -Q
```
