import os

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
LOGIN_URL = '/login/'

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
# таймаут для запросов в ILE
CONNECTION_TIMEOUT = 20
# таймаут для head запроса к файлу
HEAD_REQUEST_CONNECTION_TIMEOUT = 5
# логин и пароль пользователя в ILE
ILE_TOKEN_USER = ('user', 'token')
# базовый урл ILE
ILE_BASE_URL = 'https://ile2.u2035dev.ru'
# урл для получения токена в ILE
ILE_TOKEN_PATH = '/api/token/'
# путь к апи для получения снэпшота
ILE_SNAPSHOT_PATH = '/api/snapshot/'
# нужно ли валидировать сертификат ILE
ILE_VERIFY_CERTIFICATE = False
LABS_URL = ''
LABS_TOKEN = ''

XLE_URL = ''
XLE_TOKEN = ''

DP_URL = ''
DP_TOKEN = ''

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
XLE_TOPIC = 'xle'

# количество всех материалов в выбранных материалов, более которого генерация выгрузки должна идти асинхронно
MAX_MATERIALS_FOR_SYNC_GENERATION = 500
# максимальное количество одновременно генерируемых выгрузок для пользователя
MAX_PARALLEL_CSV_GENERATIONS = 5
# время в секундах, после которого генерация считается проваленой
TIME_TO_FAIL_CSV_GENERATION = 2 * 3600

DEFAULT_CSV_ENCODING = 'utf-8'
CSV_ENCODING_FOR_OS = {}

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
    'XLE_URL', 'XLE_TOKEN', 'DP_URL', 'DP_TOKEN', 'BASE_URL'
]

for name in define:
    if not locals().get(name):
        raise Exception('"{}" must be defined'.format(name))

import djcelery
djcelery.setup_loader()
