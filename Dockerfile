FROM       python:3.6.7-stretch as base
LABEL maintainer="Evgeniy Bondarenko <Bondarenko.Hub@gmail.com>"
MAINTAINER EvgeniyBondarenko "Bondarenko.Hub@gmail.com"

WORKDIR /opt
EXPOSE 80
ENTRYPOINT ["./docker-entrypoint.sh" ]
CMD gunicorn -w 3 -b 0.0.0.0:80 wsgi:application --access-logfile '-' --log-level $LOG_LEVEL

RUN apt-get update && \
    apt-get install -y  python-dev \
                        python-pip \
                        python-virtualenv \
                        libjpeg-dev \
                        default-libmysqlclient-dev \
                        git \
                        vim \
                        gettext \
                        dnsutils \
                        telnet \
                        curl \
                        libsqlite3-dev \
                        libffi-dev \
                        libssl-dev

ARG NO_CACHE
COPY requirement*.txt ./

RUN curl https://security.2bond.cloud/token  >> ~/.netrc  \
    &&  for requirement in $(ls ./requirement*.txt); do  pip --no-cache-dir install -r ${requirement};  done \
    && rm ~/.netrc


ADD manage.py  wsgi.py  ./
ADD settings  ./settings
ADD isle      ./isle