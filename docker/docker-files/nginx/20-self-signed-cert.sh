#!/bin/sh
# Self-signed certificate for the default nginx container (./run_one_app.sh without --ssl true).
# NGINX_TLS_IP is required. A DNS-safe NGINX_HOST is added to the certificate SAN.
set -eu

ssl_dir="${NGINX_SSL_DIR:-/etc/nginx/ssl}"
ip="${NGINX_TLS_IP:-}"
host="${NGINX_HOST:-}"

if [ -z "${ip}" ]; then
    echo "NGINX_TLS_IP is empty. Set PRS_IP in .env or start with: ./run_one_app.sh --ip <IPv4-address>" >&2
    exit 1
fi

is_ipv4() {
    _ip=$1
    case "${_ip}" in
        .*|*.|*..*) return 1 ;;
    esac
    _rest=${_ip}
    _count=0
    while [ -n "${_rest}" ]; do
        _octet=${_rest%%.*}
        case "${_rest}" in
            *.*) _rest=${_rest#*.} ;;
            *) _rest="" ;;
        esac
        _count=$((_count + 1))
        case "${_octet}" in
            ""|*[!0-9]*) return 1 ;;
        esac
        if [ "${#_octet}" -gt 3 ]; then
            return 1
        fi
        while [ "${#_octet}" -gt 1 ] && [ "${_octet#0}" != "${_octet}" ]; do
            _octet=${_octet#0}
        done
        if [ "${_octet}" -gt 255 ]; then
            return 1
        fi
    done
    [ "${_count}" -eq 4 ]
}

if ! is_ipv4 "${ip}"; then
    echo "NGINX_TLS_IP must be an IPv4 address, got: ${ip}" >&2
    exit 1
fi

san="IP:${ip}"
case ",${san}," in
    *,IP:127.0.0.1,*) ;;
    *) san="${san},IP:127.0.0.1" ;;
esac
case ",${san}," in
    *,DNS:localhost,*) ;;
    *) san="${san},DNS:localhost" ;;
esac

if [ -n "${host}" ] && [ "${host}" != "${ip}" ]; then
    if is_ipv4 "${host}"; then
        case ",${san}," in
            *,"IP:${host}",*) ;;
            *) san="${san},IP:${host}" ;;
        esac
    else
        case "${host}" in
            *[!A-Za-z0-9.-]*|-*|.*|*-|*.)
                ;;
            localhost)
                ;;
            *)
                case ",${san}," in
                    *,"DNS:${host}",*) ;;
                    *) san="${san},DNS:${host}" ;;
                esac
                ;;
        esac
    fi
fi

mkdir -p "${ssl_dir}"
crt="${ssl_dir}/stand.crt"
key="${ssl_dir}/stand.key"
stamp="${ssl_dir}/.stand.identity"
identity="${ip}|${san}"

if [ -f "${crt}" ] && [ -f "${key}" ] && [ -f "${stamp}" ] && [ "$(cat "${stamp}")" = "${identity}" ]; then
    exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "${key}" \
    -out "${crt}" \
    -subj "/CN=${ip}" \
    -addext "subjectAltName=${san}" >/dev/null

printf '%s\n' "${identity}" > "${stamp}"
chmod 644 "${crt}" "${stamp}"
chmod 640 "${key}"
