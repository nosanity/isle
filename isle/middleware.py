from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import ugettext as _
from social_core.exceptions import AuthCanceled
from social_django.middleware import SocialAuthExceptionMiddleware


class CustomSocialAuthMiddleware(SocialAuthExceptionMiddleware):
    def process_exception(self, request, exception):
        if isinstance(exception, AuthCanceled):
            messages.add_message(request, messages.ERROR, _('Вы отказались от авторизации'))
            url = reverse('login')
            if request.session.get('next'):
                url = '{}?next={}'.format(url, request.session.get('next'))
            return redirect(url)
        return super().process_exception(request, exception)
