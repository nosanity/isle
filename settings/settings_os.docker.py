import json
import os

if os.getenv('SECRET_KEY'):
    SECRET_KEY = os.getenv('SECRET_KEY')

DEBUG = str(os.getenv('DEBUG', True)) == 'True'

DATABASES = {
    'default': {
        'ENGINE': os.getenv('default_ENGINE', 'django.db.backends.mysql'),
        'NAME': os.getenv('default_NAME', 'uploads'),
        'USER': os.getenv('default_USER', 'uploads'),
        'PASSWORD': os.getenv('default_PASSWORD', 'uploads'),
        'HOST':     os.getenv('default_HOST', '127.0.0.1'),
        'PORT':     int(os.getenv('default_PORT', 3306)),
        'TEST_CHARSET': 'utf8',
    },
}

if os.getenv('ASSISTANT_TAGS_NAME'):
    ASSISTANT_TAGS_NAME = json.loads(os.getenv('ASSISTANT_TAGS_NAME'))

MAXIMUM_ALLOWED_FILE_SIZE = os.getenv('MAXIMUM_ALLOWED_FILE_SIZE', 5120)
MAX_PARALLEL_UPLOADS = os.getenv('MAX_PARALLEL_UPLOADS', 10)

SSO_UNTI_URL = os.getenv('SSO_UNTI_URL', '')
SSO_API_KEY = os.getenv('SSO_API_KEY', '')
SOCIAL_AUTH_UNTI_KEY = os.getenv('SOCIAL_AUTH_UNTI_KEY', '')
SOCIAL_AUTH_UNTI_SECRET = os.getenv('SOCIAL_AUTH_UNTI_SECRET', '')
CONNECTION_TIMEOUT = int(os.getenv('CONNECTION_TIMEOUT', 20))
HEAD_REQUEST_CONNECTION_TIMEOUT = int(os.getenv('HEAD_REQUEST_CONNECTION_TIMEOUT', 5))
LABS_URL = os.getenv('LABS_URL', '')
LABS_TOKEN = os.getenv('LABS_TOKEN', '')
XLE_URL = os.getenv('XLE_URL', '')
XLE_TOKEN = os.getenv('XLE_TOKEN', '')
DP_URL = os.getenv('DP_URL', '')
DP_TOKEN = os.getenv('DP_TOKEN', '')
BASE_URL = os.getenv('BASE_URL', '')
API_DATA_EVENT = os.getenv('API_DATA_EVENT', '')
KAFKA_HOST = os.getenv('KAFKA_HOST', '')
KAFKA_PORT = int(os.getenv('KAFKA_PORT', 80))
KAFKA_TOKEN = os.getenv('KAFKA_TOKEN', '')
KAFKA_PROTOCOL = os.getenv('KAFKA_PROTOCOL', 'http')


def get_broker_val(key, default):
    uploads_key = 'UPLOADS_{}'.format(key)
    if os.getenv(uploads_key):
        return os.getenv(uploads_key)
    return os.getenv(key, default)

BROKER_HOST = get_broker_val('BROKER_HOST', 'localhost')
BROKER_PORT = int(get_broker_val('BROKER_PORT', 5672))
BROKER_VHOST = get_broker_val('BROKER_VHOST', "/")
BROKER_USER = get_broker_val('BROKER_USER', "myuser")
BROKER_PASSWORD = get_broker_val('BROKER_PASSWORD', "mypassword")
BROKER_URL = "amqp://{user}:{password}@{host}:{port}/{vhost}".format(
    user=BROKER_USER, password=BROKER_PASSWORD, host=BROKER_HOST, port=BROKER_PORT, vhost=BROKER_VHOST
)

MAX_MATERIALS_FOR_SYNC_GENERATION = int(os.getenv('MAX_MATERIALS_FOR_SYNC_GENERATION', 500))
MAX_PARALLEL_CSV_GENERATIONS = int(os.getenv('MAX_PARALLEL_CSV_GENERATIONS', 5))
TIME_TO_FAIL_CSV_GENERATION = int(os.getenv('TIME_TO_FAIL_CSV_GENERATION', 2 * 3600))
MAXIMUM_EVENT_MEMBERS_TO_ADD = int(os.getenv('MAXIMUM_EVENT_MEMBERS_TO_ADD', 100))
PAGINATE_EVENTS_BY = int(os.getenv('PAGINATE_EVENTS_BY', 100))
