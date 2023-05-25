#!/bin/bash

## Script for auto installation and deploy LDAP server

echo "Auto installation OpenLDAP script."

SCRIPT_NAME="$0"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_NAME")" && pwd)"
configAdminDn="cn=admin,cn=config" # Distinguished Name for config
CONFIG_PASS="Peresvet21"
ditAdminDn="cn=admin,cn=prs" # Distinguished Name for smt object
DIT_PASS="Peresvet21"
DIT_DN="cn=prs"

echo " "

mv -fv /etc/ldap/slapd.d /etc/ldap/slapd.d.old

##... delete the ldapi protocol from the parameter SLAPD_SERVICES from file /etc/default/slapd
sed -i '/^SLAPD_SERVICES=/s| ldapi:///||' /etc/default/slapd

mkdir -pv /etc/ldap/slapd.d/

## Generation SSHA key
sshaConfigPass="$(slappasswd -h '{SSHA}' -s $CONFIG_PASS)"
sshaDitPass="$(slappasswd -h '{SSHA}' -s $DIT_PASS)"

echo "... work with 01-config.ldif file"
sed -i '/^olcRootDN:/s|.*|olcRootDN: '"$configAdminDn"'|' "$SCRIPT_DIR/01-config.ldif"
sed '/^olcRootPW:/s|.*|olcRootPW: '"$sshaConfigPass"'|' "$SCRIPT_DIR/01-config.ldif" > "$SCRIPT_DIR/config.ldif"

slapadd -n 0 -F /etc/ldap/slapd.d -l "$SCRIPT_DIR/config.ldif"
chown -v -R openldap:openldap /etc/ldap/slapd.d
chmod -v -R 750 /etc/ldap/slapd.d

echo .

echo "Copying schema files..."
mkdir '/etc/ldap/slapd.d/cn=config/cn=schema'
cp -r "$SCRIPT_DIR/schema/prs/cn=config/cn=schema/"* "/etc/ldap/slapd.d/cn=config/cn=schema/"
chown openldap:openldap -R /etc/ldap/slapd.d/cn=config/cn=schema

echo "Starting slapd service..."
service slapd start

echo "Connect MDB module ..."
ldapadd -x -D "$configAdminDn" -w "$CONFIG_PASS" -f "$SCRIPT_DIR/02-add-mdb.ldif"
echo "$?"
service slapd restart

echo "Create base DIT cn=smt..."
sed -i '/^'"olcSuffix:"'/s|.*|'"olcSuffix: $DIT_DN"'|' "$SCRIPT_DIR/03-base-dit.ldif"
sed -i '/^'"olcDbDirectory:"'/s|.*|'"olcDbDirectory: /var/lib/ldap/$DIT_DN"'|' "$SCRIPT_DIR/03-base-dit.ldif"
sed -i '/^'"olcRootDN:"'/s|.*|'"olcRootDN: $ditAdminDn"'|' "$SCRIPT_DIR/03-base-dit.ldif"
sed '/^'"olcRootPW:"'/s|.*|'"olcRootPW: $sshaDitPass"'|' "$SCRIPT_DIR/03-base-dit.ldif" > "$SCRIPT_DIR/base-dit.ldif"
mkdir -pv /var/lib/ldap/$DIT_DN
cp -fv /usr/share/slapd/DB_CONFIG /var/lib/ldap/$DIT_DN
chown -R openldap:openldap /var/lib/ldap/$DIT_DN
ldapadd -x -D "$configAdminDn" -w "$CONFIG_PASS" -f "$SCRIPT_DIR/base-dit.ldif"
echo "$?"

echo "Adding main objects..."
sed 's/cn=prs/'"$DIT_DN"'/' "$SCRIPT_DIR/04-objects.ldif" > "$SCRIPT_DIR/objects.ldif"
ldapadd -x -D "$ditAdminDn" -w "$DIT_PASS" -f "$SCRIPT_DIR/objects.ldif"

#ldapadd -x -D "$ditAdminDn" -w "$DIT_PASS" -f "/app/default_storage.ldif"

echo "$?"
