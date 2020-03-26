import csv
import io
import logging

import django_filters
from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_yasg.openapi import Parameter, Schema
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, exceptions
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.generics import ListAPIView, CreateAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from isle.api import LabsApi, DpApi, XLEApi, SSOApi
from isle.filters import LabsUserResultFilter, LabsTeamResultFilter, StatisticsFilter
from isle.kafka import check_kafka
from isle.models import Attendance, User, Event, EventEntry, EventMaterial, EventTeamMaterial, LabsTeamResult, \
    LabsUserResult, PLEUserResult, EventOnlyMaterial, DTraceStatistics
from isle.serializers import AttendanceSerializer, LabsUserResultSerializer, LabsTeamResultSerializer, \
    UserFileSerializer, UserResultSerializer, EventOnlyMaterialSerializer, DTraceStatisticsSerializer
from isle.tasks import handle_ple_user_result
from isle.utils import recalculate_user_chart_data, get_results_list, check_mysql_connection, get_release_version, \
    check_celery_active, calculate_user_context_statistics
from isle.views.common import ApiPermission, Paginator, IsAuthenticatedCustomized, CustomLimitOffsetPagination, \
    StatisticsPaginator


class AttendanceApi(ListAPIView):
    """
    get:
    **Описание**

        Получение списка присутствовавших на мероприятии.
        В запросе должен присутствовать хедер X-API-KEY

    **Пример get-запроса**

        GET /api/attendance/

    **Пример ответа**

        * {
            "count": 3, // общее количество объектов
            "next": null, // полный url следующей страницы (если есть)
            "previous": null, // полный url предыдущей страницы (если есть)
            "results": [
                {
                    "unti_id": 125, // id пользователя в UNTI SSO
                    "event_uuid": "11111111-1111-1111-11111111", // uuid мероприятия в LABS
                    "created_on": "2018-07-15T07:14:04+10:00", // дата создания объекта
                    "updated_on": "2018-07-15T07:14:04+10:00", // дата обновления объекта
                    "is_confirmed": true, // присутствие подтверждено
                    "confirmed_by_user": 1, // id пользователя подтвердившего присутствие в UNTI SSO
                    "confirmed_by_system": "uploads", // кем подтверждено uploads или chat_bot
                },
                ...
          }

    post:

    **Описание**

        Добавление/обновление объекта присутствия.
        В запросе должен присутствовать хедер X-API-KEY

    **Пример post-запроса**

    POST /api/attendance/{
            "is_confirmed": true,
            "user_id": 1,
            "event_uuid": "11111111-1111-1111-11111111",
            "confirmed_by_user": 1,
        }

    **Параметры post-запроса**

        * is_confirmed: подтверждено или нет, boolean
        * user_id: id пользователя в UNTI SSO, integer
        * event_id: id мероприятия в LABS, integer
        * confirmed_by_user: id пользователя в UNTI SSO, который подтвердил присутствие, integer или null,
          необязательный параметр

    **Пример ответа**

         * код 200, словарь с параметрами объекта как при get-запросе, если запрос прошел успешно
         * код 400, если не хватает параметров в запросе
         * код 403, если не указан хедер X-API-KEY или ключ неверен
         * код 404, если не найден пользователь или мероприятие из запроса

    """

    serializer_class = AttendanceSerializer
    pagination_class = Paginator
    permission_classes = (ApiPermission, )

    @swagger_auto_schema(manual_parameters=[
        Parameter('unti_id', 'query', type='number', required=False)
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Attendance.objects.order_by('id')
        unti_id = self.request.query_params.get('unti_id')
        if unti_id and unti_id.isdigit():
            qs = qs.filter(user__unti_id=unti_id)
        return qs

    @swagger_auto_schema(
        request_body=Schema(properties={
            'is_confirmed': Schema(type='boolean'),
            'user_id': Schema(type='number'),
            'event_uuid': Schema(type='string')
        }, type='object'))
    def post(self, request):
        is_confirmed = request.data.get('is_confirmed')
        user_id = request.data.get('user_id')
        event_id = request.data.get('event_uuid')
        confirmed_by = request.data.get('confirmed_by_user')
        if is_confirmed is None or not user_id or not event_id:
            return Response({'error': 'request should contain is_confirmed, user_id and event_uuid parameters'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(unti_id=user_id)
        except (User.DoesNotExist, TypeError):
            return Response({'error': 'user does not exist'}, status=status.HTTP_404_NOT_FOUND)
        try:
            event = Event.objects.get(uid=event_id)
        except (Event.DoesNotExist, TypeError):
            return Response({'error': 'event does not exist'}, status=status.HTTP_404_NOT_FOUND)
        if confirmed_by is not None:
            try:
                confirmed_by = User.objects.get(unti_id=confirmed_by)
            except (ValueError, TypeError, User.DoesNotExist):
                return Response({'error': 'user does not exist'}, status=status.HTTP_404_NOT_FOUND)
        a = Attendance.objects.update_or_create(
            user=user, event=event,
            defaults={
                'confirmed_by_user': confirmed_by,
                'confirmed_by_system': Attendance.SYSTEM_CHAT_BOT,
                'is_confirmed': is_confirmed,
            }
        )[0]
        EventEntry.all_objects.update_or_create(event=event, user=user,
                                                defaults={'deleted': False, 'added_by_assistant': False})
        logging.info('AttendanceApi request: %s' % request.data)
        return Response(self.serializer_class(instance=a).data)


class UserChartApiView(APIView):
    """
    **Описание**

        Запрос данных для отрисовки чарта пользовательских компетенций

    **Пример запроса**

        GET /api/user-chart/?user_id=123

    **Параметры запроса**

        * user_id - leader id пользователя

    **Пример ответа**

        * 200 успешно
        * 400 неполный запрос
        * 401 если не передан авторизационный токен
        * 404 пользователь не найден
    """

    authentication_classes = (TokenAuthentication, )
    permission_classes = (IsAuthenticatedCustomized, )

    @swagger_auto_schema(manual_parameters=[
        Parameter('user_id', 'query', type='number', required=True),
    ])
    def get(self, request):
        user_id = request.GET.get('user_id')
        if not user_id:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(leader_id=user_id).first()
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
        data = recalculate_user_chart_data(user)
        return Response(data)


class FileInfoMixin:
    def get_file_info(self, m):
        return {
            'activity_uuid': m.event.activity.uid,
            'title': m.result_v2.result.title,
            'event_uuid': m.event.uid,
            'file_url': m.get_url(),
            'file_name': m.get_file_name(),
            'summary_content': m.summary.content if m.summary_id else None,
            'comment': m.result_v2.comment,
            'levels': m.result_v2.get_meta(),
            'url': m.get_page_url(),
            'approved': m.result_v2.approved,
        }


class UserMaterialsListView(FileInfoMixin, APIView):
    """
    **Описание**

        Запрос файлов пользователя по его unti_id, выводятся только файлы, привязанные к результату

    **Пример запроса**

        GET /api/user-materials/?unti_id=123

    **Параметры запроса**

        * unti_id - unti id пользователя

    **Пример ответа**

        * 200 успешно
            [
                {
                    "activity_uuid": "12341234-1234-1234-1234123412341234",
                    "title": "title",
                    "event_uuid": "11111111-1111-1111-11111111",
                    "file_url": "http://example.com/file.pdf"
                    "file_name": "file.pdf",
                    "summary_content": null,
                    "comment": "",
                    "levels": [{"level": 1, "sublevel": 1, "competence": "11111111-1111-1111-11111111}],
                    "url": "https://uploads.2035.university/11111111-1111-1111-11111111/123/",
                    "approved": null,
                },
                {
                    "activity_uuid": "12341234-1234-1234-1234123412341234",
                    "title": "title",
                    "event_uuid": "11111111-1111-1111-11111111",
                    "file_url": "http://example.com/file.pdf"
                    "file_name": "file.pdf",
                    "comment": "",
                    "levels": [{"level": 1, "sublevel": 1, "competence": "11111111-1111-1111-11111111}],
                    "url": "https://uploads.2035.university/load-team/11111111-1111-1111-11111111/123/",
                    "team": {"id": 1, "name": "name", "members": [1, 2]},
                    "approved": true,
                },
                ...
            ]
        * 400 неполный запрос
        * 403 api key отсутствует или неправильный
        * 404 пользователь не найден
    """

    permission_classes = (ApiPermission, )

    @swagger_auto_schema(manual_parameters=[
        Parameter('unti_id', 'query', type='number', required=True),
    ])
    def get(self, request):
        unti_id = request.query_params.get('unti_id')
        if not unti_id or not unti_id.isdigit():
            return Response(status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(unti_id=unti_id).first()
        if not user:
            return Response(status=status.HTTP_404_NOT_FOUND)
        materials = EventMaterial.objects.filter(user_id=user.id, result_v2__isnull=False).\
            select_related('event', 'user', 'result_v2', 'result_v2__result').\
            prefetch_related('result_v2__circle_items')
        team_materials = EventTeamMaterial.objects.filter(team__users__id=user.id, result_v2__isnull=False).\
            select_related('event', 'team', 'result_v2', 'result_v2__result').\
            prefetch_related('team__users', 'result_v2__circle_items')
        resp = [self.get_file_info(m) for m in materials.iterator()]
        for m in team_materials:
            data = self.get_file_info(m)
            data.update({'team': {
                'id': m.team.id,
                'name': m.team.name,
                'members': [i.unti_id for i in m.team.users.all()]
            }})
            resp.append(data)
        return Response(resp)


class BaseResultInfoView(APIView):
    permission_classes = (ApiPermission,)
    result_model = LabsUserResult
    materials_model = EventMaterial

    @swagger_auto_schema(manual_parameters=[
        Parameter('id', 'query', type='number', required=True),
    ])
    def get(self, request):
        result_id = request.query_params.get('id')
        if not result_id or not result_id.isdigit():
            return Response(status=status.HTTP_400_BAD_REQUEST)
        result = self.result_model.objects.filter(id=result_id).\
            select_related('result', 'result__block__event').prefetch_related('circle_items').first()
        if not result:
            return Response(status=status.HTTP_404_NOT_FOUND)
        materials = self.materials_model.objects.filter(result_v2=result)
        resp = {
            'activity_uuid': result.result.block.event.activity.uid,
            'title': result.result.title,
            'event_uuid': result.result.block.event.uid,
            'comment': result.comment,
            'approved': result.approved,
            'levels': result.get_meta(),
            'url': result.get_page_url(),
            'files': [{
                'file_url': f.get_url(),
                'file_name': f.get_file_name(),
                'summary_content': f.summary.content if f.summary_id else None,
                'created_at': f.created_at and f.created_at.isoformat()
            } for f in materials]
        }
        self.update_response(resp, result)
        return Response(resp)

    def update_response(self, resp, result):
        pass


class UserResultInfoView(BaseResultInfoView):
    """
    **Описание**

        Запрос информации о пользовательском результате по его id

    **Пример запроса**

        GET /api/user-result-info/?id=123

    **Параметры запроса**

        * id - id результата

    **Пример ответа**

        * 200 успешно
            {
                "activity_uuid": "12341234-1234-1234-1234123412341234",
                "title": "title",
                "event_uuid": "11111111-1111-1111-11111111",
                "comment": "",
                "approved": false,
                "levels": [{"level": 1, "sublevel": 1, "competence": "11111111-1111-1111-11111111}],
                "user": {"unti_id": 1},
                "url": "https://uploads.2035.university/11111111-1111-1111-11111111/123/",
                "files": [
                    {
                        "file_url": "http://example.com/file.pdf",
                        "file_name": "file.pdf",
                        "summary_content": null,
                        "created_at": "2019-04-26T10:33:09.223871+00:00"
                    }
                ]
            }
        * 400 неполный запрос
        * 403 api key отсутствует или неправильный
        * 404 результат не найден
    """

    def update_response(self, resp, result):
        resp['user'] = {'unti_id': result.user.unti_id}


class TeamResultInfoView(BaseResultInfoView):
    """
    **Описание**

        Запрос информации о командном результате по его id

    **Пример запроса**

        GET /api/team-result-info/?id=123

    **Параметры запроса**

        * id - id результата

    **Пример ответа**

        * 200 успешно
            {
                "activity_uuid": "12341234-1234-1234-1234123412341234",
                "title": "title",
                "event_uuid": "11111111-1111-1111-11111111",
                "comment": "",
                "approved": false,
                "levels": [{"level": "1", "sublevel": "1", "competence": "11111111-1111-1111-11111111"}],
                "team": {"id": 1, "name": "name", "members": [1, 2]},
                "url": "https://uploads.2035.university/load-team/11111111-1111-1111-11111111/123/",
                "files": [
                    {
                        "file_url": "http://example.com/file.pdf",
                        "file_name": "file.pdf",
                        "summary_content": null,
                        "created_at": "2019-04-26T10:33:09.223871+00:00"
                    }
                ]
            }
        * 400 неполный запрос
        * 403 api key отсутствует или неправильный
        * 404 результат не найден
    """
    result_model = LabsTeamResult
    materials_model = EventTeamMaterial

    def update_response(self, resp, result):
        resp['team'] = {
            'id': result.team_id,
            'name': result.team.name,
            'members': [i.unti_id for i in result.team.get_members_for_event(result.result.block.event)]
        }


class AllUserResultsView(ListAPIView):
    """
    **Описание**

        Запрос информации о всех пользовательских результатах

    **Пример запроса**

        GET /api/all-user-results/?unti_id=123&created_at_after=2019-01-31T00:00:00&limit=10&offset=10

    **Параметры запроса**

        * unti_id - unti id пользователя, необязательный параметр
        * created_at_after - минимальная дата и время создания в iso формате, необязательный параметр
        * created_at_before - максимальная дата и время создания в iso формате, необязательный параметр
        * limit - максимальное количество результатов на странице, но не более 50
        * offset

    **Пример ответа**

        * 200 успешно
            {
                "count": 1,
                "next": null,
                "previous": null,
                "results": [
                    {
                        "activity_uuid": "12341234-1234-1234-1234123412341234",
                        "title": "title",
                        "event_uuid": "63284c8e-4f4a-4b54-9ef9-92f1cfb13d98",
                        "comment": "",
                        "approved": false,
                        "levels": null,
                        "url": "http://example.com/63284c8e-4f4a-4b54-9ef9-92f1cfb13d98/2/user/1",
                        "files": [
                            {
                                "file_url": "http://example.com/media/63284c8e-4f4a-4b54-9ef9-92f1cfb13d98/22/file.pdf",
                                "file_name": "file.pdf",
                                "summary_content": null,
                                "created_at": "2019-04-26T10:33:09.223871+00:00"
                            }
                        ],
                        "user": {
                            "unti_id": 2
                        }
                    }
                ]
            }
        * 400 некорректный запрос
        * 403 неправильный api key
    """
    pagination_class = CustomLimitOffsetPagination
    serializer_class = LabsUserResultSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = LabsUserResultFilter
    permission_classes = (ApiPermission,)

    def get_queryset(self):
        return LabsUserResult.objects.select_related('user')\
            .prefetch_related('eventmaterial_set', 'circle_items').distinct()


class AllTeamResultsView(ListAPIView):
    """
    **Описание**

        Запрос информации о всех командных результатах

    **Пример запроса**

        GET /api/all-team-results/?team_id=123&created_at_after=2019-01-31T00:00:00&limit=10&offset=10

    **Параметры запроса**

        * team_id - id команды, необязательный параметр
        * created_at_after - минимальная дата и время создания в iso формате, необязательный параметр
        * created_at_before - максимальная дата и время создания в iso формате, необязательный параметр
        * limit - максимальное количество результатов на странице, но не более 50
        * offset

    **Пример ответа**

        * 200 успешно
            {
                "count": 1,
                "next": null,
                "previous": null,
                "results": [
                    {
                        "activity_uuid": "12341234-1234-1234-1234123412341234",
                        "title": "title",
                        "event_uuid": "63284c8e-4f4a-4b54-9ef9-92f1cfb13d98",
                        "comment": "",
                        "approved": false,
                        "levels": null,
                        "url": "http://example.com/63284c8e-4f4a-4b54-9ef9-92f1cfb13d98/2/team/1",
                        "files": [
                            {
                                "file_url": "http://example.com/media/63284c8e-4f4a-4b54-9ef9-92f1cfb13d98/22/file.pdf",
                                "file_name": "file.pdf",
                                "summary_content": null,
                                "created_at": "2019-04-26T10:33:09.223871+00:00"
                            }
                        ],
                        "team": {
                            "id": 123,
                            "name": "name",
                            "members": [1, 2, 3]
                        }
                    }
                ]
            }
        * 400 некорректный запрос
        * 403 неправильный api key
    """
    pagination_class = CustomLimitOffsetPagination
    serializer_class = LabsTeamResultSerializer
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = LabsTeamResultFilter
    permission_classes = (ApiPermission,)

    def get_queryset(self):
        return LabsTeamResult.objects.select_related('team')\
            .prefetch_related('eventteammaterial_set', 'team__users', 'circle_items').distinct()


class GetDpData(APIView):
    """
    TODO: описание
    """
    authentication_classes = (SessionAuthentication, )
    permission_classes = (IsAdminUser, )

    def get(self, request):
        event_uid = request.GET.get('event')
        if not event_uid:
            event = None
        else:
            event = get_object_or_404(Event, uid=event_uid)
        s = io.StringIO()
        c = csv.writer(s, delimiter=';')
        for line in get_results_list(event):
            c.writerow(line)
        s.seek(0)
        b = io.BytesIO()
        b.write(s.read().encode('utf8'))
        b.seek(0)
        resp = FileResponse(b, content_type='text/csv')
        resp['Content-Disposition'] = "attachment; filename*=UTF-8''{}.csv".format('data')
        return resp


class ApiCheckHealth(APIView):
    """
    **Описание**

        Проверка статуса приложения, связи с системами, с которыми оно общается, и с базой данных

    **Пример запроса**

        GET /api/check/

    **Пример ответа**

        * 200 успешно
            {
                "labs": "ok",
                "dp": 500,
                "xle": "ok",
                "sso": "ok",
                "mysql": "ok",
                "kafka": false,
                "release": "1.1.0",
            }
        * 403 api key отсутствует или неправильный
    """
    permission_classes = (ApiPermission, )

    def get(self, request):
        return Response({
            'labs': LabsApi().health_check(),
            'dp': DpApi().health_check(),
            'xle': XLEApi().health_check(),
            'sso': SSOApi().health_check(),
            'mysql': check_mysql_connection(),
            'kafka': check_kafka(),
            'release': get_release_version(),
        })


class UploadUserFile(CreateAPIView):
    """
    **Описание**

        Загрузка пользовательского файла

    **Пример запроса**

        POST /api/upload-user-file/

    **Параметры post-запроса**

        * user: int - unti id пользователя
        * source: str - система инициатор загрузки
        * file: загружаемый файл
        * activity_uuid: str - uuid активности (необязательный параметр)
        * data: str - json с дополнительными данными (необязательный параметр)

    **Пример ответа**

        * 200 успешно
            {
                "id":8,
                "user":1,
                "data":"{\"qwerty\": 123}",
                "source":"PLE",
                "activity_uuid":"",
                "file":"http://127.0.0.1:8092/media/course-image.jpg"
            }
        * 400 некорректный запрос
        * 403 api key отсутствует или неправильный
    """

    permission_classes = (ApiPermission, )
    serializer_class = UserFileSerializer
    parser_classes = (MultiPartParser, )


class CreateUserResultAPI(CreateAPIView):
    """
    **Описание**

        Загрузка пользовательского результата

    **Пример запроса**

        POST /api/upload/create-user-result/{
            "user": 1,
            "comment": "",
            "meta": "{\"key\": \"value\"}",
            "materials": [{"url": "http://example.com/file.pdf"}, {"file": "http://example.com/file.pdf"}],
            "callback_url": "https://ple.2035.university/callback"
        }

    **Параметры запроса**

        * user - unti id пользователя
        * comment - комментарий к результату (необязательно)
        * additional_data - json c разметкой
        * materials - массив ссылок на файлы или ссылки результата, ключ url должен присутствовать для ссылок,
                      а file - для файлов, которые uploads будет закачивать
        * callback_url - url, к которому обратится uploads после обработки запроса

    **Пример ответа**

        * 200 успешно
        * 400 некорректный запрос
        * 403 неверный api key
        * 417 если невозможно обработать запрос
    """

    permission_classes = (ApiPermission,)
    serializer_class = UserResultSerializer

    def create(self, request, *args, **kwargs):
        if not check_celery_active():
            return Response(status=status.HTTP_417_EXPECTATION_FAILED)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        handle_ple_user_result.delay(request.data)
        return Response(status=status.HTTP_200_OK)


class GetPLEUserResultApi(APIView):
    """
    **Описание**

        Запрос информации о пользовательском результате в PLE

    **Пример запроса**

        GET /api/get-ple-user-result/{result_id}/

    **Параметры запроса**

        * result_id - id результата, обязательный параметр

    **Пример ответа**

        * 200 успешно
            {
                "id": 1,
                "user": 1,
                "meta": {"key": "value"},
                "comment": "",
                "materials": [
                    {
                        "id": 1,
                        "uploads_url": "http://example.com/file.pdf"
                    }
                ]
            }
        * 403 неверный api key
        * 404 результат с указанным id не существует
    """

    permission_classes = (ApiPermission,)

    @swagger_auto_schema(manual_parameters=[
        Parameter('result_id', 'query', type='number', required=True),
    ])
    def get(self, request, *args, **kwargs):
        try:
            user_result = PLEUserResult.objects.get(id=kwargs['result_id'])
        except PLEUserResult.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(user_result.get_json())


class CheckUserTraceApi(APIView):
    """
    **Описание**

        Проверка загрузки пользователем цифрового следа для мероприятия

    **Пример запроса**

        GET /api/check-user-trace/?leader_id=1&event_id=cd602dd7-4fef-440b-82bf-013b5817e3dd

    **Параметры запроса**

        * event_id - uuid мероприятия, обязательный параметр
        * leader_id - leader id пользователя, необязательный параметр

    **Пример ответа**

        * 200 успешно
            если в запросе указан leader_id:
            {
                "exists": true,
                "n_personal": 2,
                "n_team": 3
            }
            где n_personal - количество ЦС, который пользователь загрузил для себя,
            n_team - количество ЦС из команд event-а, в которых есть пользователь,
            exists true, если хотя бы одно из значенй n_personal или n_team больше 0

            если в запросе не указан leader_id:
            {
                "exists": true,
                "n_personal": 2,
                "n_team": 3,
                "n_event": 1,
                "personal_users": 1,
                "team_users": 1,
                "unique_users": 1,
            }
            где n_personal - количество персонального ЦС для мероприятия,
            n_team - количество командного ЦС,
            n_event - количество файлов мероприятия,
            exists true, если хотя бы одно из значенй n_personal или n_team, или n_event больше 0,
            personal_users - количество пользователей с загруженным персональным ЦС,
            team_users - количество пользователей, грузивших командный ЦС,
            unique_users - количество уникальных пользователей из предыдущих двух пунктов

        * 400
            {
                "leader_id": "user with leader_id 1 not found",
                "event_id": "event with uuid cd602dd7-4fef-440b-82bf-013b5817e3dd not found"
            }
            если не указан какой-то параметр или не найден пользователь/мероприятие с описанием ошибок по параметрам

        * 401 если не передан авторизационный токен
    """
    authentication_classes = (TokenAuthentication, )
    permission_classes = (IsAuthenticatedCustomized, )

    @swagger_auto_schema(manual_parameters=[
        Parameter('leader_id', 'query', type='number', required=False),
        Parameter('event_id', 'query', type='string', required=True),
    ])
    def get(self, request):
        event_id = request.query_params.get('event_id')
        leader_id = request.query_params.get('leader_id')
        errors = {}
        if not event_id:
            errors['event_id'] = 'required parameter'
        else:
            try:
                event = Event.objects.get(uid=event_id)
            except Event.DoesNotExist:
                errors['event_id'] = 'event with uuid {} not found'.format(event_id)
        if not leader_id:
            user = None
        else:
            try:
                user = User.objects.get(leader_id=leader_id)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                errors['leader_id'] = 'user with leader_id {} not found'.format(leader_id)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        if user:
            n_personal = EventMaterial.objects.filter(event=event, user=user).count()
            n_team = EventTeamMaterial.objects.filter(event=event, team__users=user).distinct().count()
            return Response({
                'exists': n_personal + n_team > 0,
                'n_personal': n_personal,
                'n_team': n_team,
            })
        else:
            n_personal = EventMaterial.objects.filter(event=event).count()
            n_team = EventTeamMaterial.objects.filter(event=event).count()
            n_event = EventOnlyMaterial.objects.filter(event=event).count()
            personal_users = set(EventMaterial.objects.filter(event=event).values_list('user__unti_id', flat=True)
                                 .distinct())
            team_users = set(EventTeamMaterial.objects.filter(event=event).values_list('initiator', flat=True)
                             .distinct())
            return Response({
                'exists': n_personal + n_team + n_event > 0,
                'n_personal': n_personal,
                'n_team': n_team,
                'n_event': n_event,
                'personal_users': len(personal_users),
                'team_users': len(team_users),
                'unique_users': len(personal_users.union(team_users)),
            })


class EventMaterialsApi(ListAPIView):
    """
    **Описание**

        Получение списка материалов мероприятия

    **Пример запроса**

        GET /api/event-materials/?event_id=cd602dd7-4fef-440b-82bf-013b5817e3dd

    **Параметры запроса**

        * event_id - uuid мероприятия, обязательный параметр

    **Пример ответа**

        * 200 успешно
            {
                "count": 1, // количество объектов
                "next": null, // полный url следующей страницы (если есть)
                "previous": null, // полный url предыдущей страницы (если есть)
                "results": [
                    {
                        "id": 1,
                        "url": "", // урл файла, если он был загружен ссылкой
                        "file": "http://127.0.0.1:8092/media/file.csv", // урл файла в uploads, если он был загружен как файл
                        "file_type": "text/csv", // тип файла
                        "file_size": 8835, // размер в байтах
                        "created_at": "2019-07-08T20:01:50.104666+10:00",
                        "initiator": 11111134, // unti_id того, кто загрузил файл (может быть null)
                        "deleted": false, // если deleted: true, значит файл был перенесен в личные или командные
                        "comment": "qwe",
                        "event": "c26530a5-09a0-485d-89cc-3ccb790ba876",
                        "trace": { // информация о блоке, который загружен файл
                            "trace_type": "Презентация",
                            "name": "Презентация спикера",
                            "event_type": "36364eea-de91-4a9d-b498-87e5beb9b3c1", // uuid типа события из labs
                            "deleted": false
                        }
                    }
                ]
            }

        * 400 если не указан event_id или такого мероприятия нет
        * 403 если не указан хедер X-API-KEY или ключ неверен
    """

    permission_classes = (ApiPermission, )
    serializer_class = EventOnlyMaterialSerializer
    pagination_class = Paginator

    @swagger_auto_schema(manual_parameters=[
        Parameter('event_id', 'query', type='string', required=True),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if not self.request.query_params.get('event_id'):
            raise exceptions.ValidationError({'event_id': 'required parameter'})
        event = Event.objects.filter(uid=self.request.query_params.get('event_id')).first()
        if not event:
            raise exceptions.ValidationError({'event_id': 'event with uuid {} not found'.
                                             format(self.request.query_params.get('event_id'))})
        return EventOnlyMaterial.all_objects.filter(event=event).select_related('event', 'trace', 'trace__event_type')


class ContextUserStatistics(ListAPIView):
    """
    **Описание**

        Получение статистики по пользователям, у которых есть цс в контексте

    **Пример запроса**

        GET /api/context-user-statistics/{context_uuid}/?unti_id=1&force_update=1

    **Параметры запроса**

        * unti_id - unti_id пользователя, необязательный параметр
        * leader_id - leader_id пользователя, необязательный параметр
        * force_update - если присутствует в запросе, будет произведен пересчет статистики по пользователю. Работает
                         только в случае запроса статистики по конкретному пользователю

    **Пример ответа**

        * 200 успешно
            {
                "count": 1, // количество объектов
                "next": null, // полный url следующей страницы (если есть)
                "previous": null, // полный url предыдущей страницы (если есть)
                "results": [
                    {
                        "context": "2fa173c5-6a0b-4d76-b670-be49004ac7c6",
                        "unti_id": 1,
                        "leader_id": "123",
                        "n_entry": 2,  // количество материалов мероприятия, загруженных пользователем
                        "n_run_entry": 0,  // количество записей на прогоны котекста
                        "n_personal": 0,  // колчество персональных файлов
                        "n_team": 2018,  // количество командных файлов
                        "n_event": 4,  // количество записей на мероприятия контекста
                        "updated_at": "2019-07-17T02:35:32.685916+10:00"
                    }
                ]
            }

        * 400 если unti_id не является числом
        * 403 если не указан хедер X-API-KEY или ключ неверен
    """

    permission_classes = (ApiPermission, )
    serializer_class = DTraceStatisticsSerializer
    pagination_class = StatisticsPaginator
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = StatisticsFilter

    def get_queryset(self):
        if self.kwargs.get('context_uuid'):
            return DTraceStatistics.objects.filter(context__uuid=self.kwargs['context_uuid'])\
                .select_related('user', 'context')
        return DTraceStatistics.objects.none()

    def list(self, request, *args, **kwargs):
        if any(i in request.query_params for i in ('leader_id', 'unti_id')):
            item = self.filter_queryset(self.get_queryset()).first()
            if item and (item.updated_at < timezone.now() - timezone.timedelta(seconds=settings.STATISTICS_VALID_FOR)
                         or 'force_update' in request.query_params):
                calculate_user_context_statistics(item.user, item.context)
        return super().list(request, *args, **kwargs)
