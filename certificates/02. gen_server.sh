#!/usr/bin/env bash
# coding: utf-8
#
# Run this script inside `certificates` folder.
#
# $ ./02.\ gen_server.sh -h <server_name> -d <days> -k <key_length> -s <subj>
#
# h - server_name; default = local host name
# d - valid period in days for root certificate; default = 3654 (10 years)
# k - key length in bits; default = 4096
# s - subj info; default = /CN=<server_name>
#
# Script generates certificate, key and bundle (certificate + key)
# for server and places them to tls/servers/<server_name> folder.
# Script supposes that tls/rooCA folder exists and contains
# CA certificate and private key.
# If certificate for <server_name> exists it will be recreated.

# Server Name
SRV_NAME=$(hostname)

# Subj
SUBJ="/CN=${SRV_NAME}"

# Certificate validity period (10 years)
DAYS=3654

# common folder
TLS_DIR="tls"

# Store for center authority (CA) root certificate
ROOT_DIR="${TLS_DIR}/rootCA"

# Path to server's certificate
SRV_DIR="${TLS_DIR}/servers"

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
    -h)
      SRV_NAME=$2
      shift # past argument
      shift # past value
      ;;
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
      echo "$ ./02.\ gen_server.sh -h <server_name> -d <days> -k <key_length> -s <subj>"
      exit 1
      ;;
  esac
done

SRV_DIR="${SRV_DIR}/${SRV_NAME}"

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

# create tls/server
if [[ -d ${SRV_DIR} ]]
then
    rm -r ${SRV_DIR}
fi
mkdir -p ${SRV_DIR}

SRV_KEY=${SRV_DIR}/${SRV_NAME}.key
SRV_CERT=${SRV_DIR}/${SRV_NAME}.crt
SRV_CSR=${SRV_DIR}/${SRV_NAME}.csr
SRV_BUNDLE=${SRV_DIR}/${SRV_NAME}.pem

echo "Create private key for server certificate..."
openssl genrsa -out ${SRV_KEY} ${KEY_LENGTH}

echo "Create request"
openssl req -sha256 -new -key ${SRV_KEY} -out ${SRV_CSR} \
        -subj ${SUBJ}

echo "Sign the CSR by own root CA certificate"
openssl x509 -req -in ${SRV_CSR} -CA ${ROOT_CA_CRT} -CAkey ${ROOT_CA_KEY} \
    -CAcreateserial -out ${SRV_CERT} -days ${DAYS}

echo "Create bundle: server_cert + server_key"
cat ${SRV_CERT} ${SRV_KEY} > ${SRV_BUNDLE}

echo "Certificate for ${SRV_NAME} created."
