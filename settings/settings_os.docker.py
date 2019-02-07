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
