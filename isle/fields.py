import re
from django.db import models
import unicodedata


def escape_utf8mb4_chars(text):
    # символы UTF8MB4
    re_4 = re.compile(u'[\U00010000-\U0010ffff]')
    result = text
    for match in re_4.finditer(text):
        character = match.group()
        try:
            name = unicodedata.name(character)
            name = ':{}:'.format(name.lower().replace(' ', '_'))
            result = re.sub(character, name, result)
        except ValueError:
            # если символ не найден, он удаляется
            result = re.sub(character, '', result)
    return result


class SafeUTF8Text(models.TextField):
    def to_python(self, value):
        return escape_utf8mb4_chars(super().to_python(value))
