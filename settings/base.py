import os
from raven.contrib.django.models import client
from raven.contrib.celery import register_signal, register_logger_signal

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '5$&ql62&7dhu6tq6++)o_j2+*rt$@#m_)ke8t8mk9uc4#n5-n8'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'dal',
    'dal_select2',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'isle',
    'social_core',
    'social_django',
    'rest_framework',
    'rest_framework.authtoken',
    'django_carrier_client',
    'djcelery',
    'django_user_agents'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'isle.middleware.CustomSocialAuthMiddleware',
    'django_user_agents.middleware.UserAgentMiddleware',
]

ROOT_URLCONF = 'settings.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'isle.context_processors.context',
            ],
            'builtins': [
                'isle.templatetags.helpers',
            ],
        },
    },
]

WSGI_APPLICATION = 'wsgi.application'


# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'Asia/Vladivostok'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

STATIC_URL = '/static/'

AUTH_USER_MODEL = 'isle.User'
AUTHENTICATION_BACKENDS = (
    'isle.auth.UNTIBackend',
    'django.contrib.auth.backends.ModelBackend'
)
LOGIN_URL = '/login/unti/'
LOGOUT_REDIRECT_URL = 'https://my.2035.university'

AWS_S3_FILE_OVERWRITE = False

### константы, которые можно переписать ###
# название тега, по которому приложение понимает, что пользователь ассистент
ASSISTANT_TAGS_NAME = ['assistant', 'island_assistant']
# максимальный размер загружаемых файлов
MAXIMUM_ALLOWED_FILE_SIZE = 5120
# на сколько кешировать данные, получаемые по апи
API_DATA_CACHE_TIME = 60 * 30
# максимальное количество одновременно загружаемых файлов пользователем
MAX_PARALLEL_UPLOADS = 10
# сколько активностей запрашивать на странице (если не используется снэпшот для обновления эвентов)
ACTIVITIES_PER_PAGE = 20

### параметры, которые надо указать в local_settings ###
# урл sso без / в конце
SSO_UNTI_URL = ''
# ключ апи sso
SSO_API_KEY = ''
# key и secret для oauth авторизации
SOCIAL_AUTH_UNTI_KEY = ''
SOCIAL_AUTH_UNTI_SECRET = ''
# таймаут для запросов
CONNECTION_TIMEOUT = 20
# таймаут для head запроса к файлу
HEAD_REQUEST_CONNECTION_TIMEOUT = 5
LABS_URL = ''
LABS_TOKEN = ''

XLE_URL = ''
XLE_TOKEN = ''

DP_URL = ''
DP_TOKEN = ''

PT_URL = ''
PT_TOKEN = ''

OPENAPI_URL = ''
OPENAPI_KEY = ''

# базовый урл uploads
BASE_URL = ''

# uuid эвента, в который будут грузиться данные для чартов
API_DATA_EVENT = ''

# данные для коммуникации с кафкой
KAFKA_TOPIC = 'uploads'
KAFKA_HOST = ''
KAFKA_PORT = 80
KAFKA_TOKEN = ''
KAFKA_PROTOCOL = 'http'
KAFKA_TOPIC_SSO = 'sso'
KAFKA_TOPIC_OPENAPI = 'openapi'

# количество всех материалов в выбранных материалов, более которого генерация выгрузки должна идти асинхронно
MAX_MATERIALS_FOR_SYNC_GENERATION = 500
# максимальное количество одновременно генерируемых выгрузок для пользователя
MAX_PARALLEL_CSV_GENERATIONS = 5
# время в секундах, после которого генерация считается проваленой
TIME_TO_FAIL_CSV_GENERATION = 2 * 3600
# максимальное количество пользователей, которых можно добавить на мероприятие за один раз
MAXIMUM_EVENT_MEMBERS_TO_ADD = 100
# количество мероприятий/активностей на одной странице
PAGINATE_EVENTS_BY = 100
# дефолтная пагинация при использовании LimitOffsetPagination
DRF_LIMIT_OFFSET_PAGINATION_DEFAULT = 20
# максимальное количество записей на странице при использовании LimitOffsetPagination
DRF_LIMIT_OFFSET_PAGINATION_MAX = 50
# включить отображение команд, сформированных в pt, на мероприятиях
ENABLE_PT_TEAMS = False
# ссылка на now
NOW_URL = '/'
HEADER_CABINET_URL = 'https://now.2035.university'
HEADER_FULL_SCHEDULE_URL = 'https://xle.u2035test.ru/island1022/timetable/all'
HEADER_MY_SCHEDULE_URL = 'https://xle.u2035test.ru/island1022/timetable'
# время, которое статистика пользователя валидна, в секундах
STATISTICS_VALID_FOR = 60 * 30
# периодичность "очистки" удаленных из xle записей на прогоны в часах
XLE_RUN_ENROLLMENT_DELETE_CHECK_TIME = 24
# интервал автосохранения конспектов в миллисекундах
SUMMARY_SAVE_INTERVAL = 60000

BLEACH_ALLOWED_TAGS = ['a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'strong',
                       'ul', 'p', 'img', 'table', 'td', 'tr', 'tbody', 'th', 'thead', 'h1', 'h2', 'h3',
                       'h4', 'h5', 'h6', 'h7', 's', 'hr', 'div', 'br']

BLEACH_ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'acronym': ['title'],
    'abbr': ['title'],
    'img': ['src', 'style', 'alt'],
    'div': ['style']
}

DEFAULT_CSV_ENCODING = 'utf-8'
CSV_ENCODING_FOR_OS = {}

DEFAULT_TRACE_DATA_JSON = [
   {
      "name": "Презентация спикера",
      "trace_type": "Презентация"
   },
   {
      "name": "Видео",
      "trace_type": "Видео"
   },
   {
      "name": "Потоковое аудио",
      "trace_type": "Аудио"
   },
   {
      "name": "Фото мероприятия/участников/продуктов",
      "trace_type": "Фото"
   },
   {
      "name": "Фото флипчартов",
      "trace_type": "Фото"
   },
   {
      "name": "Другое",
      "trace_type": "Файл"
   }
]

from os import getenv
from split_settings.tools import include
settings_path = getenv('UPLOADS_SETTINGS_PATH', 'local_settings.py')
try:
    include(settings_path)
except IOError as e:
    print("CRITICAL: {}".format(e))
    exit(1)

define = [
    'SSO_UNTI_URL', 'SSO_API_KEY', 'SSO_API_KEY', 'SOCIAL_AUTH_UNTI_SECRET', 'LABS_URL', 'LABS_TOKEN',
    'XLE_URL', 'XLE_TOKEN', 'DP_URL', 'DP_TOKEN', 'BASE_URL', 'PT_URL', 'PT_TOKEN', 'OPENAPI_URL', 'OPENAPI_KEY',
]

for name in define:
    if not locals().get(name):
        raise Exception('"{}" must be defined'.format(name))

import djcelery
djcelery.setup_loader()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },
    'formatters': {
        'verbose': {
            'format': '%(levelname)s  %(asctime)s  %(module)s '
                      '%(process)d  %(thread)d  %(message)s',
            'datefmt': "%Y-%m-%d %H:%M:%S",
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        }
    },
    'loggers': {
        'django.db.backends': {
            'level': 'ERROR',
            'handlers': ['console'],
            'propagate': False,
        },
        'raven': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'sentry.errors': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
    },
}

if locals().get('RAVEN_CONFIG', None):
    INSTALLED_APPS += ('raven.contrib.django.raven_compat',)
    register_signal(client)
    register_logger_signal(client)
    LOGGING['root']['handlers'].append('sentry')
    LOGGING['handlers']['sentry'] = {
        'level': 'ERROR',
        'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
        'tags': {'custom-tag': 'x'},
    }

if locals().get('LOGSTASH_HOST') and locals().get('LOGSTASH_PORT'):
    LOGGING['root']['handlers'].append('logstash')
    tags = locals().get('LOGSTASH_TAGS', None)
    if isinstance(tags, list) and 'uploads' not in tags:
        tags.append('uploads')
    else:
        tags = ['uploads']
    LOGGING['handlers']['logstash'] = {
        'level': locals().get('LOGSTASH_LEVEL', 'INFO'),
        'class': 'logstash.TCPLogstashHandler',
        'host': LOGSTASH_HOST,
        'port': LOGSTASH_PORT,
        'version': 1,
        'ssl': locals().get('LOGSTASH_SSL', False),
        'keyfile': locals().get('LOGSTASH_KEYFILE', None),
        'certfile': locals().get('LOGSTASH_CERTFILE', None),
        'ca_certs': locals().get('LOGSTASH_CA_CERTS', None),
        'message_type': locals().get('LOGSTASH_MESSAGE_TYPE', 'logstash'),
        'tags': tags,
        'fqdn': locals().get('LOGSTASH_FQDN', False),
    }
