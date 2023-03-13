Восстановление бэкапа иерархии
==============================
Предположим, что конейнер c ldap-сервером называется ldap.

::

    -- копируем файл бэкапа (prs.ldif) в контейнер
    $ docker cp prs.ldif ldap:/app
    -- заходим в контейнер ldap и попадаем сразу в каталог /app,
    -- в который мы скопировали файл prs.ldif
    $ docker exec -it ldap bash
    -- удаляем старые файлы иерархии
    # rm /var/lib/ldap/cn\=prs/*.mdb
    -- восстанавливаем базу ldap
    # slapadd -l prs.ldif
    -- меняем права доступа на файлы
    # chown -R openldap:openldap /var/lib/ldap/cn\=prs/
    -- выходим из конейнера
    # exit
    -- и перезапускаем его
    $ docker stop ldap
    $ docker start ldap
