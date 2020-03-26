import logging
from django.conf import settings
import requests


class ApiError(Exception):
    pass


class ApiNotFound(ApiError):
    pass


class BadApiResponse(ApiError):
    pass


class BaseApi:
    name = ''
    base_url = ''
    app_token = ''
    authorization = {}
    verify = True

    def update_kwargs(self, kwargs):
        """
        добавление параметров авторизации в запрос
        """
        self._populate_kwargs(kwargs, self.authorization)

    def _populate_kwargs(self, kwargs, upd_dict):
        for key, item in upd_dict.items():
            if key in kwargs and isinstance(kwargs[key], dict):
                kwargs[key].update(item)
            else:
                kwargs[key] = item

    def make_request(self, url, method='GET', **kwargs):
        """
        итератор по всем страницам ответа
        """
        url = '{}{}'.format(self.base_url, url)
        page = 1
        total_pages = None
        kwargs.setdefault('timeout', settings.CONNECTION_TIMEOUT)
        self.update_kwargs(kwargs)
        if not self.verify:
            kwargs.setdefault('verify', False)
        while total_pages is None or page <= total_pages:
            try:
                kwargs['params']['page'] = page
                resp = requests.request(method, url, **kwargs)
                assert resp.ok, 'status_code %s' % resp.status_code
                total_pages = int(resp.headers['X-Pagination-Page-Count'])
                yield resp.json()
                page += 1
            except (ValueError, TypeError, AssertionError):
                logging.exception('Unexpected %s response for url %s' % (self.name, url))
                raise BadApiResponse
            except KeyError:
                logging.error('%s %s response has no header "X-Pagination-Page-Count"' % (self.name, url))
                raise ApiError
            except AssertionError:
                logging.exception('%s connection error' % self.name)
                raise ApiError

    def make_request_no_pagination(self, url, method='GET', **kwargs):
        """
        запрос, не предполагающий пагинацию в ответе
        """
        if not url.startswith(('http://', 'https://')):
            url = '{}{}'.format(self.base_url, url)
        kwargs.setdefault('timeout', settings.CONNECTION_TIMEOUT)
        self.update_kwargs(kwargs)
        if not self.verify:
            kwargs.setdefault('verify', False)
        try:
            resp = requests.request(method, url, **kwargs)
            assert resp.ok, 'status_code %s' % resp.status_code
            return resp.json()
        except (ValueError, TypeError, AssertionError):
            logging.exception('Unexpected %s response for url %s' % (self.name, url))
            raise BadApiResponse
        except AssertionError:
            logging.exception('%s connection error' % self.name)
            raise ApiError

    def django_paginated_request(self, url, method='GET', **kwargs):
        while url:
            resp = self.make_request_no_pagination(url, method=method, **kwargs)
            yield resp
            url = resp['next']

    def health_check(self):
        try:
            resp = requests.head(self.base_url)
            if resp.status_code < 400:
                return 'ok'
            else:
                logging.error('Health check returned code %s for system %s' % (resp.status_code, self.name))
                return resp.status_code
        except requests.RequestException:
            logging.exception('Health check error for system %s' % self.name)


class LabsApi(BaseApi):
    name = 'labs'
    base_url = settings.LABS_URL.rstrip('/')
    authorization = {'params': {'app_token': getattr(settings, 'LABS_TOKEN', '')}}
    verify = False

    def get_activities(self, date_min=None, date_max=None):
        params = {}
        if date_min:
            params['date_min'] = date_min
        if date_max:
            params['date_max'] = date_max
        return self.make_request('/api/v2/activity', params=params)

    def get_types(self):
        return self.make_request('/api/v2/type')

    def get_contexts(self):
        return self.make_request('/api/v2/context')

    def get_context(self, uuid):
        return self.make_request_no_pagination('/api/v2/context/{}'.format(uuid))

    def get_activity(self, uuid):
        return self.make_request_no_pagination('/api/v2/activity/{}'.format(uuid))

    def get_run(self, uuid):
        return self.make_request_no_pagination('/api/v2/run/{}'.format(uuid))

    def get_event(self, uuid):
        return self.make_request_no_pagination('/api/v2/event/{}'.format(uuid))


class XLEApi(BaseApi):
    name = 'xle'
    base_url = settings.XLE_URL.rstrip('/')
    authorization = {'params': {'app_token': getattr(settings, 'XLE_TOKEN', '')}}
    verify = False

    def update_kwargs(self, kwargs):
        super().update_kwargs(kwargs)
        if getattr(settings, 'XLE_PER_PAGE', None):
            self._populate_kwargs(kwargs, {'params': {'per-page': settings.XLE_PER_PAGE}})

    def get_attendance(self, updated_at=None):
        params = {}
        if updated_at:
            params['updated_at'] = updated_at
        return self.make_request('/api/v1/checkin', params=params)

    def get_timetable(self, context=None, updated_at=None):
        params = {}
        if updated_at:
            params['updated_at'] = updated_at
        if context:
            params['context'] = context
        return self.make_request('/api/v1/timetable', params=params)

    def get_checkin(self, checkin_uuid):
        return self.make_request_no_pagination('/api/v1/checkin/{}'.format(checkin_uuid))


class DpApi(BaseApi):
    name = 'dp'
    base_url = settings.DP_URL.rstrip('/')
    authorization = {'params': {'app_token': getattr(settings, 'DP_TOKEN', '')}}
    verify = False

    def get_metamodel(self, uuid):
        return self.make_request_no_pagination('/api/v1/model/{}'.format(uuid))

    def get_frameworks(self):
        return self.make_request('/api/v1/framework')


class SSOApi(BaseApi):
    name = 'sso'
    base_url = settings.SSO_UNTI_URL.rstrip('/')
    authorization = {'headers': {'x-sso-api-key': getattr(settings, 'SSO_API_KEY', '')}}
    verify = False

    def push_user_to_uploads(self, user_id):
        return self.make_request_no_pagination('/api/push-user-to-uploads/', method='POST', json={'unti_id': user_id})

    def get_casbin_data(self):
        return self.make_request_no_pagination('/api/casbin/')


class PTApi(BaseApi):
    name = 'pt'
    base_url = settings.PT_URL.rstrip('/')
    authorization = {'params': {'app_token': getattr(settings, 'PT_TOKEN', '')}}
    verify = False

    def fetch_teams(self):
        return self.make_request('/api/v1/team')


class Openapi(BaseApi):
    name = 'openapi'
    base_url = settings.OPENAPI_URL.rstrip('/')
    authorization = {'headers': {'x-api-key': settings.OPENAPI_KEY}}

    def get_token(self, token_id):
        return self.make_request_no_pagination('/api/user-token/{}/'.format(token_id))

    def get_token_list(self):
        return self.django_paginated_request('/api/user-token/')
