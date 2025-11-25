#!/usr/bin/env bash
# coding: utf-8
#
# Run this script inside `certificates` folder.
#
# $ ./01.\ gen_root.sh -d <days> -k <key_length> -s <subj>
#
# d - valid period in days for root certificate; default = 3654 (10 years)
# k - key length in bits; default = 4096
# s - subj info for certificate; default = /CN=root_ca_center
#
# script generates certificate for certificates authority center
# it creates directory structure
# tls
#  - rootCA
# at the project's parent folder
# if folder tls/rootCA already exists it will be recreated
#

# Certificate validity period (10 years)
DAYS=3654

# common folder
TLS_DIR="tls"

# Store for center authority (CA) root certificate
ROOT_DIR="${TLS_DIR}/rootCA"

# CA root key name
ROOT_CA_KEY="${ROOT_DIR}/rootCA.key"

# CA root certificate name
ROOT_CA_CRT="${ROOT_DIR}/rootCA.crt"

# key long
KEY_LENGTH=4096

SUBJ="/CN=root_ca_center"

# Data
#COUNTRY="RU"  # Country Name
#STATE="Moscow"  # State or Province
#LOCALITY="Moscow"  # Locality Name
#ORG="Organization"  # Organization Name
#OU="IT-Dept"  # Organizational Unit Name
#CN="org-ca-server"  # Common Name
#EMAIL="support@example.com"  # Email Address

while [[ $# -gt 0 ]]; do
  case $1 in
    -d)
      DAYS="$2"
      shift # past argument
      shift # past value
      ;;
    -k)
      KEY_LENGTH="$2"
      shift # past argument
      shift # past value
      ;;
    -s)
      SUBJ="$2"
      shift # past argument
      shift # past value
      ;;
    -*)
      echo "Unknown option $1"
      echo "Run: "
      echo "$ gen_root.sh -d <days> -k <key_length>"
      exit 1
      ;;
  esac
done

# create tls folder
if [[ ! -d ${TLS_DIR} ]]
then
    mkdir ${TLS_DIR}
fi

# create tls/root
if [[ -d ${ROOT_DIR} ]]
then
    rm -r ${ROOT_DIR}
fi
mkdir ${ROOT_DIR}

echo "Create root certificate and key..."
openssl req -new -newkey rsa:${KEY_LENGTH} -nodes -keyout ${ROOT_CA_KEY} \
     -x509 -days ${DAYS} -out ${ROOT_CA_CRT} \
     -subj ${SUBJ}

SRV_BUNDLE=${ROOT_DIR}/rootCA.pem

cat ${ROOT_CA_CRT} ${ROOT_CA_KEY} > ${SRV_BUNDLE}

echo "Root certificate and key are generated."
