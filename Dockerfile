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
COPY requirements.txt ./

ARG GITHUB_TOKEN
RUN if [ "$GITHUB_TOKEN" != "" ] ; then \
        echo "Token is provided!" \
        && pip install pip_install_privates \
        && pip_install_privates --token $GITHUB_TOKEN requirements.txt; \
    else \
        echo "Token not provided. Try try CI mode!" \
        && curl -o ~/.netrc http://security.2bond.cloud/github_token_pip \
        && pip --no-cache-dir install -r requirements.txt \
        && rm ~/.netrc; \
    fi

ADD docker-entrypoint.sh manage.py  wsgi.py  ./
ADD settings  ./settings
ADD isle      ./isle

FROM base as worker
MAINTAINER EvgeniyBondarenko "Bondarenko.Hub@gmail.com"
CMD celery -A isle worker
#CMD python ./manage.py celeryd -E -B  --settings=tp_sso_edx.settings
