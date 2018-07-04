import os

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '5$&ql62&7dhu6tq6++)o_j2+*rt$@#m_)ke8t8mk9uc4#n5-n8'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'isle',
    'social_core',
    'social_django',
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

WSGI_APPLICATION = 'settings.wsgi.application'


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
ASSISTANT_TAG_NAME = 'assistant'
# максимальный размер загружаемых файлов
MAXIMUM_ALLOWED_FILE_SIZE = 5
# значение в секундах, +- от текущего времени когда событие считается новым
CURRENT_EVENT_DELTA = 60 * 60
# на сколько кешировать данные, получаемые по апи
API_DATA_CACHE_TIME = 60 * 30

### параметры, которые надо указать в local_settings ###
# урл sso без / в конце
SSO_UNTI_URL = ''
# key и secret для oauth авторизации
SOCIAL_AUTH_UNTI_KEY = ''
SOCIAL_AUTH_UNTI_SECRET = ''
# урл, по которому надо получать токен в ILE
ILE_GET_TOKEN_URL = 'https://ile.u2035dev.ru/api/token/'
# таймаут для запросов в ILE
CONNECTION_TIMEOUT = 20
# логин и пароль пользователя в ILE
ILE_TOKEN_USER = ('user', 'password')
# урл ручки для получения всех нужных данных по эвентам и участникам в ILE
ILE_EVENTS_URL = ''

from .local_settings import *
