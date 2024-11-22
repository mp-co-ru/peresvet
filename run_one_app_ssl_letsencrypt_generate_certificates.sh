#!/bin/bash
# Скрипт используется для создания сертификатов для работы платформы.
# Используется на сервере, имеющим выход в интернет и доступным из интернета по имени.

srv=$HOSTNAME
if [ -n "$1" ]
then
    srv=$1
fi

sed -i "s/NGINX_HOST=.*/NGINX_HOST=$srv/" docker/compose/.cont_one_app.env
docker compose --env-file docker/compose/.cont_one_app.env \
    -f docker/compose/docker-compose.nginx.ssl_letsencrypt_generate_certificates.yml up -d

echo 
echo "Генерация сертификатов. Следуйте командам генератора."

docker compose --env-file docker/compose/.cont_one_app.env \
    -f docker/compose/docker-compose.certbot.ssl_letsencrypt_generate_certificates.yml run \
    --rm  certbot certonly --webroot --webroot-path /var/www/certbot/ -d $srv

docker stop nginx_one_app
docker rm nginx_one_app

# создадим сервис обновления сертификатов

dir=`pwd`

echo "[Unit]
Description=Certbot Renewal

[Service]
WorkingDirectory=$dir
ExecStart=docker compose --env-file docker/compose/.cont_one_app.env -f docker/compose/docker-compose.nginx.one_app_ssl_letsencrypt.yml certbot renew --force-renewal --post-hook \"docker exec nginx_one_app nginx -s reload\"" > /etc/systemd/system/certbot-renewal.service

echo "[Unit]
Description=Timer for Certbot Renewal

[Timer]
OnBootSec=300
OnUnitActiveSec=11w

[Install]
WantedBy=multi-user.target" > /etc/systemd/system/certbot-renewal.timer

systemctl reload
systemctl start certbot-renewal.timer
systemctl enable certbot-renewal.timer
