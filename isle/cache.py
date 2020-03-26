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

    def get(self, *args):
        key = self.get_cache_key(*args)
        val = DEFAULT_CACHE.get(key)
        if self._allow_null and isinstance(val, NullValue):
            return None
        if val is None:
            val = self.create_value(*args)
            self.set(val, *args)
        if self._allow_null and isinstance(val, NullValue):
            val = None
        return val

    def get_cache_timeout(self, value):
        return self.CACHE_TIME

    def set(self, val, *args):
        if val is not None:
            key = self.get_cache_key(*args)
            timeout = self.get_cache_timeout(val)
            if timeout is not None:
                DEFAULT_CACHE.set(key, val, timeout=timeout)
            else:
                DEFAULT_CACHE.set(key, val)

    def discard(self, *args):
        key = self.get_cache_key(*args)
        DEFAULT_CACHE.delete(key)

    def discard_many(self, args_list):
        keys = []
        for x in args_list:
            item = x if isinstance(x, Iterable) else [x]
            keys.append(self.get_cache_key(*item))
        DEFAULT_CACHE.delete_many(keys)

    def create_value(self, *args):
        raise NotImplementedError()

    def get_cache_key(self, *args):
        return ':'.join([self.get_key_part()] + ['%s' % x for x in self.transform_args(*args)])

    def get_key_part(self):
        return self.KEY_PART

    def transform_args(self, *args):
        return args


def get_user_available_contexts(user):
    """
    контексты, в которых у пользователя есть права ассистента
    """
    from isle.models import Context
    uuids = set(Context.objects.values_list('uuid', flat=True))
    uuid_cache_key = {UserContextAssistantCache().get_cache_key(user, ctx): ctx for ctx in uuids}
    results = DEFAULT_CACHE.get_many(uuid_cache_key.keys())
    results = {uuid_cache_key[k]: v for k, v in results.items()}
    not_found_ctxs = uuids - set(results.keys())
    for ctx in not_found_ctxs:
        results[ctx] = UserContextAssistantCache().get(user, ctx)
    return [i[0] for i in results.items() if i[1]]


class UserContextAssistantCache(BaseCache):
    KEY_PART = 'v%s:ctx-assistant'

    def __init__(self):
        from .casbin import get_current_enforcer_and_version
        __, version = get_current_enforcer_and_version()
        self.KEY_PART = self.KEY_PART % version

    def create_value(self, *args):
        return args[0].is_assistant_for_context(args[1])

    def transform_args(self, *args):
        return [args[0].id, args[1]]

    def set_many(self, arg_value_list):
        result = {self.get_cache_key(*item[0]): item[1] for item in arg_value_list}
        timeout = self.get_cache_timeout(None)
        if timeout is not None:
            DEFAULT_CACHE.set_many(result, timeout=timeout)
        else:
            DEFAULT_CACHE.set_many(result)
