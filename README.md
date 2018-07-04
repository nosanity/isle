## Установка

    Используется python3
    pip install -r requirements.txt
    Создать файл с настройками settings/local_settings.py
    ./manage.py migrate

## Файл настроек

    Стандартно, заполнить настройки DATABASES, MEDIA_URL, прописать настройки MEDIA_ROOT или
    настройки для s3. Для того, чтобы можно было загружать файлы также надо указать
    ALLOW_FILE_UPLOAD = True

    см. settings/base.py для остальных параметров, которые надо указать
