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

API_KEY = os.getenv('API_KEY', '')
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
PT_URL = os.getenv('PT_URL', '')
PT_TOKEN = os.getenv('PT_TOKEN', '')
OPENAPI_URL = os.getenv('OPENAPI_URL', '')
OPENAPI_KEY = os.getenv('OPENAPI_KEY', '')
BASE_URL = os.getenv('BASE_URL', '')
API_DATA_EVENT = os.getenv('API_DATA_EVENT', '')
KAFKA_HOST = os.getenv('KAFKA_HOST', '')
KAFKA_PORT = int(os.getenv('KAFKA_PORT', 80))
KAFKA_TOKEN = os.getenv('KAFKA_TOKEN', '')
KAFKA_PROTOCOL = os.getenv('KAFKA_PROTOCOL', 'http')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'uploads')
KAFKA_TOPIC_SSO = os.getenv('KAFKA_TOPIC_SSO', 'sso')
XLE_TOPIC = os.getenv('KAFKA_TOPIC_XLE', 'xle')
KAFKA_TOPIC_OPENAPI = os.getenv('KAFKA_TOPIC_OPENAPI', 'openapi')

BROKER_URL = os.getenv('UPLOADS_BROKER_URL', '')

MAX_MATERIALS_FOR_SYNC_GENERATION = int(os.getenv('MAX_MATERIALS_FOR_SYNC_GENERATION', 500))
MAX_PARALLEL_CSV_GENERATIONS = int(os.getenv('MAX_PARALLEL_CSV_GENERATIONS', 5))
TIME_TO_FAIL_CSV_GENERATION = int(os.getenv('TIME_TO_FAIL_CSV_GENERATION', 2 * 3600))
MAXIMUM_EVENT_MEMBERS_TO_ADD = int(os.getenv('MAXIMUM_EVENT_MEMBERS_TO_ADD', 100))
PAGINATE_EVENTS_BY = int(os.getenv('PAGINATE_EVENTS_BY', 100))
DRF_LIMIT_OFFSET_PAGINATION_DEFAULT = int(os.getenv('DRF_LIMIT_OFFSET_PAGINATION_DEFAULT', 20))
DRF_LIMIT_OFFSET_PAGINATION_MAX = int(os.getenv('DRF_LIMIT_OFFSET_PAGINATION_MAX', 50))
ENABLE_PT_TEAMS = str(os.getenv('LOGSTASH_SSL', False)) == 'True'
NOW_URL = os.getenv('NOW_URL', '/')
HEADER_CABINET_URL = os.getenv('HEADER_CABINET_URL', 'https://now.2035.university')
HEADER_FULL_SCHEDULE_URL = os.getenv('HEADER_FULL_SCHEDULE_URL', 'https://xle.u2035test.ru/island1022/timetable/all')
HEADER_MY_SCHEDULE_URL = os.getenv('HEADER_MY_SCHEDULE_URL', 'https://xle.u2035test.ru/island1022/timetable')
STATISTICS_VALID_FOR = int(os.getenv('STATISTICS_VALID_FOR', 60 * 30))
XLE_RUN_ENROLLMENT_DELETE_CHECK_TIME = int(os.getenv('XLE_RUN_ENROLLMENT_DELETE_CHECK_TIME', 24))
SUMMARY_SAVE_INTERVAL = int(os.getenv('SUMMARY_SAVE_INTERVAL', 60000))

DWH_HOST = os.getenv('DWH_HOST', '')
DWH_PORT = int(os.getenv('DWH_PORT', '3306'))
DWH_USER = os.getenv('DWH_USER', '')
DWH_PASSWD = os.getenv('DWH_PASSWD', '')
DWH_LABS_DB_NAME = os.getenv('DWH_LABS_DB_NAME', 'labs')
DWH_XLE_DB_NAME = os.getenv('DWH_LABS_DB_NAME', 'xle')
DWH_DP_DB_NAME = os.getenv('DWH_LABS_DB_NAME', 'dp')
DWH_PT_DB_NAME = os.getenv('DWH_LABS_DB_NAME', 'people')

LOGSTASH_HOST = os.getenv('LOGSTASH_HOST', None)
LOGSTASH_PORT = os.getenv('LOGSTASH_PORT', None)
LOGSTASH_SSL = str(os.getenv('LOGSTASH_SSL', False)) == 'True'
LOGSTASH_FQDN = str(os.getenv('LOGSTASH_FQDN', False)) == 'True'
LOGSTASH_KEYFILE = os.getenv('LOGSTASH_KEYFILE', None)
LOGSTASH_CERTFILE = os.getenv('LOGSTASH_CERTFILE', None)
LOGSTASH_CA_CERTS = os.getenv('LOGSTASH_CA_CERTS', None)
LOGSTASH_MESSAGE_TYPE = os.getenv('LOGSTASH_MESSAGE_TYPE', 'logstash')
LOGSTASH_TAGS = json.loads(os.getenv('LOGSTASH_TAGS', '[]')) or None
LOGSTASH_LEVEL = os.getenv('LOGSTASH_LEVEL', 'INFO')

LOGOUT_REDIRECT_URL = os.getenv('LOGOUT_REDIRECT_URL', 'https://my.2035.university')

MEDIA_URL = os.getenv('MEDIA_URL', '/media/')
if os.getenv('MEDIA_ROOT', None):
    MEDIA_ROOT = os.getenv('MEDIA_ROOT')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_ROOT = os.getenv('STATIC_ROOT', os.path.join(BASE_DIR, 'static_col'))
if os.getenv('DEFAULT_FILE_STORAGE', None) == 'storages.backends.s3boto.S3BotoStorage':
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto.S3BotoStorage'
    AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', None)
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', None)
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', None)
    AWS_S3_HOST = os.getenv('AWS_S3_HOST', None)
    AWS_S3_CALLING_FORMAT = os.getenv('AWS_S3_CALLING_FORMAT', 'boto.s3.connection.OrdinaryCallingFormat')
    AWS_S3_CUSTOM_DOMAIN = '{}.{}'.format(AWS_STORAGE_BUCKET_NAME, AWS_S3_HOST)
ALLOW_FILE_UPLOAD = str(os.getenv('ALLOW_FILE_UPLOAD', True)) == 'True'

API_DATA_EVENT = os.getenv('API_DATA_EVENT', '')
SPECIAL_CONTEXT_UUID = os.getenv('SPECIAL_CONTEXT_UUID', '')

if os.getenv('RAVEN_CONFIG_DSN', ''):
    RAVEN_CONFIG = {
        'dsn': os.getenv('RAVEN_CONFIG_DSN', ''),
    }

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': os.getenv('CACHE_LOCATION_default', '127.0.0.1:11211'),
        'TIMEOUT': int(os.getenv('CACHE_TIMEOUT_default', 604800)),
    }
}

if str(os.getenv('USE_WHITENOISE_MIDDLEWARE', True)) == 'True':
    MIDDLEWARE = [MIDDLEWARE[0]] + ['whitenoise.middleware.WhiteNoiseMiddleware'] + MIDDLEWARE[1:]

if str(os.getenv('USE_DOGSLOW_MIDDLEWARE', False)) == 'True':
    DOGSLOW_TIMER = int(os.getenv('DOGSLOW_TIMER', 10))
    DOGSLOW_LOG_TO_FILE = str(os.getenv('DOGSLOW_LOG_TO_FILE', False)) == 'True'
    if DOGSLOW_LOG_TO_FILE:
        DOGSLOW_OUTPUT = os.getenv('DOGSLOW_OUTPUT', '/tmp')
    MIDDLEWARE = ['dogslow.WatchdogMiddleware', ] + MIDDLEWARE

# в котором часу по UTC производить обновление всех мероприятий
UPDATE_ALL_EVENTS_UTC_HOUR = int(os.getenv('UPDATE_ALL_EVENTS_UTC_HOUR', 0))
