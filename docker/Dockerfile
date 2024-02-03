FROM nginx/unit:1.28.0-python3.10

ENV LDAP_ORGANISATION mycompany
ENV LDAP_DOMAIN mycompany.com
ENV LDAP_ADMIN_PASSWORD 123456

#RUN rm /bin/sh && ln -s /bin/bash /bin/sh

WORKDIR /home
RUN pip3 install pipenv
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    build-essential python3-dev \
    libldap2-dev libsasl2-dev tox lcov valgrind

RUN bash -c "DEBIAN_FRONTEND=noninteractive apt install -q -y slapd ldap-utils"

# ---------------------- alerts ---------------------------------------------------------------------------------
WORKDIR /usr/src
RUN mkdir alerts_api_crud alerts_model_crud alerts_app alerts_app_api
COPY src/services/alerts/api_crud/Pipfile /usr/src/alerts_api_crud/
COPY src/services/alerts/model_crud/Pipfile /usr/src/alerts_model_crud/
COPY src/services/alerts/app/Pipfile /usr/src/alerts_app/
COPY src/services/alerts/app_api/Pipfile /usr/src/alerts_app_api/

WORKDIR /usr/src/alerts_api_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/alerts_model_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/alerts_app
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/alerts_app_api
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

RUN apt-get -y purge slapd

RUN addgroup --gid 1024 volume_group
RUN usermod -a -G volume_group unit

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY docker/docker-files/alerts/config_nginx.unit_alerts.all.json /docker-entrypoint.d/

# копируем исходники --------------------------------------------
RUN mkdir /usr/src/alerts_api_crud/log
RUN chown unit:volume_group /usr/src/alerts_api_crud/log
ADD src/common/ /usr/src/alerts_api_crud/src/common
COPY src/__init__.py /usr/src/alerts_api_crud/src/
RUN rm -r -f /usr/src/alerts_api_crud/src/common/__pycache__
WORKDIR /usr/src/alerts_api_crud/src
RUN mkdir services
WORKDIR /usr/src/alerts_api_crud/src/services
ADD src/services/alerts/api_crud alerts/api_crud
WORKDIR /usr/src/alerts_api_crud

RUN mkdir /usr/src/alerts_model_crud/log
RUN chown unit:volume_group /usr/src/alerts_model_crud/log
ADD src/common/ /usr/src/alerts_model_crud/src/common
COPY src/__init__.py /usr/src/alerts_model_crud/src/
RUN rm -r -f /usr/src/alerts_model_crud/src/common/__pycache__
WORKDIR /usr/src/alerts_model_crud/src
RUN mkdir services
WORKDIR /usr/src/alerts_model_crud/src/services
ADD src/services/alerts/model_crud alerts/model_crud
WORKDIR /usr/src/alerts_model_crud

RUN mkdir /usr/src/alerts_app/log
RUN chown unit:volume_group /usr/src/alerts_app/log
ADD src/common/ /usr/src/alerts_app/src/common
COPY src/__init__.py /usr/src/alerts_app/src/
RUN rm -r -f /usr/src/alerts_app/src/common/__pycache__
WORKDIR /usr/src/alerts_app/src
RUN mkdir services
WORKDIR /usr/src/alerts_app/src/services
ADD src/services/alerts/app alerts/app
WORKDIR /usr/src/alerts_app

RUN mkdir /usr/src/alerts_app_api/log
RUN chown unit:volume_group /usr/src/alerts_app_api/log
ADD src/common/ /usr/src/alerts_app_api/src/common
COPY src/__init__.py /usr/src/alerts_app_api/src/
RUN rm -r -f /usr/src/alerts_app_api/src/common/__pycache__
WORKDIR /usr/src/alerts_app_api/src
RUN mkdir services
WORKDIR /usr/src/alerts_app_api/src/services
ADD src/services/alerts/app_api alerts/app_api
WORKDIR /usr/src/alerts_app_api
# ------------------------------------------------------------

#EXPOSE 85 86


#------------------------------ connectors -------------------------------------------------------------------
WORKDIR /usr/src


RUN mkdir connectors_api_crud connectors_model_crud connectors_app
COPY src/services/connectors/api_crud/Pipfile /usr/src/connectors_api_crud/
COPY src/services/connectors/model_crud/Pipfile /usr/src/connectors_model_crud/
COPY src/services/connectors/app/Pipfile /usr/src/connectors_app/
WORKDIR /usr/src/connectors_api_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/connectors_model_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/connectors_app
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

RUN apt-get -y purge slapd

RUN addgroup --gid 1024 volume_group
RUN usermod -a -G volume_group unit

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY docker/docker-files/connectors/config_nginx.unit_connectors.all.json /docker-entrypoint.d/

# копируем исходники --------------------------------------------
RUN mkdir /usr/src/connectors_api_crud/log
RUN chown unit:volume_group /usr/src/connectors_api_crud/log
ADD src/common/ /usr/src/connectors_api_crud/src/common
COPY src/__init__.py /usr/src/connectors_api_crud/src/
RUN rm -r -f /usr/src/connectors_api_crud/src/common/__pycache__
WORKDIR /usr/src/connectors_api_crud/src
RUN mkdir services
WORKDIR /usr/src/connectors_api_crud/src/services
ADD src/services/connectors/api_crud connectors/api_crud
WORKDIR /usr/src/connectors_api_crud

RUN mkdir /usr/src/connectors_model_crud/log
RUN chown unit:volume_group /usr/src/connectors_model_crud/log
ADD src/common/ /usr/src/connectors_model_crud/src/common
COPY src/__init__.py /usr/src/connectors_model_crud/src/
RUN rm -r -f /usr/src/connectors_model_crud/src/common/__pycache__
WORKDIR /usr/src/connectors_model_crud/src
RUN mkdir services
WORKDIR /usr/src/connectors_model_crud/src/services
ADD src/services/connectors/model_crud connectors/model_crud
WORKDIR /usr/src/connectors_model_crud

RUN mkdir /usr/src/connectors_app/log
RUN chown unit:volume_group /usr/src/connectors_app/log
ADD src/common/ /usr/src/connectors_app/src/common
COPY src/__init__.py /usr/src/connectors_app/src/
RUN rm -r -f /usr/src/connectors_model_crud/src/common/__pycache__
WORKDIR /usr/src/connectors_app/src
RUN mkdir services
WORKDIR /usr/src/connectors_app/src/services
ADD src/services/connectors/app connectors/app
WORKDIR /usr/src/connectors_app
# ------------------------------------------------------------

#EXPOSE 83 84

#------------------------------ dataStorages --------------------------------------------------
WORKDIR /usr/src
RUN mkdir dataStorages_api_crud dataStorages_model_crud dataStorages_app_psql dataStorages_app_vm
COPY src/services/dataStorages/api_crud/Pipfile /usr/src/dataStorages_api_crud/
COPY src/services/dataStorages/model_crud/Pipfile /usr/src/dataStorages_model_crud/
COPY src/services/dataStorages/app/postgresql/Pipfile /usr/src/dataStorages_app_psql/
COPY src/services/dataStorages/app/victoriametrics/Pipfile /usr/src/dataStorages_app_vm/

WORKDIR /usr/src/dataStorages_api_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/dataStorages_model_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/dataStorages_app_psql
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/dataStorages_app_vm
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

RUN apt-get -y purge slapd

RUN addgroup --gid 1024 volume_group
RUN usermod -a -G volume_group unit

# устранение ошибки, когда приложение FastAPI из-под nginx.unit не может
# присоединиться к базе PostgreSQL
RUN usermod -a -G root unit
RUN chmod g+wx /root

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY docker/docker-files/dataStorages/config_nginx.unit_dataStorages.all.json /docker-entrypoint.d/

# копируем исходники --------------------------------------------
RUN mkdir /usr/src/dataStorages_api_crud/log
RUN chown unit:volume_group /usr/src/dataStorages_api_crud/log
ADD src/common/ /usr/src/dataStorages_api_crud/src/common
COPY src/__init__.py /usr/src/dataStorages_api_crud/src/
RUN rm -r -f /usr/src/dataStorages_api_crud/src/common/__pycache__
WORKDIR /usr/src/dataStorages_api_crud/src
RUN mkdir services
COPY src/services/__init__.py /usr/src/dataStorages_api_crud/src/services/
WORKDIR /usr/src/dataStorages_api_crud/src/services
ADD src/services/dataStorages/api_crud dataStorages/api_crud
RUN rm -r -f /usr/src/dataStorages_api_crud/src/services/dataStorages/api_crud/__pycache__

RUN mkdir /usr/src/dataStorages_model_crud/log
RUN chown unit:volume_group /usr/src/dataStorages_model_crud/log
ADD src/common/ /usr/src/dataStorages_model_crud/src/common
COPY src/__init__.py /usr/src/dataStorages_model_crud/src/
RUN rm -r -f /usr/src/dataStorages_model_crud/src/common/__pycache__
WORKDIR /usr/src/dataStorages_model_crud/src
RUN mkdir services
COPY src/services/__init__.py /usr/src/dataStorages_model_crud/src/services/
WORKDIR /usr/src/dataStorages_model_crud/src/services
ADD src/services/dataStorages/model_crud dataStorages/model_crud
RUN rm -r -f /usr/src/dataStorages_model_crud/src/services/dataStorages/model_crud/__pycache__

RUN mkdir /usr/src/dataStorages_app_psql/log
RUN chown unit:volume_group /usr/src/dataStorages_app_psql/log
ADD src/common/ /usr/src/dataStorages_app_psql/src/common
COPY src/__init__.py /usr/src/dataStorages_app_psql/src/
RUN rm -r -f /usr/src/dataStorages_app_psql/src/common/__pycache__
WORKDIR /usr/src/dataStorages_app_psql/src
RUN mkdir -p services/dataStorages/app
COPY src/services/__init__.py /usr/src/dataStorages_app_psql/src/services/
COPY src/services/dataStorages/__init__.py /usr/src/dataStorages_app_psql/src/services/dataStorages/
COPY src/services/dataStorages/app/*.py /usr/src/dataStorages_app_psql/src/services/dataStorages/app/
WORKDIR /usr/src/dataStorages_app_psql/src/services
ADD src/services/dataStorages/app/postgresql dataStorages/app/postgresql
RUN rm -r -f /usr/src/dataStorages_app_psql/src/services/dataStorages/app/postgresql/__pycache__

RUN mkdir /usr/src/dataStorages_app_vm/log
RUN chown unit:volume_group /usr/src/dataStorages_app_vm/log
ADD src/common/ /usr/src/dataStorages_app_vm/src/common
COPY src/__init__.py /usr/src/dataStorages_app_vm/src/
RUN rm -r -f /usr/src/dataStorages_app_vm/src/common/__pycache__
WORKDIR /usr/src/dataStorages_app_vm/src
RUN mkdir -p services/dataStorages/app
COPY src/services/__init__.py /usr/src/dataStorages_app_vm/src/services/
COPY src/services/dataStorages/__init__.py /usr/src/dataStorages_app_vm/src/services/dataStorages/
COPY src/services/dataStorages/app/*.py /usr/src/dataStorages_app_vm/src/services/dataStorages/app/
WORKDIR /usr/src/dataStorages_app_vm/src/services
ADD src/services/dataStorages/app/victoriametrics dataStorages/app/victoriametrics
RUN rm -r -f /usr/src/dataStorages_app_vm/src/services/dataStorages/app/victoriametrics/__pycache__
# ------------------------------------------------------------

# EXPOSE 82

#------------------------------ graphana - пропустил --------------------------------------------------



#-------------------------------- ldap - пропустил --------------------------------------------------



#-------------------------------- locust - пропустил --------------------------------------------------



#-------------------------------- methods --------------------------------------------------

WORKDIR /usr/src
RUN mkdir methods_api_crud methods_model_crud methods_app
COPY src/services/methods/api_crud/Pipfile /usr/src/methods_api_crud/
COPY src/services/methods/model_crud/Pipfile /usr/src/methods_model_crud/
COPY src/services/methods/app/Pipfile /usr/src/methods_app/

WORKDIR /usr/src/methods_api_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/methods_model_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/methods_app
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

RUN apt-get -y purge slapd

RUN addgroup --gid 1024 volume_group
RUN usermod -a -G volume_group unit

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY docker/docker-files/methods/config_nginx.unit_methods.all.json /docker-entrypoint.d/

# копируем исходники --------------------------------------------
RUN mkdir /usr/src/methods_api_crud/log
RUN chown unit:volume_group /usr/src/methods_api_crud/log
ADD src/common/ /usr/src/methods_api_crud/src/common
COPY src/__init__.py /usr/src/methods_api_crud/src/
RUN rm -r -f /usr/src/methods_api_crud/src/common/__pycache__
WORKDIR /usr/src/methods_api_crud/src
RUN mkdir services
WORKDIR /usr/src/methods_api_crud/src/services
ADD src/services/methods/api_crud methods/api_crud
WORKDIR /usr/src/methods_api_crud

RUN mkdir /usr/src/methods_model_crud/log
RUN chown unit:volume_group /usr/src/methods_model_crud/log
ADD src/common/ /usr/src/methods_model_crud/src/common
COPY src/__init__.py /usr/src/methods_model_crud/src/
RUN rm -r -f /usr/src/methods_model_crud/src/common/__pycache__
WORKDIR /usr/src/methods_model_crud/src
RUN mkdir services
WORKDIR /usr/src/methods_model_crud/src/services
ADD src/services/methods/model_crud methods/model_crud
WORKDIR /usr/src/methods_model_crud

RUN mkdir /usr/src/methods_app/log
RUN chown unit:volume_group /usr/src/methods_app/log
ADD src/common/ /usr/src/methods_app/src/common
COPY src/__init__.py /usr/src/methods_app/src/
RUN rm -r -f /usr/src/methods_app/src/common/__pycache__
WORKDIR /usr/src/methods_app/src
RUN mkdir services
WORKDIR /usr/src/methods_app/src/services
ADD src/services/methods/app methods/app
WORKDIR /usr/src/methods_app
# ------------------------------------------------------------

# EXPOSE 87

#-------------------------------- nginx - пропустил --------------------------------------------------



#-------------------------------- objects --------------------------------------------------

WORKDIR /usr/src
RUN mkdir objects_api_crud objects_model_crud
COPY src/services/objects/api_crud/Pipfile /usr/src/objects_api_crud/
COPY src/services/objects/model_crud/Pipfile /usr/src/objects_model_crud/
WORKDIR /usr/src/objects_api_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/objects_model_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

RUN apt-get -y purge slapd

RUN addgroup --gid 1024 volume_group
RUN usermod -a -G volume_group unit

# копируем исходники --------------------------------------------
RUN mkdir /usr/src/objects_api_crud/log
RUN chown unit:volume_group /usr/src/objects_api_crud/log
ADD src/common/ /usr/src/objects_api_crud/src/common
COPY src/__init__.py /usr/src/objects_api_crud/src/
RUN rm -r -f /usr/src/objects_api_crud/src/common/__pycache__
WORKDIR /usr/src/objects_api_crud/src
RUN mkdir services
WORKDIR /usr/src/objects_api_crud/src/services
ADD src/services/objects/api_crud objects/api_crud
WORKDIR /usr/src/objects_api_crud

RUN mkdir /usr/src/objects_model_crud/log
RUN chown unit:volume_group /usr/src/objects_model_crud/log
ADD src/common/ /usr/src/objects_model_crud/src/common
COPY src/__init__.py /usr/src/objects_model_crud/src/
RUN rm -r -f /usr/src/objects_model_crud/src/common/__pycache__
WORKDIR /usr/src/objects_model_crud/src
RUN mkdir services
WORKDIR /usr/src/objects_model_crud/src/services
ADD src/services/objects/model_crud objects/model_crud
WORKDIR /usr/src/objects_model_crud
# ------------------------------------------------------------

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY docker/docker-files/objects/config_nginx.unit_objects.all.json /docker-entrypoint.d/

#EXPOSE 83


#-------------------------------- objects --------------------------------------------------



#-------------------------------- у рэббита нет докера --------------------------------------------------


#-------------------------------- retranslator --------------------------------------------------

WORKDIR /usr/src
RUN mkdir retranslator_app
COPY src/services/retranslator/app/Pipfile /usr/src/retranslator_app/

WORKDIR /usr/src/retranslator_app
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

RUN apt-get -y purge slapd

RUN addgroup --gid 1024 volume_group
RUN usermod -a -G volume_group unit

# копируем исходники --------------------------------------------
RUN mkdir /usr/src/retranslator_app/log
RUN chown unit:volume_group /usr/src/retranslator_app/log
ADD src/common/ /usr/src/retranslator_app/src/common
COPY src/__init__.py /usr/src/retranslator_app/src/
WORKDIR /usr/src/retranslator_app/src
RUN mkdir services
WORKDIR /usr/src/retranslator_app/src/services
ADD src/services/retranslator/app retranslator/app
WORKDIR /usr/src/retranslator_app
# ------------------------------------------------------------

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY docker/docker-files/retranslator/config_nginx.unit_retranslator.json /docker-entrypoint.d/

# EXPOSE 88 89


#-------------------------------- shedules --------------------------------------------------

WORKDIR /usr/src
RUN mkdir schedules_api_crud schedules_model_crud schedules_app
COPY src/services/schedules/api_crud/Pipfile /usr/src/schedules_api_crud/
COPY src/services/schedules/model_crud/Pipfile /usr/src/schedules_model_crud/
COPY src/services/schedules/app/Pipfile /usr/src/schedules_app/

WORKDIR /usr/src/schedules_api_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/schedules_model_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/schedules_app
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

RUN apt-get -y purge slapd

RUN addgroup --gid 1024 volume_group
RUN usermod -a -G volume_group unit

# копируем исходники --------------------------------------------
RUN mkdir /usr/src/schedules_api_crud/log
RUN chown unit:volume_group /usr/src/schedules_api_crud/log
ADD src/common/ /usr/src/schedules_api_crud/src/common
COPY src/__init__.py /usr/src/schedules_api_crud/src/
RUN rm -r -f /usr/src/schedules_api_crud/src/common/__pycache__
WORKDIR /usr/src/schedules_api_crud/src
RUN mkdir services
WORKDIR /usr/src/schedules_api_crud/src/services
ADD src/services/schedules/api_crud schedules/api_crud
WORKDIR /usr/src/schedules_api_crud

RUN mkdir /usr/src/schedules_model_crud/log
RUN chown unit:volume_group /usr/src/schedules_model_crud/log
ADD src/common/ /usr/src/schedules_model_crud/src/common
COPY src/__init__.py /usr/src/schedules_model_crud/src/
RUN rm -r -f /usr/src/schedules_model_crud/src/common/__pycache__
WORKDIR /usr/src/schedules_model_crud/src
RUN mkdir services
WORKDIR /usr/src/schedules_model_crud/src/services
ADD src/services/schedules/model_crud schedules/model_crud
WORKDIR /usr/src/schedules_model_crud

RUN mkdir /usr/src/schedules_app/log
RUN chown unit:volume_group /usr/src/schedules_app/log
ADD src/common/ /usr/src/schedules_app/src/common
COPY src/__init__.py /usr/src/schedules_app/src/
RUN rm -r -f /usr/src/schedules_model_crud/src/common/__pycache__
WORKDIR /usr/src/schedules_app/src
RUN mkdir services
WORKDIR /usr/src/schedules_app/src/services
ADD src/services/schedules/app schedules/app
WORKDIR /usr/src/schedules_app
# ------------------------------------------------------------

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY docker/docker-files/schedules/config_nginx.unit_schedules.all.json /docker-entrypoint.d/

# EXPOSE 85


#-------------------------------- tags --------------------------------------------------

WORKDIR /usr/src
RUN mkdir tags_api_crud tags_model_crud tags_app tags_app_api
COPY src/services/tags/api_crud/Pipfile /usr/src/tags_api_crud/
COPY src/services/tags/model_crud/Pipfile /usr/src/tags_model_crud/
COPY src/services/tags/app/Pipfile /usr/src/tags_app/
COPY src/services/tags/app_api/Pipfile /usr/src/tags_app_api/

WORKDIR /usr/src/tags_api_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/tags_model_crud
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/tags_app
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

WORKDIR /usr/src/tags_app_api
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

RUN apt-get -y purge slapd


RUN addgroup --gid 1024 volume_group
RUN usermod -a -G volume_group unit

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY docker/docker-files/tags/config_nginx.unit_tags.all.json /docker-entrypoint.d/

# копируем исходники --------------------------------------------
RUN mkdir /usr/src/tags_api_crud/log
RUN chown unit:volume_group /usr/src/tags_api_crud/log
ADD src/common/ /usr/src/tags_api_crud/src/common
COPY src/__init__.py /usr/src/tags_api_crud/src/
RUN rm -r -f /usr/src/tags_api_crud/src/common/__pycache__
WORKDIR /usr/src/tags_api_crud/src
RUN mkdir services
WORKDIR /usr/src/tags_api_crud/src/services
ADD src/services/tags/api_crud tags/api_crud
WORKDIR /usr/src/tags_api_crud

RUN mkdir /usr/src/tags_model_crud/log
RUN chown unit:volume_group /usr/src/tags_model_crud/log
ADD src/common/ /usr/src/tags_model_crud/src/common
COPY src/__init__.py /usr/src/tags_model_crud/src/
RUN rm -r -f /usr/src/tags_model_crud/src/common/__pycache__
WORKDIR /usr/src/tags_model_crud/src
RUN mkdir services
WORKDIR /usr/src/tags_model_crud/src/services
ADD src/services/tags/model_crud tags/model_crud
WORKDIR /usr/src/tags_model_crud

RUN mkdir /usr/src/tags_app/log
RUN chown unit:volume_group /usr/src/tags_app/log
ADD src/common/ /usr/src/tags_app/src/common
COPY src/__init__.py /usr/src/tags_app/src/
RUN rm -r -f /usr/src/tags_app/src/common/__pycache__
WORKDIR /usr/src/tags_app/src
RUN mkdir services
WORKDIR /usr/src/tags_app/src/services
ADD src/services/tags/app tags/app
WORKDIR /usr/src/tags_app

RUN mkdir /usr/src/tags_app_api/log
RUN chown unit:volume_group /usr/src/tags_app_api/log
ADD src/common/ /usr/src/tags_app_api/src/common
COPY src/__init__.py /usr/src/tags_app_api/src/
RUN rm -r -f /usr/src/tags_app_api/src/common/__pycache__
WORKDIR /usr/src/tags_app_api/src
RUN mkdir services
WORKDIR /usr/src/tags_app_api/src/services
ADD src/services/tags/app_api tags/app_api
WORKDIR /usr/src/tags_app_api
# ------------------------------------------------------------

# EXPOSE 80 81

