import functools
import json
import logging
import os
from collections import defaultdict

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q, Count
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import TemplateView

from isle.forms import ResultStructureFormset, EventMaterialForm, EventDTraceAdminFilter, EventDTraceFilter
from isle.kafka import send_object_info, KafkaActions

from isle.models import Trace, Summary, User, LabsUserResult, UserResult, EventEntry, RunEnrollment, DpCompetence, \
    MetaModel, DpTool, CircleItem, LabsEventResult, EventMaterial, EventTeamMaterial, Team, LabsTeamResult, \
    TeamResult, EventOnlyMaterial, ApiUserChart
from isle.views.common import context_setter, GetEventMixinWithAccessCheck, GetEventMixin


class ResultUpdateType:
    SET_VALIDATION = 'set_validation'
    EDIT_COMMENT = 'edit_comment'
    ADD_FILE = 'add_file'
    EDIT_TOOLS = 'edit_tools'
    BLOCK_CHANGED = 'block_changed'
    DELETE_FILE = 'delete_file'


@method_decorator(context_setter, name='get')
class BaseLoadMaterials(TemplateView):
    template_name = 'load_materials.html'
    material_model = None

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({
            'traces': self.get_traces_data(),
            'allow_file_upload': getattr(settings, 'ALLOW_FILE_UPLOAD', True),
            'max_size': settings.MAXIMUM_ALLOWED_FILE_SIZE,
            'max_uploads': settings.MAX_PARALLEL_UPLOADS,
            'event': self.event,
            'can_upload': self.can_upload(),
            'can_set_public': self._can_set_public(),
            'SUMMARY_SAVE_INTERVAL': settings.SUMMARY_SAVE_INTERVAL,
            'unattached_files': self.get_unattached_files()
        })
        return data

    def get_unattached_files(self):
        return []

    def can_upload(self):
        return self.current_user_is_assistant

    def _can_set_public(self):
        return False

    def get_traces_data(self):
        traces = self.event.get_traces()
        result = []
        links = defaultdict(list)
        for item in self.get_materials():
            links[item.trace_id].append(item)
        for trace in traces:
            result.append({'trace': trace, 'links': links.get(trace.id, [])})
        return result

    def post(self, request, *args, **kwargs):
        resp = self.check_post_allowed(request)
        if resp is not None:
            return resp
        try:
            trace_id = int(request.POST.get('trace_name'))
        except (ValueError, TypeError):
            return JsonResponse({}, status=400)
        if not trace_id or not trace_id in [i.id for i in self.event.get_traces()]:
            return JsonResponse({}, status=400)
        if 'add_btn' in request.POST:
            return self.add_item(request)
        return self.delete_item(request)

    def check_post_allowed(self, request):
        if not self.event.is_active:
            return JsonResponse({'error': 'Мероприятие недоступно для оцифровки'}, status=403)
        if not self.can_upload():
            return JsonResponse({}, status=403)

    def delete_item(self, request):
        material_id = request.POST.get('material_id')
        if not material_id or not material_id.isdigit():
            return JsonResponse({}, status=400)
        result_value = self._get_result_value(request)
        if not result_value:
            return JsonResponse({}, status=400)
        return self._delete_item(result_value, material_id)

    def get_result_key_and_value(self, request):
        return self._get_result_key(), self._get_result_value(request)

    def _get_result_key(self):
        return 'trace'

    def _get_result_value(self, request):
        return Trace.objects.filter(id=request.POST['trace_name']).first()

    def add_item(self, request, block_upload=False):
        result_key, result_value = self.get_result_key_and_value(request)
        if not result_value:
            return JsonResponse({}, status=400)
        data = self.get_material_fields(request)
        data[result_key] = result_value
        url = request.POST.get('url_field')
        file_ = request.FILES.get('file_field')
        summary_content = request.POST.get('summary')
        # в запросе должен быть или файл, или урл, или содержание конспекта
        if sum(map(lambda x: int(bool(x)), [url, file_, summary_content])) != 1:
            return JsonResponse({}, status=400)
        if url:
            try:
                r = requests.head(url, timeout=settings.HEAD_REQUEST_CONNECTION_TIMEOUT)
                assert r.ok
                file_type = r.headers.get('content-type', '')
                file_size = r.headers.get('Content-Length')
            except:
                file_type, file_size = '', None
            data.update({'url': url, 'file_type': file_type, 'file_size': file_size})
        elif file_:
            data.update({'file_type': file_.content_type, 'file_size': file_.size})
        else:
            summary = Summary.publish_summary(
                request.user,
                self.event,
                result_value if isinstance(result_value, Trace) else result_value.result,
                summary_content
            )
            data.update({'summary_id': summary.id})
        data['initiator'] = request.user.unti_id
        material = self.material_model.objects.create(**data)
        if file_:
            material.file.save(self.make_file_path(file_.name), file_)
        resp = {
            'material_id': material.id,
            'url': material.get_url(),
            'name': material.get_name(),
            'comment': getattr(material, 'comment', ''),
            'is_public': getattr(material, 'is_public', True),
            'data_attrs': material.render_metadata(),
            'summary': material.get_short_summary(),
            'can_set_public': self._can_set_public()
        }
        self.update_add_item_response(resp, material, result_value)
        if self.extra_context and self.extra_context.get('team_upload'):
            resp['uploader_name'] = request.user.fio
        return JsonResponse(resp)

    def update_add_item_response(self, resp, material, trace):
        pass

    def get_material_fields(self, request):
        return {}

    def make_file_path(self, fn):
        return fn

    def set_initiator_users_to_qs(self, qs):
        users = {i.unti_id: i for i in User.objects.filter(unti_id__in=filter(None, [j.initiator for j in qs]))}
        for item in qs:
            item.initiator_user = users.get(item.initiator)


class BaseLoadMaterialsWithAccessCheck(GetEventMixinWithAccessCheck, BaseLoadMaterials):
    pass


class BaseLoadMaterialsLabsResults:
    """
    Базовый класс для вьюх загрузки результатов в привязке к лабсовским результатам
    """
    results_model = LabsUserResult
    lookup_attr = 'user'
    legacy_results_model = UserResult

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        blocks = self.event.blocks.prefetch_related('results', 'results__circle_items')
        structure = [
            {
                'title': block.title,
                'deleted': block.deleted,
                'results': [
                    {
                        'id': result.id,
                        'deleted': result.deleted,
                        'title': 'Результат {}.{}'.format(i, j)
                    } for j, result in enumerate(block.results.all(), 1) if self.is_according_result_type(result)
                ]
            } for i, block in enumerate(blocks, 1) if self.block_has_available_results(block)
        ]
        qs_results = self.results_model.objects.filter(**self._update_query_dict({
            'result__block__event_id': self.event.id
        })).order_by('-id')
        qs_materials = self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'result_v2__isnull': False
        })).order_by('-id')
        materials = defaultdict(list)
        for m in qs_materials:
            materials[m.result_v2_id].append(m)
        item_results = defaultdict(list)
        for item in qs_results:
            item.links = materials.get(item.id, [])
            if item.links:
                item_results[item.result_id].append(item)
        for block in blocks:
            for result in block.results.all():
                result.results = item_results.get(result.id, [])
        traces = data['traces']
        links = functools.reduce(lambda x, y: x + y, [i.get('links', []) for i in traces], [])
        data.update(self._update_query_dict({
            'blocks': blocks,
            'old_results': self.get_old_results(),
            'links': links,
            'blocks_structure_json': json.dumps(structure, ensure_ascii=False),
            'event_members': list(EventEntry.objects.filter(event=self.event).values_list('user_id', flat=True)) +
                             list(RunEnrollment.objects.filter(run_id=self.event.run_id)
                                  .values_list('user_id', flat=True)),
        }))
        return data

    def get_unattached_files(self):
        return self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'result_v2__isnull': True,
            'result__isnull': True,
            'trace__isnull': True,
        }))

    def _update_query_dict(self, d):
        """
        т.к. у базовых классов есть cached_property user или team, которое одновременно является
        параметром фильтрации для персональных файлов/результатов и командных файлов/результатов соответственно,
        то этот метод добавляет нужный параметр в словарь для фильтрации/создания объектов
        """
        d.update({self.lookup_attr: getattr(self, self.lookup_attr)})
        return d

    def get_old_results(self):
        """
        получение старых результатов legacy_results_model если такие есть
        """
        results = self.legacy_results_model.objects.filter(**self._update_query_dict({
            'event': self.event,
        })).order_by('id')
        if not results:
            return []
        data = defaultdict(list)
        for item in self.material_model.objects.filter(**self._update_query_dict({'result__isnull': False})):
            data[item.result_id].append(item)
        res = []
        for result in results:
            res.append({'result': result, 'links': data.get(result.id, [])})
        return res

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'edit_comment':
            # действие доступно для всех, кто может заходить на страницу
            return self.action_edit_comment(request)
        resp = self.check_post_allowed(request)
        if resp is not None:
            return resp
        result_id_error, result_deleted, type_ok = self._check_labs_result_id(request)
        allowed_actions = ['delete_all', 'init_result', 'move', 'move_unattached', 'approve_result',
                           'change_circle_items', 'init_structure_edit', 'edit_structure']
        if 'add_btn' in request.POST:
            if result_id_error is not None or result_deleted or not type_ok:
                return result_id_error
            return self.add_item(request)
        elif 'action' in request.POST and request.POST['action'] in allowed_actions:
            if request.POST['action'] != 'move_unattached' and result_id_error is not None:
                return result_id_error
            if request.POST['action'] == 'delete_all':
                return self.action_delete_all(request)
            elif request.POST['action'] == 'init_result':
                if result_deleted or not type_ok:
                    return JsonResponse({}, status=400)
                return self.action_init_result(request)
            elif request.POST['action'] == 'move':
                return self.action_move(request)
            elif request.POST['action'] == 'move_unattached':
                return self.action_move_unattached(request)
            elif request.POST['action'] == 'approve_result':
                return self.action_approve_result(request)
            elif request.POST['action'] == 'change_circle_items':
                return self.action_change_circle_items(request)
            elif request.POST['action'] == 'init_structure_edit':
                return self.action_init_structure_edit(request)
            elif request.POST['action'] == 'edit_structure':
                return self.action_edit_structure(request)
        return self.delete_item(request)

    def action_init_structure_edit(self, request):
        """
        рендерит формсет текущей структуры результата
        """
        if not self.current_user_is_assistant:
            raise PermissionDenied
        result = self.get_result_for_request(request)
        if not result:
            return JsonResponse({}, status=400)
        initial_data = self.get_result_structure_initial_data(result)
        context = {
            'formset': ResultStructureFormset(initial=initial_data),
            'additional_fields': {
                'labs_result_id': result.result_id,
                'action': 'edit_structure',
                'result_item_id': result.id,
            }
        }
        t = get_template('edit_result_structure_modal.html').render(context=context, request=request)
        return JsonResponse({'html': t})

    def get_result_structure_initial_data(self, result):
        """
        initial data для формсета структуры результата
        """
        initial_data = []
        meta = result.get_meta()
        competence_uuids = filter(None, (i['competence'] for i in meta))
        model_uuids = filter(None, (i['model'] for i in meta))
        competences = {i.uuid: i for i in DpCompetence.objects.filter(uuid__in=competence_uuids)}
        models = {i.uuid: i for i in MetaModel.objects.filter(uuid__in=model_uuids)}
        for item in meta:
            tmp = {
                'level': str(item['level']) if item['level'] else None,
                'sublevel': str(item['sublevel']) if item['sublevel'] else None,
            }
            tmp['metamodel'] = models.get(item['model'])
            tmp['competence'] = competences.get(item['competence'])
            if item.get('tools'):
                # на данном этапе у инструментов нет uuid, но можно считать, что в пределах одной модели
                # названия инструментов уникальны
                tmp['tools'] = DpTool.objects.filter(models=tmp['metamodel'], title__in=item['tools'])
            initial_data.append(tmp)
        return initial_data

    def action_edit_structure(self, request):
        """
        обновление структуры результата
        """
        if not self.current_user_is_assistant:
            raise PermissionDenied
        result = self.get_result_for_request(request)
        if not result:
            return JsonResponse({}, status=400)
        initial_data = self.get_result_structure_initial_data(result)
        formset = ResultStructureFormset(initial=initial_data, data=request.POST)
        if formset.is_valid():
            circle_items = []
            for form_data in formset.cleaned_data:
                if not form_data or form_data.get('DELETE'):
                    continue
                defaults = dict(
                    level=form_data['level'],
                    sublevel=form_data['sublevel'],
                    competence=form_data['competence'],
                    model=form_data['metamodel'],
                    result=result.result,
                    competence_uuid=form_data['competence'].uuid,
                    model_uuid=form_data['metamodel'].uuid,
                    created_in=CircleItem.SYSTEM_UPLOADS,
                    source=CircleItem.SYSTEM_UPLOADS,
                    tool=None,
                )
                if form_data.get('tools'):
                    for tool in form_data['tools']:
                        defaults['tool'] = tool.title
                        ci = CircleItem(**defaults)
                        ci = CircleItem.objects.get_or_create(code=ci.get_code(), defaults=defaults)[0]
                        circle_items.append(ci)
                else:
                    ci = CircleItem(**defaults)
                    ci = CircleItem.objects.get_or_create(code=ci.get_code(), defaults=defaults)[0]
                    circle_items.append(ci)
            result.circle_items.set(circle_items)
            logging.info('User %s has set new structure for %s %s: %s', self.request.user.unti_id,
                         result._meta.model_name, result.id, result.get_meta())
            send_object_info(result, result.id, KafkaActions.UPDATE,
                             additional_data={'what': ResultUpdateType.EDIT_TOOLS})
            return JsonResponse({
                'status': 0,
                'items': {i.id: i.tool for i in circle_items if i.tool},
                'type': 'user' if isinstance(result, LabsUserResult) else 'team',
                'labs_result_id': result.result_id,
                'result_id': result.id,
                'object_id': result.user.unti_id if isinstance(result, LabsUserResult) else result.team_id,
            })
        return JsonResponse({'status': 1, 'errors': formset.errors})

    def action_approve_result(self, request):
        if not self.current_user_is_assistant:
            raise PermissionDenied
        result_id = request.POST.get('labs_result_id') or ''
        result_item_id = request.POST.get('result_item_id') or ''
        approve_text = request.POST.get('approve_text') or ''
        approved = {'true': True, 'false': False}.get(request.POST.get('approved'))
        if result_id.isdigit() and result_item_id.isdigit() and isinstance(approved, bool):
            result = self.get_result_for_request(request)
            if not result or result.result.block.event_id != self.event.id:
                return JsonResponse({}, status=404)
            result.approve_text = approve_text
            result.approved = approved
            result.save(update_fields=['approve_text', 'approved'])
            if self.should_send_to_kafka(result):
                send_object_info(result, result.id, KafkaActions.UPDATE,
                                 additional_data={'what': ResultUpdateType.SET_VALIDATION})
            logging.info('User %s set approved to %s, comment: %s for result #%s' %
                         (request.user.username, result.approved, result.approve_text, result_id))
            return JsonResponse({'approved': result.approved, 'approve_text': result.approve_text, 'id': result.id})
        return JsonResponse({}, status=400)

    def action_change_circle_items(self, request):
        result_id = request.POST.get('labs_result_id') or ''
        result_item_id = request.POST.get('result_item_id') or ''
        selected_circle_items = request.POST.get('circle_items') or ''
        try:
            selected_circle_items = [int(i) for i in selected_circle_items.split(',')] if selected_circle_items else []
        except (ValueError, TypeError, AttributeError):
            return JsonResponse({}, status=400)
        if result_id.isdigit() and result_item_id.isdigit():
            result = self.get_result_for_request(request)
            if not result or result.result.block.event_id != self.event.id:
                return JsonResponse({}, status=404)
            q = Q(tool__isnull=True)
            if not self.current_user_is_assistant:
                q |= Q(created_in=CircleItem.SYSTEM_UPLOADS)
            q &= Q(id__in=list(result.circle_items.values_list('id', flat=True)))
            # обычный пользователь не может редактировать инструменты своего результата, если они не описаны
            # в структуре мероприятия в лабс
            unchangeable_items = result.result.circle_items.filter(q)
            all_items = set([i.id for i in result.result.circle_items.all()])
            selected_items = set([i for i in all_items if i in selected_circle_items])
            selected_items |= set(unchangeable_items.values_list('id', flat=True))
            result.circle_items.set(selected_items)
            if self.should_send_to_kafka(result):
                send_object_info(result, result.id, KafkaActions.UPDATE,
                                 additional_data={'what': ResultUpdateType.EDIT_TOOLS})
            logging.info('User %s updated circle items for result #%s, circle items ids: %s' %
                         (request.user.username, result_id, [i.id for i in result.circle_items.all()]))
            return JsonResponse({'selected_items': [i.id for i in result.circle_items.all()]})
        return JsonResponse({}, status=400)

    def action_edit_comment(self, request):
        result_id = request.POST.get('labs_result_id') or ''
        result_item_id = request.POST.get('result_item_id') or ''
        comment = request.POST.get('comment')
        if result_id.isdigit() and result_item_id.isdigit() and comment is not None:
            result = self.get_result_for_request(request)
            if not result:
                return JsonResponse({}, status=404)
            result.comment = comment
            result.save(update_fields=['comment'])
            if self.should_send_to_kafka(result):
                send_object_info(result, result.id, KafkaActions.UPDATE,
                                 additional_data={'what': ResultUpdateType.EDIT_COMMENT})
            logging.info('User %s has updated comment for result #%s: %s' %
                (request.user.username, result_id, comment))
            return JsonResponse({})
        return JsonResponse({}, status=400)

    def action_move(self, request):
        """
        перемещение объекта результата из одного блока результата в другой
        """
        if not self.current_user_is_assistant:
            raise PermissionDenied
        item_result = self.results_model.objects.filter(**self._update_query_dict({
            'result_id': request.POST.get('labs_result_id'),
            'id': request.POST.get('result_item_id'),
        })).first()
        if not item_result:
            return JsonResponse({}, status=400)
        old_result_id = item_result.result.id
        try:
            assert item_result.result.block.event_id == self.event.id
            move_to = LabsEventResult.objects.select_related('block').get(id=request.POST.get('move_to'))
            assert move_to.block.event_id == self.event.id and not move_to.deleted and not move_to.block.deleted
            assert self.is_according_result_type(move_to)
        except (AssertionError, LabsEventResult.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=400)
        item_result.result = move_to
        item_result.save(update_fields=['result'])
        logging.info('User %s moved result %s from LabsEventResult %s to %s' %
                     (self.request.user.email, item_result.id, old_result_id, move_to.id))
        if self.should_send_to_kafka(item_result):
            send_object_info(item_result, item_result.id, KafkaActions.UPDATE,
                             additional_data={'what': ResultUpdateType.BLOCK_CHANGED})
        return JsonResponse({'new_result_id': move_to.id})

    def action_move_unattached(self, request):
        """
        перемещение файла, у которого нет связей с трейсом или результатом, в результат
        """
        if not self.current_user_is_assistant:
            raise PermissionDenied
        try:
            material = self.material_model.objects.get(**self._update_query_dict({
                'event': self.event,
                'id': request.POST.get('material_id'),
                'trace__isnull': True,
                'result__isnull': True,
                'result_v2__isnull': True,
            }))
        except (self.material_model.DoesNotExist, ValueError, TypeError):
            return JsonResponse({}, status=400)
        try:
            result = LabsEventResult.objects.get(
                block__event_id=self.event.id,
                id=request.POST.get('move_to')
            )
            assert not result.deleted and not result.block.deleted
            assert self.is_according_result_type(result)
        except (AssertionError, self.material_model.DoesNotExist, ValueError, TypeError):
            return JsonResponse({}, status=400)
        item_result = self.results_model.objects.create(**self._update_query_dict({
            'result': result,
        }))
        if self.should_send_to_kafka(item_result):
            send_object_info(item_result, item_result.id, KafkaActions.CREATE)
        material.result_v2 = item_result
        material.save(update_fields=['result_v2'])
        if self.should_send_to_kafka(item_result):
            send_object_info(item_result, item_result.id, KafkaActions.UPDATE,
                             additional_data={'what': ResultUpdateType.ADD_FILE})
        logging.info('User %s created result %s from unattached file %s' %
                     (request.user.email, item_result.id, material.id))
        return JsonResponse({
            'material_id': material.id,
            'url': material.get_url(),
            'name': material.get_name(),
            'comment': '',
            'is_public': getattr(material, 'is_public', True),
            'data_attrs': material.render_metadata(),
            'can_set_public': self._can_set_public(),
            'item_result_id': item_result.id,
            'result_id': result.id,
            'result_url': item_result.get_page_url(),
        })

    def action_init_result(self, request):
        """
        создание результата, в который будут загружаться файлы
        """
        item = self.results_model.objects.create(**self._update_query_dict({
            'result_id': request.POST.get('labs_result_id'),
            'comment': request.POST.get('comment') or '',
        }))
        circle_items = request.POST.get('circle_items') or ''
        circle_items = circle_items.split(',')
        circle_items_ids = []
        for cid in circle_items:
            try:
                circle_items_ids.append(int(cid))
            except (ValueError, TypeError):
                pass
        # если в структуре лабс указан какой-то элемент без инструментов, он автоматически добавляется
        # к результату
        auto_add_items = set(CircleItem.objects.filter(
            result_id=item.result_id,
            source=CircleItem.SYSTEM_LABS,
            tool__isnull=True,
        ).values_list('id', flat=True))
        circle_items_ids = set(circle_items_ids) | auto_add_items
        item.circle_items.set(CircleItem.objects.filter(
            id__in=circle_items_ids,
            result_id=item.result_id,
            source=CircleItem.SYSTEM_LABS,
        ))
        if self.should_send_to_kafka(item):
            send_object_info(item, item.id, KafkaActions.CREATE)
        return JsonResponse({'result_id': item.id})

    def action_delete_all(self, request):
        if not request.POST.get('result_item_id'):
            return JsonResponse({}, status=400)
        result = self.results_model.objects.filter(**self._update_query_dict({
            'result_id': request.POST.get('labs_result_id'),
            'id': request.POST.get('result_item_id'),
        })).first()
        if not result:
            return JsonResponse({}, status=400)
        materials = self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'result_v2': result
        }))
        try:
            result_id = result.id
            should_send = self.should_send_to_kafka(result)
            with transaction.atomic():
                materials.delete()
                result.delete()
            if should_send:
                send_object_info(result, result_id, KafkaActions.DELETE)
        except Exception:
            logging.exception('Failed to delete result %s for user %s' % (result.id, result.user.username))
            return JsonResponse({}, status=500)
        logging.warning('User %s deleted all result files for %s %s result #%s' %
                        (request.user.username, self.lookup_attr, getattr(self, self.lookup_attr).id,
                         request.POST.get('labs_result_id')))
        return JsonResponse({})

    def delete_item(self, request):
        material_id = request.POST.get('material_id')
        if not material_id or not material_id.isdigit():
            return JsonResponse({}, status=400)
        if 'labs_result_id' in request.POST:
            result_value = self.get_result_for_request(request)
            if not result_value:
                return JsonResponse({}, status=400)
            return self._delete_item(result_value, material_id)
        # обработка удаления старых файлов, не привязанных к результатам из лабс
        material = self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'result_v2__isnull': True,
            'id': request.POST.get('material_id', 0),
        })).first()
        if not material:
            return JsonResponse({}, status=400)
        logging.warning('User %s deleted old file %s for %s %s' %
                        (request.user.username, material.get_url(), self.lookup_attr, getattr(self, self.lookup_attr)))
        material.delete()
        return JsonResponse({})

    def _check_labs_result_id(self, request):
        try:
            result_id = int(request.POST.get('labs_result_id'))
        except (ValueError, TypeError):
            return JsonResponse({}, status=400), None, None
        result = LabsEventResult.objects.filter(id=result_id, block__event_id=self.event.id).\
            select_related('block').first()
        if not result_id or not result:
            return JsonResponse({}, status=400), None, None
        return None, result.deleted or result.block.deleted, self.is_according_result_type(result)

    def is_according_result_type(self, result):
        """
        проверка того, что формат результата соответствует типу загрузки
        """
        return True

    def block_has_available_results(self, block):
        """
        проверка того, что в блоке есть результаты нужного формата
        """
        return True

    def _get_result_key(self):
        return 'result_v2'

    def _get_result_value(self, request):
        return self.get_result_for_request(request)

    def update_add_item_response(self, resp, material, trace):
        resp['comment'] = trace.comment
        resp['result_url'] = trace.get_page_url()
        resp['circle_items'] = [{'id': i.id, 'tool': i.tool} for i in trace.result.available_circle_items]
        resp['selected_circle_items'] = list(trace.circle_items.values_list('id', flat=True))
        # отправка сообщения об изменении результата
        if self.should_send_to_kafka(trace):
            send_object_info(trace, trace.id, KafkaActions.UPDATE,
                             additional_data={'what': ResultUpdateType.ADD_FILE})

    def _delete_item(self, trace, material_id):
        result_id = trace.id
        material = self.material_model.objects.filter(**self._update_query_dict({
            'event': self.event,
            'id': material_id,
            'result_v2': trace,
        })).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        self._log_material_delete(material)
        # удаление связи пользователя/команды с результатом, если у пользователя/команды больше нет файлов
        # с привязкой к этому результату
        should_send = self.should_send_to_kafka(trace)
        additional_data = None
        if not self.material_model.objects.filter(
                **self._update_query_dict({'result_v2': trace, 'event': self.event})).exists():
            trace.delete()
            action = KafkaActions.DELETE
        else:
            action = KafkaActions.UPDATE
            additional_data = {'what': ResultUpdateType.DELETE_FILE}
        if should_send:
            send_object_info(trace, result_id, action, additional_data=additional_data)
        return JsonResponse({})

    def _log_material_delete(self, material):
        pass

    def get_result_for_request(self, request):
        return self.results_model.objects.filter(**self._update_query_dict({
            'result_id': request.POST.get('labs_result_id'),
            'id': request.POST.get('result_item_id')
        })).first()

    def should_send_to_kafka(self, result):
        """
        проверка того, что для соответствующего результата блока заданы ячейки
        """
        return bool(result.result.circle_items.exists())


class LoadMaterials(BaseLoadMaterialsWithAccessCheck):
    """
    Просмотр/загрузка материалов по эвенту
    """
    material_model = EventMaterial
    extra_context = {'with_public_checkbox': True, 'user_upload': True}

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({'other_materials': self.user.connected_materials.order_by('id')})
        return data

    def _can_set_public(self):
        return self.request.user.unti_id == int(self.kwargs['unti_id'])

    def can_upload(self):
        return self.current_user_is_assistant or int(self.kwargs['unti_id']) == self.request.user.unti_id

    def get_materials(self):
        if self.can_upload():
            qs = EventMaterial.objects.filter(event=self.event, user=self.user, trace__isnull=False)
        else:
            qs = EventMaterial.objects.filter(event=self.event, user=self.user, trace__isnull=False, is_public=True)
        self.set_initiator_users_to_qs(qs)
        return qs

    @cached_property
    def user(self):
        return get_object_or_404(User, unti_id=self.kwargs['unti_id'])

    def _delete_item(self, trace, material_id):
        material = EventMaterial.objects.filter(
            event=self.event, user=self.user, trace=trace, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        logging.warning('User %s has deleted file %s for user %s' %
                        (self.request.user.username, material.get_url(), self.user.username))
        return JsonResponse({})

    def add_item(self, request, **kwargs):
        if not (EventEntry.objects.filter(event=self.event, user=self.user).exists() or (self.event.run_id and
                RunEnrollment.objects.filter(run_id=self.event.run_id, user=self.user).exists())):
            return JsonResponse({}, status=400)
        return super().add_item(request, **kwargs)

    def get_material_fields(self, request):
        public = self._can_set_public() and request.POST.get('is_public') in ['on']
        return dict(event=self.event, user=self.user, is_public=public,
                    comment=request.POST.get('comment', ''))

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, str(self.user.unti_id), fn)


class LoadUserMaterialsResult(BaseLoadMaterialsLabsResults, LoadMaterials):
    template_name = 'personal_results.html'
    material_model = EventMaterial
    extra_context = {'user_upload': True}

    def get_material_fields(self, request):
        return dict(event=self.event, user=self.user, is_public=True,
                    loaded_by_assistant=self.current_user_is_assistant)

    def _log_material_delete(self, material):
        logging.warning('User %s has deleted file %s for user %s' %
                        (self.request.user.username, material.get_url(), self.user.username))

    def is_according_result_type(self, result):
        return result.is_personal()

    def block_has_available_results(self, block):
        return not block.block_has_only_group_results()

    def update_add_item_response(self, resp, material, trace):
        super().update_add_item_response(resp, material, trace)
        resp.update({
            'target_item_info': {
                'type': 'user',
                'name': trace.user.fio,
                'id': trace.user.unti_id,
                'image': trace.user.icon,
            }
        })


class LoadTeamMaterials(BaseLoadMaterialsWithAccessCheck):
    """
    Просмотр/загрузка командных материалов по эвенту
    """
    extra_context = {'with_comment_input': True, 'team_upload': True}
    material_model = EventTeamMaterial

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        users = self.team.users.order_by('last_name', 'first_name', 'second_name')
        num = dict(EventMaterial.objects.filter(event=self.event, user__in=users).
                   values_list('user_id').annotate(num=Count('event_id')))
        for u in users:
            u.materials_num = num.get(u.id, 0)
        data.update({'students': users, 'event': self.event, 'team_name': getattr(self.team, 'name', ''),
                     'event_participants': list(self.event.get_participant_ids()),
                     'team': self.team, 'other_materials': self.team.connected_materials.order_by('id')})
        return data

    @cached_property
    def team(self):
        return get_object_or_404(Team, id=self.kwargs['team_id'])

    def get_materials(self):
        qs = EventTeamMaterial.objects.filter(event=self.event, team=self.team)
        self.set_initiator_users_to_qs(qs)
        return qs

    def can_upload(self):
        # командные файлы загружает ассистент или участники этой команды
        return self.current_user_is_assistant or self.team.users.filter(id=self.request.user.id).exists()

    def post(self, request, *args, **kwargs):
        # загрузка и удаление файлов доступны только для эвентов, доступных для оцифровки, и по
        # командам, сформированным в данном эвенте
        if not self.event.is_active or not (self.current_user_is_assistant or
                Team.objects.filter(event=self.event, id=self.kwargs['team_id']).exists()):
            return JsonResponse({}, status=403)
        try:
            trace_id = int(request.POST.get('trace_name'))
        except (ValueError, TypeError):
            return JsonResponse({}, status=400)
        if not trace_id or not trace_id in [i.id for i in self.event.get_traces()]:
            return JsonResponse({}, status=400)
        if 'add_btn' in request.POST:
            return self.add_item(request)
        return self.delete_item(request)

    def check_post_allowed(self, request):
        # загрузка и удаление файлов доступны только для эвентов, доступных для оцифровки, и по
        # командам, сформированным в данном эвенте
        if super().check_post_allowed(request) is not None or not \
                Team.objects.filter(Q(event=self.event, id=self.kwargs['team_id'], system=Team.SYSTEM_UPLOADS) |
                                    (Q(system=Team.SYSTEM_PT, contexts=self.event.context, id=self.kwargs['team_id']))
                                    ).exists():
            return JsonResponse({}, status=403)

    def _delete_item(self, trace, material_id):
        material = EventTeamMaterial.objects.filter(
            event=self.event, team=self.team, trace=trace, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        material.delete()
        logging.warning('User %s has deleted file %s for team %s' %
                        (self.request.user.username, material.get_url(), self.team.id))
        return JsonResponse({})

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, str(self.team.team_name), fn)

    def get_material_fields(self, request):
        return dict(event=self.event, team=self.team, comment=request.POST.get('comment', ''),
                    confirmed=self.current_user_is_assistant)


class LoadTeamMaterialsResult(BaseLoadMaterialsLabsResults, LoadTeamMaterials):
    results_model = LabsTeamResult
    legacy_results_model = TeamResult
    lookup_attr = 'team'
    template_name = 'team_results.html'

    def get_material_fields(self, request):
        return dict(event=self.event, team=self.team, loaded_by_assistant=self.current_user_is_assistant)

    def _log_material_delete(self, material):
        logging.warning('User %s has deleted file %s for team %s' %
                        (self.request.user.username, material.get_url(), self.team.id))

    def is_according_result_type(self, result):
        return result.is_group()

    def block_has_available_results(self, block):
        return not block.block_has_only_personal_results()

    def update_add_item_response(self, resp, material, trace):
        super().update_add_item_response(resp, material, trace)
        participants = self.event.get_participant_ids()
        resp.update({
            'target_item_info': {
                'type': 'team',
                'name': trace.team.name,
                'id': trace.team.id,
                'users': [{
                    'name': user.fio, 'image': user.icon, 'enrolled': user.id in participants,
                } for user in trace.team.users.all()],
            }
        })


class LoadEventMaterials(GetEventMixin, BaseLoadMaterials):
    """
    Загрузка материалов мероприятия
    """
    material_model = EventOnlyMaterial
    extra_context = {'with_comment_input': True, 'show_owners': True, 'event_upload': True}

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated and self.current_user_is_assistant and 'change_material_info' in request.POST:
            return self.change_material_info(request)
        return super().post(request, *args, **kwargs)

    def change_material_info(self, request):
        result_key, result_value = self.get_result_key_and_value(request)
        if not result_value:
            return JsonResponse({}, status=400)
        try:
            material = self.material_model.objects.get(id=request.POST.get('material_id'), event=self.event)
            original_trace_id = material.trace_id
        except (self.material_model.DoesNotExist, ValueError, TypeError):
            return JsonResponse({}, status=400)
        comment = request.POST.get('comment') or ''
        material.trace = result_value
        material.comment = comment
        material.save(update_fields=['comment', 'trace'])
        logging.info('User %s updated material %s. Trace_id: %s, comment: %s' %
                     (request.user.username, material.id, result_value.id, comment))
        return JsonResponse({
            'comment': comment,
            'trace_id': result_value.id,
            'info_str': material.get_info_string(),
            'original_trace_id': original_trace_id,
            'material_id': material.id,
        })

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data.update({
            'event_users': self.event.get_participants(),
            'event_teams': Team.objects.filter(event=self.event).order_by('name'),
            'blocks_form': EventMaterialForm(event=self.event),
        })
        return data

    def can_upload(self):
        """
        любой пользователь может грузить материалы мероприятия
        """
        return True

    def get_unattached_files(self):
        return self.material_model.objects.filter(event=self.event, trace__isnull=True)

    def get_materials(self):
        qs = EventOnlyMaterial.objects.filter(event=self.event)
        self.set_initiator_users_to_qs(qs)
        return qs

    def _delete_item(self, trace, material_id):
        material = EventOnlyMaterial.objects.filter(
            event=self.event, trace=trace, id=material_id
        ).first()
        if not material:
            return JsonResponse({}, status=400)
        if not (self.request.user.unti_id and self.request.user.unti_id == material.initiator or
                self.current_user_is_assistant):
            return JsonResponse({}, status=400)
        if self.event.uid == getattr(settings, 'API_DATA_EVENT', ''):
            ApiUserChart.objects.update(updated=None)
        material.delete()
        logging.warning('User %s has deleted file %s for event %s' %
                        (self.request.user.username, material.get_url(), self.event.uid))
        return JsonResponse({})

    def make_file_path(self, fn):
        return os.path.join(self.event.uid, fn)

    def get_material_fields(self, request):
        return dict(event=self.event, comment=request.POST.get('comment', ''))

    def update_add_item_response(self, resp, material, trace):
        if not isinstance(trace, Trace):
            return
        form = EventMaterialForm(instance=material, data=self.request.POST, prefix=str(trace.id), event=self.event)
        if form.is_valid():
            material = form.save()
        resp['trace_id'] = trace.id
        resp['info_string'] = material.get_info_string()
        logging.info('User %s created block info for material %s: %s' %
                     (self.request.user.username, material.id, resp['info_string']))


class SummaryAutosave(GetEventMixinWithAccessCheck, View):
    """
    автосохранение черновика конспекта
    """
    def post(self, request, **kwargs):
        if 'id' in request.POST:
            return self.do_update(request)
        return self.do_create(request)

    def do_create(self, request):
        result_type = request.POST.get('result_type')
        result_id = request.POST.get('result_id')
        content = request.POST.get('content', '')
        try:
            if result_type == 'labseventresult':
                result = LabsEventResult.objects.select_related('block').get(id=result_id)
                assert result.block.event_id == self.event.id
            else:
                result = None
        except (AssertionError, ValueError, TypeError, ObjectDoesNotExist):
            return JsonResponse({}, status=400)
        summary = Summary.objects.create(author=request.user, result=result, content=content, event=self.event)
        return JsonResponse({'summary_id': summary.id})

    def do_update(self, request):
        summary_id = request.POST.get('id')
        try:
            summary = Summary.objects.get(id=summary_id)
            assert summary.is_draft and summary.author_id == request.user.id and summary.event_id == self.event.id
        except (Summary.DoesNotExist, ValueError, TypeError, AssertionError):
            return JsonResponse({}, status=400)
        summary.content = request.POST.get('content', '')
        summary.save(update_fields=['content'])
        return JsonResponse({'summary_id': summary.id})


class SummaryDelete(GetEventMixinWithAccessCheck, View):
    """
    Удаление черновика конспекта
    """
    def post(self, request, **kwargs):
        try:
            Summary.objects.filter(is_draft=True, author=request.user, event=self.event,
                                   id=request.POST.get('id')).delete()
            return JsonResponse({})
        except (ValueError, TypeError):
            return JsonResponse({}, status=400)


@method_decorator(login_required, name='dispatch')
class IsMaterialPublic(GetEventMixin, View):
    def post(self, request, uid=None):
        try:
            trace = EventMaterial.objects.get(id=request.POST.get('trace_id'))
        except (EventMaterial.DoesNotExist, ValueError, TypeError):
            return JsonResponse({}, status=404)
        if trace.user != request.user:
            return JsonResponse({}, status=403)
        is_public = request.POST.get('is_public') in ['true', 'True']
        EventMaterial.objects.filter(id=trace.id).update(is_public=is_public)
        return JsonResponse({'is_public': is_public})


class ConfirmTeamMaterial(GetEventMixin, View):
    def post(self, request, uid=None, team_id=None):
        if not request.user.is_authenticated or not self.current_user_is_assistant:
            return JsonResponse({}, status=403)
        try:
            team = Team.objects.get(event=self.event, id=team_id)
            confirmed = EventTeamMaterial.objects.filter(team=team, id=request.POST.get('material_id')).\
                update(confirmed=True)
            assert confirmed
            logging.info('User %s confirmed team %s upload %s' %
                         (request.user.username, team.id, request.POST.get('material_id')))
        except (Team.DoesNotExist, EventTeamMaterial.DoesNotExist, ValueError, TypeError, AssertionError):
            return JsonResponse({}, status=404)
        return JsonResponse({})


class BaseOwnershipChecker(GetEventMixin, View):
    def post(self, request, **kwargs):
        if self.current_user_is_assistant or not EventEntry.objects.filter(event=self.event, user=request.user):
            return JsonResponse({}, status=403)
        material = self.get_material()
        confirm = request.POST.get('confirm')
        if confirm not in ['true', 'false']:
            return JsonResponse({}, status=400)
        confirm = confirm == 'true'
        if confirm:
            material.owners.add(request.user)
        else:
            material.owners.remove(request.user)
        return JsonResponse({'is_owner': confirm, 'owners': ', '.join(material.get_owners())})


class TeamMaterialOwnership(BaseOwnershipChecker):
    """не используется"""
    def get_material(self):
        return get_object_or_404(EventTeamMaterial, id=self.kwargs['material_id'], event=self.event,
                                 team_id=self.kwargs['team_id'])


class EventMaterialOwnership(BaseOwnershipChecker):
    """не используется"""
    def get_material(self):
        return get_object_or_404(EventOnlyMaterial, id=self.kwargs['material_id'], event=self.event)


class TransferView(GetEventMixin, View):
    def dispatch(self, request, *args, **kwargs):
        # not used
        return HttpResponseForbidden()
        if request.user.is_authenticated and not self.current_user_is_assistant:
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, uid=None):
        if request.POST.get('type') == 'event':
            return self.move_to_event(request)
        if request.POST.get('type') not in ['team']:
            return JsonResponse({}, status=400)
        try:
            material = EventOnlyMaterial.objects.get(event=self.event, id=request.POST.get('material_id'))
        except (EventOnlyMaterial.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=404)
        if request.POST['type'] == 'user':
            return self.move_to_user(request, material)
        return self.move_to_team(request, material)

    def move_to_user(self, request, material):
        try:
            user = User.objects.get(id=request.POST.get('dest_id'))
        except (User.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=404)
        if not (EventEntry.objects.filter(event=self.event, user=user).exists() or
                (self.event.run_id and RunEnrollment.objects.filter(run_id=self.event.run_id, user=user).exists())):
            return JsonResponse({}, status=400)
        EventMaterial.copy_from_object(material, user)
        logging.info('User %s transferred event file %s to user %s' % (request.user.username, material.id, user.id))
        return JsonResponse({})

    def move_to_team(self, request, material):
        try:
            team = Team.objects.get(id=request.POST.get('dest_id'))
        except (Team.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=404)
        if not Team.objects.filter(id=team.id, event=self.event).exists():
            return JsonResponse({}, status=400)
        EventTeamMaterial.copy_from_object(material, team)
        logging.info('User %s transferred event file %s to team %s' % (request.user.username, material.id, team.id))
        return JsonResponse({})

    def move_to_event(self, request):
        model = {'true': EventMaterial, 'false': EventTeamMaterial}.get(request.POST.get('from_user'))
        if not model:
            return JsonResponse({}, status=400)
        try:
            obj = model.objects.get(id=request.POST.get('material_id'), event=self.event)
        except (model.DoesNotExist, TypeError, ValueError):
            return JsonResponse({}, status=404)
        if not obj.trace:
            return JsonResponse({}, status=404)
        if model == EventMaterial and not (EventEntry.objects.filter(event=self.event, user=obj.user_id).exists() or
                                           (self.event.run_id and RunEnrollment.objects.filter(
                                               run_id=self.event.run_id, user_id=obj.user_id).exists())):
            return JsonResponse({}, status=400)
        if model == EventTeamMaterial and not Team.objects.filter(id=obj.team_id, event=self.event).exists():
            return JsonResponse({}, status=400)
        EventOnlyMaterial.copy_from_object(obj)
        logging.info('User %s transferred %s file %s to event' %
                     (request.user.username, 'user' if model == EventMaterial else 'team', obj.id))
        return JsonResponse({})


class EventDigitalTrace(GetEventMixin, TemplateView):
    """
    страница цс мероприятия
    """
    template_name = 'event_dtrace.html'
    extra_context = {'can_upload': True}

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        blocks = self.event.blocks.prefetch_related('results', 'results__circle_items')
        form = self.get_filter_form()
        team_filter, user_filter, approved_filter, search_filter = self.get_filters(form)
        qs_user_results, qs_user_materials = self.get_results_and_files(
            LabsUserResult, EventMaterial, user_filter, approved_filter, search_filter
        )
        qs_team_results, qs_team_materials = self.get_results_and_files(
            LabsTeamResult, EventTeamMaterial, team_filter, approved_filter, search_filter
        )
        blocks = self.add_info_to_blocks(blocks, qs_user_materials, qs_user_results, 'user')
        blocks = self.add_info_to_blocks(blocks, qs_team_materials, qs_team_results, 'team')

        user_upload_url_pattern = reverse('load-materials', kwargs={'uid': self.event.uid, 'unti_id': 0})
        user_upload_url_pattern = user_upload_url_pattern.replace('/0/', '/{REPLACE}/')
        team_upload_url_pattern = reverse('load-team-materials', kwargs={'uid': self.event.uid, 'team_id': 0})
        team_upload_url_pattern = team_upload_url_pattern.replace('/0/', '/{REPLACE}/')

        user_teams = list(Team.objects.filter(system=Team.SYSTEM_UPLOADS, event=self.event, users=self.request.user)
                          .values_list('id', flat=True)) + \
            list(self.event.get_pt_teams().filter(users=self.request.user).values_list('id', flat=True))
        structure = [
            {
                'title': block.title,
                'deleted': block.deleted,
                'results': [
                    {
                        'id': result.id,
                        'deleted': result.deleted,
                        'title': 'Результат {}.{}'.format(i, j),
                        'is_personal': result.is_personal(),
                        'is_group': result.is_group(),
                    } for j, result in enumerate(block.results.all(), 1)
                ]
            } for i, block in enumerate(blocks, 1)
        ]
        is_enrolled = EventEntry.objects.filter(user=self.request.user, event=self.event).exists()

        data.update({
            'event': self.event,
            'blocks': blocks,
            'filter_form': form,
            'allow_file_upload': getattr(settings, 'ALLOW_FILE_UPLOAD', True),
            'max_size': settings.MAXIMUM_ALLOWED_FILE_SIZE,
            'max_uploads': settings.MAX_PARALLEL_UPLOADS,
            'user_upload_url_pattern': user_upload_url_pattern,
            'team_upload_url_pattern': team_upload_url_pattern,
            'user_content_type_id': ContentType.objects.get_for_model(User).id,
            'team_content_type_id': ContentType.objects.get_for_model(Team).id,
            'is_assistant': self.current_user_is_assistant,
            'participant_ids': self.event.get_participant_ids(),
            'user_teams': user_teams,
            'blocks_structure_json': json.dumps(structure, ensure_ascii=False),
            'SUMMARY_SAVE_INTERVAL': settings.SUMMARY_SAVE_INTERVAL,
            'can_upload': self.current_user_is_assistant or is_enrolled,
            'is_enrolled': is_enrolled,
        })

        return data

    def get_filters(self, form):
        selected_user, selected_team = None, None
        team_filter, user_filter, approved_filter, search_filter = {}, {}, {}, Q()
        if form.is_valid():
            if form.cleaned_data.get('item'):
                if isinstance(form.cleaned_data.get('item'), User):
                    selected_user = form.cleaned_data.get('item')
                elif isinstance(form.cleaned_data.get('item'), Team):
                    selected_team = form.cleaned_data.get('item')
            if form.cleaned_data.get('only_my'):
                selected_user = self.request.user
            if selected_user:
                user_filter = {'user': selected_user}
                team_filter = {
                    'team_id__in': list(Team.objects.filter(users=selected_user).values_list('id', flat=True))}
            elif selected_team:
                user_filter = {'user_id__in': []}
                team_filter = {'team': selected_team}
            if form.cleaned_data.get('approved') == form.APPROVED_TRUE:
                approved_filter['approved'] = True
            elif form.cleaned_data.get('approved') == form.APPROVED_FALSE:
                approved_filter['approved'] = False
            elif form.cleaned_data.get('approved') == form.APPROVED_NONE:
                approved_filter['approved__isnull'] = True
            search = form.cleaned_data.get('search')
            if search:
                search_filter = Q(url__icontains=search) | Q(file__icontains=search) | \
                                Q(result_v2__comment__icontains=search)
        return team_filter, user_filter, approved_filter, search_filter

    def get_results_and_files(self, result_model, materials_model, person_filter, approved_filter, search_filter):
        qs_materials = materials_model.objects.filter(
            event=self.event,
            result_v2__isnull=False,
            **person_filter
        )
        if search_filter:
            qs_materials = qs_materials.filter(search_filter)
        qs_results = result_model.objects.filter(result__block__event_id=self.event.id, **person_filter,
                                                 **approved_filter)
        return qs_results, qs_materials

    def get_filter_form(self):
        form_class = EventDTraceAdminFilter if self.current_user_is_assistant else EventDTraceFilter
        return form_class(event=self.event, data=self.request.GET)

    def add_info_to_blocks(self, blocks, qs_materials, qs_results, result_type):
        materials = defaultdict(list)
        for m in qs_materials:
            materials[m.result_v2_id].append(m)
        results = defaultdict(list)
        for item in qs_results:
            item.type = result_type
            item.links = materials.get(item.id, [])
            if item.links:
                results[item.result_id].append(item)
        for result_id, items in results.items():
            by_attr = defaultdict(list)
            for item in items:
                by_attr[getattr(item, result_type)].append(item)
            results[result_id] = [{'type': result_type, 'obj': k, 'items': v} for k, v in by_attr.items()]
        for block in blocks:
            for result in block.results.all():
                if not hasattr(result, 'results'):
                    result.results = []
                result.results.extend(results.get(result.id, []))
        return blocks
