from collections import Iterable
from django.core.cache import caches


DEFAULT_CACHE = caches["default"]


class NullValue:
    def __bool__(self):
        return False


class BaseCache:
    KEY_PART = ''
    CACHE_TIME = None
    _allow_null = False

    @classmethod
    def get(cls, *args):
        key = cls.get_cache_key(*args)
        val = DEFAULT_CACHE.get(key)
        if cls._allow_null and isinstance(val, NullValue):
            return None
        if val is None:
            val = cls.create_value(*args)
            cls.set(val, *args)
        if cls._allow_null and isinstance(val, NullValue):
            val = None
        return val

    @classmethod
    def get_cache_timeout(cls, value):
        return cls.CACHE_TIME

    @classmethod
    def set(cls, val, *args):
        if val is not None:
            key = cls.get_cache_key(*args)
            timeout = cls.get_cache_timeout(val)
            if timeout is not None:
                DEFAULT_CACHE.set(key, val, timeout=timeout)
            else:
                DEFAULT_CACHE.set(key, val)

    @classmethod
    def discard(cls, *args):
        key = cls.get_cache_key(*args)
        DEFAULT_CACHE.delete(key)

    @classmethod
    def discard_many(cls, args_list):
        keys = []
        for x in args_list:
            item = x if isinstance(x, Iterable) else [x]
            keys.append(cls.get_cache_key(*item))
        DEFAULT_CACHE.delete_many(keys)

    @classmethod
    def create_value(cls, *args):
        raise NotImplementedError()

    @classmethod
    def get_cache_key(cls, *args):
        return ':'.join([cls.KEY_PART] + ['%s' % x for x in cls.transform_args(*args)])

    @classmethod
    def transform_args(cls, *args):
        return args


class UserAvailableContexts(BaseCache):
    KEY_PART = 'user-ctx'
    _allow_null = True

    @classmethod
    def create_value(cls, *args):
        return args[0].available_context_uuids

    @classmethod
    def transform_args(cls, *args):
        return [args[0].id]
