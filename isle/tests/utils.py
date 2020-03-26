from isle.casbin import _thread_locals, LOCAL_ENFORCER_KEY, LOCAL_MODEL_VERSION_KEY
from isle.models import CasbinData, Context


model = '''
[request_definition]
r = sub, con, obj, act

[policy_definition]
p = sub, con, obj, act, eft

[policy_effect]
e = some(where (p.eft == allow))

[role_definition]
g = _, _, _

[matchers]
m = g(r.sub,p.sub,r.con) && p.act == r.act && p.obj == r.obj && p.con == r.con
'''.strip()


class CasbinDataMixin:
    def create_casbin_data(self, admin=None):
        policy = []
        for ctx in Context.objects.all():
            policy.append('p, admin, {context}, file, upload, allow'.format(context=ctx.uuid))
            if admin:
                policy.append('g, {user_id}, admin, {context}'.format(user_id=admin.unti_id, context=ctx.uuid))
        CasbinData.objects.update_or_create(id=1, defaults={'model': model, 'policy': '\n'.join(policy)})
        setattr(_thread_locals, LOCAL_MODEL_VERSION_KEY, None)
        setattr(_thread_locals, LOCAL_ENFORCER_KEY, None)
