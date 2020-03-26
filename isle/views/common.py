from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from drf_swagger_docs.permissions import SwaggerBasePermission
from rest_framework.pagination import PageNumberPagination, LimitOffsetPagination
from rest_framework.permissions import BasePermission, IsAuthenticated

from isle.models import Event, EventEntry, RunEnrollment


def login(request):
    return render(request, 'login.html', {'next': request.GET.get('next', reverse('index'))})


def context_setter(f):
    """
    декоратор для установки контекста ассистенту при заходе на страницы мероприятия и связанных страниц в случае,
    если его текущий контекст не совпадает с контекстом этого мероприятия
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            uid = kwargs.get('uid')
            if uid:
                event = Event.objects.filter(uid=uid).first()
                if event and request.user.is_authenticated and request.user.has_assistant_role() and \
                        request.user.chosen_context_id != event.context_id:
                    request.user.chosen_context_id = event.context_id
                    request.user.save(update_fields=['chosen_context_id'])
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator(f)


class GetEventMixin:
    @cached_property
    def event(self):
        return get_object_or_404(Event, uid=self.kwargs['uid'])

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def current_user_is_assistant(self):
        return self.request.user.is_assistant_for_context(self.event.context)

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['is_assistant'] = self.current_user_is_assistant
        return data


class GetEventMixinWithAccessCheck(GetEventMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect('{}?next={}'.format(
                reverse('social:begin', kwargs={'backend': 'unti'}), request.get_full_path()
            ))
        if self.current_user_is_assistant or EventEntry.objects.filter(user=request.user, event=self.event).exists() \
                or (self.event.run_id and RunEnrollment.objects.filter(user=request.user, run_id=self.event.run_id)):
            return super().dispatch(request, *args, **kwargs)
        return render(request, 'to_xle.html', {
            'link': getattr(settings, 'XLE_URL', 'https://xle.2035.university/feedback'),
            'event': self.event,
        })


class BaseApiKeyPermission(SwaggerBasePermission, BasePermission):
    _swagger_security_definition = {
        'type': 'apiKey',
        'name': 'x-api-key',
        'in': 'header',
    }
    _swagger_definition_name = 'api_key'

    def has_permission(self, request, view):
        if request.method == 'OPTIONS':
            return True
        api_key = getattr(settings, 'API_KEY', '')
        key = self.get_key_from_request(request)
        if key and api_key and key == api_key:
            return True
        return False

    def get_key_from_request(self, request):
        pass


class IsAuthenticatedCustomized(SwaggerBasePermission, IsAuthenticated):
    _require_authentication = True

    def has_permission(self, request, view):
        if request.method == 'OPTIONS':
            return True
        return super().has_permission(request, view)


class ApiPermission(BaseApiKeyPermission):
    def get_key_from_request(self, request):
        return request.META.get('HTTP_X_API_KEY')


class ApiKeyGetPermission(BaseApiKeyPermission):
    _swagger_security_definition = {
        'type': 'apiKey',
        'name': 'x-api-key',
        'in': 'query',
    }

    def get_key_from_request(self, request):
        return request.query_params.get('x-api-key')


class CustomLimitOffsetPagination(LimitOffsetPagination):
    default_limit = settings.DRF_LIMIT_OFFSET_PAGINATION_DEFAULT
    max_limit = settings.DRF_LIMIT_OFFSET_PAGINATION_MAX


class Paginator(PageNumberPagination):
    page_size = 20


class StatisticsPaginator(PageNumberPagination):
    page_size = 100
