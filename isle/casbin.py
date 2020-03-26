import logging
from threading import local
from casbin import persist
from casbin.enforcer import Enforcer
from casbin.model import Model
from casbin.persist.adapter import Adapter
from .models import CasbinData

_thread_locals = local()
LOCAL_ENFORCER_KEY = '__local_casbin_enforcer'
LOCAL_MODEL_VERSION_KEY = '__local_casbin_model_version'


class TextAdapter(Adapter):
    def __init__(self, policy):
        self.policy = policy

    def load_policy(self, model):
        for line in self.policy.splitlines():
            if not line.strip():
                continue
            persist.load_policy_line(line.strip(), model)


def get_current_enforcer_and_version():
    version = getattr(_thread_locals, LOCAL_MODEL_VERSION_KEY, None)
    enforcer = getattr(_thread_locals, LOCAL_ENFORCER_KEY, None)
    if version is None or enforcer is None:
        data = CasbinData.objects.order_by('id').first()
        if version is None:
            version = data and data.model_version or 0
            setattr(_thread_locals, LOCAL_MODEL_VERSION_KEY, version)
        if enforcer is None:
            try:
                m = Model()
                m.load_model_from_text(data.model)
                enforcer = Enforcer(m, TextAdapter(data.policy))
            except Exception:
                logging.exception('Failed to get enforcer')
                enforcer = False
            setattr(_thread_locals, LOCAL_ENFORCER_KEY, enforcer)
    return enforcer, version


def enforce(sub, ctx, obj_type, action):
    try:
        enforcer, __ = get_current_enforcer_and_version()
        if not enforcer:
            return False
        return enforcer.enforce(sub, ctx, obj_type, action)
    except Exception:
        logging.exception('Enforcer failed')
        return False
