# Скрипт обновления сертификатов Lets Encrypt. Запускается автоматически сервисом.

docker compose --env-file docker/compose/.cont_one_app.env -f docker/compose/docker-compose.nginx.one_app_ssl_letsencrypt.yml run certbot renew --force-renewal && docker exec nginx_one_app nginx -s reload