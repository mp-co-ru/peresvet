#!/usr/bin/env bash
# coding: utf-8
#
# $ ./gen_crt.sh
#
# Run this script inside `certificates` folder.
#
# This script just calls other three scripts in this directory
# to generate full chain of certificates: root-server-client.
# Sub-scripts are called with default parameters, which are:
# valid period for certificates is 10 years;
# default server name is name of current computer;
# key length is 4096 bits
# default subjs are explained in subscript comments.
#
# As a result, the following structure will be created inside of project's
# parent folder:
# tls
#  - rootCA
#      - rootCA.crt  # root certificate for certificates authority center
#      - rootCA.key  # private key for root certificate
#  - servers
#      - <serverName>
#          - <server_name>.crt   # server's certificate
#          - <server_name>.key   # private key for server's certificate
#          - <server_name>.pem   # <server_name>.crt + <server_name>.key
#  - clients
#      - <client_name>
#          - <client>.crt   # client's certificate
#          - <client>.key   # private key for client's certificate
#
# You may run subscripts independently.

./01.\ gen_root.sh
./02.\ gen_server.sh
./03.\ gen_client.sh
