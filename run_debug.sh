# Скрипт запуска контейнеров в режиме отладки.
# Запускается с двумя параметрами: идентификатор контейнера
# и имя сервиса для отладки.

if [ $# -ne 2 ]
then
    echo "Формат запуска скрипта: "
    echo "./run_debug.sh <id контейнера> <имя сервиса>"
    exit
fi

container_ip=$(docker inspect $1 | \
    grep -E '"IPAddress": "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"' | \
    grep -oE '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}')

echo "IP контейнера: $container_ip"

echo "Создаём конфигурацию для запуска отладки сервиса '$2' в контейнере '$1'..."
$PWD/.venv/bin/python docker/docker-files/common/debug_create_launch.py $1 $2 $container_ip
echo "...конфигурация создана."

docker cp docker/docker-files/common/debug_setup.py $1:/usr/src/
echo "Запускаем процесс для отладки в контейнере..."
docker exec -it $1 python /usr/src/debug_setup.py $2
