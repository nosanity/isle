import logging
from django.conf import settings
from django.core.cache import caches
from django.utils import timezone
import requests

DEFAULT_CACHE = caches['default']


class ApiError(Exception):
    pass


class ApiNotFound(ApiError):
    pass


class BadApiResponse(ApiError):
    pass


class Api:
    """
    класс, реализующий запрос к ручке ILE с поддержкой получения и хранения токена, а также
    его обновлением по истечении его действия
    """
    TOKEN_CACHE_KEY = 'ILE_TOKEN'
    EVENTS_DATA_CACHE_KEY = 'EVENTS_DATA'
    LAST_FETCH_CACHE_KEY = 'LAST_TIME_FETCHED'
    MAX_RETRIES = 2

    def __init__(self):
        self.token = self.get_token()

    def get_token(self):
        return DEFAULT_CACHE.get(self.TOKEN_CACHE_KEY)

    def refresh_token(self):
        try:
            r = requests.get(
                '{}{}'.format(settings.ILE_BASE_URL, settings.ILE_TOKEN_PATH),
                auth=settings.ILE_TOKEN_USER,
                timeout=settings.CONNECTION_TIMEOUT,
                verify=settings.ILE_VERIFY_CERTIFICATE,
            )
            assert r.ok
            DEFAULT_CACHE.set(self.TOKEN_CACHE_KEY, r.json()['token'], timeout=int(r.json()['duration']))
            self.token = r.json()['token']
            return r.json()['token']
        except AssertionError:
            logging.error('ILE returned code %s, reason: %s' % (r.status_code, r.reason))
            raise ApiError
        except requests.RequestException:
            logging.exception('ILE connection failure')
            raise ApiError
        except Exception:
            logging.exception('ILE unexpected answer: %s' % r.json())
            raise ApiError

    def get_events_data(self, force=False, retry=0):
        if not force:
            val = DEFAULT_CACHE.get(self.EVENTS_DATA_CACHE_KEY)
            fetch_dt = DEFAULT_CACHE.get(self.LAST_FETCH_CACHE_KEY)
            do_refresh = fetch_dt is None or (timezone.now() - fetch_dt).seconds < settings.API_DATA_CACHE_TIME \
                         or val is None
            if not do_refresh:
                return val, False
        try:
            if not self.token:
                self.refresh_token()
            r = requests.get(
                '{}{}'.format(settings.ILE_BASE_URL, settings.ILE_SNAPSHOT_PATH),
                headers={'Authorization': 'Bearer %s' % self.token},
                timeout=settings.CONNECTION_TIMEOUT,
                verify=settings.ILE_VERIFY_CERTIFICATE,
            )
            if r.status_code == 401:
                if retry < self.MAX_RETRIES:
                    return self.get_events_data(force=force, retry=retry + 1)
                else:
                    raise ApiError
            elif r.status_code == 404:
                raise ApiNotFound
            assert r.ok
            DEFAULT_CACHE.set(self.EVENTS_DATA_CACHE_KEY, r.json(), timeout=settings.API_DATA_CACHE_TIME)
            return r.json(), True
        except AssertionError:
            logging.error('ILE returned code %s, reason: %s' % (r.status_code, r.reason))
            raise ApiError
        except requests.RequestException:
            logging.exception('ILE connection failure')
            raise ApiError

    def get_paginated_activities(self, page):
        return self.make_request(
            '{}/api/activity/list/'.format(settings.ILE_BASE_URL),
            params={
                '_I': ['activity.runs',
                       'run.assignments',
                       'assignment.user',
                       'run.events',
                       'event.time_slot',
                       'event.check_ins',
                       'check_in.user'],
                '_per_page': getattr(settings, 'ACTIVITIES_PER_PAGE', 20),
                '_page': page
            }
        )

    def make_request(self, url, method='get', retry=0, **kwargs):
        try:
            if not self.token:
                self.refresh_token()
            r = requests.request(
                method,
                url,
                headers={'Authorization': 'Bearer %s' % self.token},
                timeout=settings.CONNECTION_TIMEOUT,
                verify=settings.ILE_VERIFY_CERTIFICATE,
                **kwargs
            )
            if r.status_code == 401:
                if retry < self.MAX_RETRIES:
                    return self.make_request(url, method=method, retry=retry + 1)
                else:
                    raise ApiError
            assert r.ok
            return r.json()
        except AssertionError:
            logging.error('ILE returned code %s, reason: %s' % (r.status_code, r.content))
            raise ApiError
        except requests.RequestException:
            logging.exception('ILE connection failure')
            raise ApiError

    def get_check_ins_data(self, event_id):
        return self.make_request(
            '{}/api/check_in/list/?_I=check_in.user&event_id={}'.format(settings.ILE_BASE_URL, event_id)
        )

    def set_check_in(self, event_id, unti_id, confirmed):
        return self.make_request(
            '{}/api/user/check_in/confirm/?unti_id={}&event_id={}&confirmed={}'.format(
                settings.ILE_BASE_URL, unti_id, event_id, int(bool(confirmed))),
            method='post'
        )


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
