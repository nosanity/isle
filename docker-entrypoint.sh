#!/bin/bash -ex
# by Evgeniy Bondarenko <Bondarenko.Hub@gmail.com>


export UPLOADS_SETTINGS_PATH='settings_os.docker.py'
export FORWARDED_ALLOW_IPS=${FORWARDED_ALLOW_IPS:-'*'}
export LOG_LEVEL=${LOG_LEVEL:-"WARNING"}


if [ "${MIGRATION}" == 1 ] || [ "${MIGRATION}" == 'TRUE' ] ||  [ "${MIGRATION}" == 'true' ] || [ "${MIGRATION}" == 'True' ]; then
    # Migarations
#    ./manage.py makemigrations
    ./manage.py migrate
    # Build static and localization
#    echo "start  Build static and localization"
#    ./manage.py collectstatic
#    ./manage.py compilemessages
#Create Admin user
#    ./manage.py create_admin_user
# Replace Domain in site tab (in admin panel)
#    ./manage.py check_default_site
# Add OAth Client
#    ./manage.py check_default_clients
fi
echo starting

exec "$@"