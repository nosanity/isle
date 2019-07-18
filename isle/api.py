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

    def add_authorization_to_kwargs(self, kwargs):
        for key, item in self.authorization.items():
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
        if not self.verify:
            kwargs.setdefault('verify', False)
        self.add_authorization_to_kwargs(kwargs)
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
        self.add_authorization_to_kwargs(kwargs)
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

    def get_activities(self):
        return self.make_request('/api/v2/activity')

    def get_types(self):
        return self.make_request('/api/v2/type')

    def get_contexts(self):
        return self.make_request('/api/v2/context')


class XLEApi(BaseApi):
    name = 'xle'
    base_url = settings.XLE_URL.rstrip('/')
    authorization = {'params': {'app_token': getattr(settings, 'XLE_TOKEN', '')}}
    verify = False

    def get_attendance(self):
        return self.make_request('/api/v1/checkin')

    def get_timetable(self):
        return self.make_request('/api/v1/timetable')


class DpApi(BaseApi):
    name = 'dp'
    base_url = settings.DP_URL.rstrip('/')
    authorization = {'params': {'app_token': getattr(settings, 'DP_TOKEN', '')}}
    verify = False

    def get_metamodel(self, uuid):
        return self.make_request_no_pagination('/api/v1/model/{}'.format(uuid))


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
