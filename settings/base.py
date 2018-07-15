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
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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

### константы, которые можно переписать ###
# название тега, по которому приложение понимает, что пользователь ассистент
ASSISTANT_TAGS_NAME = ['assistant', 'island_assistant']
# максимальный размер загружаемых файлов
MAXIMUM_ALLOWED_FILE_SIZE = 100
# значение в секундах, +- от текущего времени когда событие считается новым
CURRENT_EVENT_DELTA = 60 * 60
# на сколько кешировать данные, получаемые по апи
API_DATA_CACHE_TIME = 60 * 30
# мероприятия каких типов отображать
VISIBLE_EVENT_TYPES = ['клуб мышления', 'визионерская лекция', 'мастер-класс', 'x-labs']
# максимальное количество одновременно загружаемых файлов пользователем
MAX_PARALLEL_UPLOADS = 10
# использовать снэпшот для обновления эвентов
USE_ILE_SNAPSHOT = True
# сколько активностей запрашивать на странице (если не используется снэпшот для обновления эвентов)
ACTIVITIES_PER_PAGE = 20

### параметры, которые надо указать в local_settings ###
# урл sso без / в конце
SSO_UNTI_URL = ''
# key и secret для oauth авторизации
SOCIAL_AUTH_UNTI_KEY = ''
SOCIAL_AUTH_UNTI_SECRET = ''
# таймаут для запросов в ILE
CONNECTION_TIMEOUT = 20
# логин и пароль пользователя в ILE
ILE_TOKEN_USER = ('user', 'password')
# базовый урл ILE
ILE_BASE_URL = 'https://ile2.u2035dev.ru'
# урл для получения токена в ILE
ILE_TOKEN_PATH = '/api/token/'
# путь к апи для получения снэпшота
ILE_SNAPSHOT_PATH = '/api/snapshot/'
# нужно ли валидировать сертификат ILE
ILE_VERIFY_CERTIFICATE = False
# урл для получения трейсов из LABS
LABS_TRACES_API_URL = 'https://labs.u2035dev.ru/api/v1/tracetype?app_token=7at0hbdmabmtfl0y'

from .local_settings import *
