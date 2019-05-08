import logging
from casbin import persist
from casbin.enforcer import Enforcer
from casbin.model import Model
from casbin.persist.adapter import Adapter
from .models import CasbinData


class TextAdapter(Adapter):
    def __init__(self, policy):
        self.policy = policy

    def load_policy(self, model):
        for line in self.policy.splitlines():
            if not line.strip():
                continue
            persist.load_policy_line(line.strip(), model)


def get_enforcer():
    data = CasbinData.objects.first()
    if data:
        m = Model()
        m.load_model_from_text(data.model)
        return Enforcer(m, TextAdapter(data.policy))


def enforce(sub, ctx, obj_type, action):
    try:
        enforcer = get_enforcer()
        if not enforcer:
            return False
        return enforcer.enforce(sub, ctx, obj_type, action)
    except Exception:
        logging.exception('Enforcer failed')
        return False
