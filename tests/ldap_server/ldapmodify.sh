ldapmodify -Y EXTERNAL <<EOF
dn: uid=user01,ou=People,dc=directory,dc=nh
changetype: modify
replace: loginShell
loginShell: /bin/zsh
EOF