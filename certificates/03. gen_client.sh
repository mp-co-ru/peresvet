#!/usr/bin/env bash
# coding: utf-8
#
# Run this script inside `certificates` folder.
#
# $ ./03.\ gen_client.sh -d <days> -k <key_length> -s <subj>
#
# d - valid period in days for root certificate; default = 3654 (10 years)
# k - key length in bits; default = 4096
# s - subj info; default = /CN=client-<some_GUID>
#
# Script generates certificate, key and bundle (certificate + key)
# for client and places them to tls/clients/<subj> folder.
# Script supposes that tls/rooCA folder exists and contains
# CA certificate and private key.
# If certificate for <subj> exists it will be recreated.

# Certificate validity period (10 years)
DAYS=3654

# common folder
TLS_DIR="tls"

# Store for center authority (CA) root certificate
ROOT_DIR="${TLS_DIR}/rootCA"

# Path to client's certificate
CLIENT_DIR="${TLS_DIR}/clients"

# default subj
SUBJ="/CN=client-$(uuidgen)"

# CA root key name
ROOT_CA_KEY="${ROOT_DIR}/rootCA.key"

# CA root certificate name
ROOT_CA_CRT="${ROOT_DIR}/rootCA.crt"

# key long
KEY_LENGTH=4096

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
      echo "$ ./03.\ gen_client.sh -d <days> -k <key_length> -s <subj>"
      exit 1
      ;;
  esac
done

CLIENT_DIR="${CLIENT_DIR}/${SUBJ}"

# check tls/rootCA folder
if [[ ! -d ${ROOT_DIR} ]]
then
    echo "There is no `${ROOT_DIR}` folder. Run `01. gen_root.sh` firstly."
    exit 1
fi

# check rootCA certificate and key
if [[ ! -f ${ROOT_CA_CRT} ]]
then
    echo "There is no rootCA certificate. Run `01. gen_root.sh` firstly."
    exit 1
fi
if [[ ! -f ${ROOT_CA_KEY} ]]
then
    echo "There is no rootCA key. Run `01. gen_root.sh` firstly."
    exit 1
fi

# create tls/client
if [[ -d ${CLIENT_DIR} ]]
then
    rm -r ${CLIENT_DIR}
fi
mkdir -p ${CLIENT_DIR}

echo "Create client private key"
openssl genrsa -out ${CLIENT_DIR}/client.key ${KEY_LENGTH}

echo "Create CSR for client. Attention: name of client is '${SUBJ}'"
openssl req -new -key "${CLIENT_DIR}/client.key" -out "${CLIENT_DIR}/client.csr" \
    -subj "${SUBJ}"

echo "Create client certificate"
openssl x509 -req -in "${CLIENT_DIR}/client.csr" \
    -CA ${ROOT_CA_CRT} -CAkey ${ROOT_CA_KEY} -CAcreateserial \
    -out "${CLIENT_DIR}/client.crt" -days ${DAYS}
