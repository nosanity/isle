let counter = 0;
const uploads = [];

let maxSizeSelector = null;
let structureEditSelectDisablerIsSet = false;

const UPLOAD_TYPE_FILE = 'file';
const UPLOAD_TYPE_URL = 'url';
const UPLOAD_TYPE_SUMMARY = 'summary';

CKEDITOR.replaceAll('ckedit');

const formClass = pageType == 'loadMaterials' ? '.trace-form' : '.user-materials-form'


class SummaryObserver {
    constructor(instance) {
        this.instance = instance;
        this.last_sync = null;
        this.summary_id = $(instance.element.$).data('draft-id') || null;
        this.last_change = null;
        this.content = instance.getData();
        this.interval_id = window.setInterval(() => {this.loop();}, SUMMARY_SAVE_INTERVAL);
    }

    destroy() {
        window.clearInterval(this.interval_id);
    }

    loop() {
        let has_contents = !!this.instance.getData();
        if (has_contents && this.summary_id == null) {
            this.init();
        }
        if (this.summary_id != null && this.last_change > this.last_sync) {
            this.sync();
        }
    }

    dataUpdated() {
        let data = this.instance.getData();
        if (data != this.content) {
            this.last_change = new Date();
            this.content = data;
        }
    }

    init() {
        let data = {
            csrfmiddlewaretoken: csrfmiddlewaretoken,
            result_type: resultType,
            result_id: $(this.instance.element.$).parents('.material-result-div').data('result'),
            content: this.instance.getData(),
        }
        let self = this;
        $.ajax({
            method: 'POST',
            url: summarySyncUrl,
            data: data,
            success: (resp) => {
                self.summary_id = resp['summary_id'];
                self.last_sync = new Date();
                $(self.instance.element.$).data('draft-id', self.summary_id);
            }
        })
    }

    sync() {
        let self = this;
        let data = {
            csrfmiddlewaretoken: csrfmiddlewaretoken,
            id: this.summary_id,
            content: this.content,
        }
        $.ajax({
            method: 'POST',
            url: summarySyncUrl,
            data: data,
            success: (resp) => {
                self.last_sync = new Date();
            }
        })
    }
}

function ckeditor_changed(e) {
    let id = $(e.editor.element).attr('id');
    if (window.summary_observers === undefined)
        window.summary_observers = {};
    if (e.editor.getData()) {
        if (window.summary_observers[id] === undefined)
            window.summary_observers[id] = new SummaryObserver(e.editor);
        window.summary_observers[id].dataUpdated();
    }
    setActivateButton($(e.editor.element.$).parents(formClass));
}

for (key in CKEDITOR.instances) {
    CKEDITOR.instances[key].on( 'change', ckeditor_changed);
}

function get_error_msg(xhr) {
    try {
        return xhr.responseJSON.error || 'error';
    }
    catch (e) {
        return 'error';
    }
}

if (pageType == 'loadMaterials' || pageType == 'eventStructure') {
    maxSizeSelector = 'form.trace-form input[type=file]';

    const $forms = $('form.trace-form');
    for (form of $forms) {
        $(form).areYouSure({
            fieldSelector: ':input:not(input[type=submit]):not(input[type=button]):not(.btn)'
        });
    }

    $forms.submit((e) => {
        e.preventDefault();
        formSubmitHadler(e.target);
    });

    $('body').delegate('input.upload_is_public', 'change', (e) => {
        const $obj = $(e.target);
        const isPublic = $obj.prop('checked');
        const csrfmiddlewaretoken = $obj.parents('form.trace-form').find('input[name=csrfmiddlewaretoken]').val();
        const traceId = $obj.data('link-id');

        $.ajax({
            url: changeState,
            method: 'POST',
            data: {
                csrfmiddlewaretoken: csrfmiddlewaretoken,
                trace_id: traceId,
                is_public: isPublic
            },
            error: function () {
                $obj.prop('checked', !isPublic);
            }
        })
    });
}
else if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace') {
    maxSizeSelector = 'form.user-materials-form input[type=file]';

    const $forms = $('form.user-materials-form');
    for (form of $forms) {
        $(form).areYouSure({
            fieldSelector: ':input:not(input[type=submit]):not(input[type=button]):not(.btn)'
        });
    }

    $forms.submit((e) => {
        e.preventDefault();
        formSubmitHadler(e.target);
    });
} else if (pageType == 'loadUserMaterials') {
    maxSizeSelector = '#result_form input[type=file]';

    $('#result_form').submit((e) => {
        e.preventDefault();
        resultFormHandler(e);
    })

    $('body').delegate('.edit-result', 'click', (e) => {
        e.preventDefault();
        if (uploads.length > 0) {
            alert('Дождитесь окончания загрузки файлов');
            return;
        }
        const data = $(e.target).data('result');
        const $form = $('#result_form');
        clearForm($form);
        $form.find('[name="result_id"]').val(data.id);
        setAutocompleteChoice($form.find('[name="result_type"]'), data.result_type, data.result_type_display);
        $form.find('[name="rating"] option[value="' + data.rating + '"]').prop('selected', true);
        $form.find('[name="competences"]').val(data.competences);
        $form.find('[name="result_comment"]').val(data.result_comment);
        window.scrollTo(0, 0);
        if (formsetRenderUrl) {
            $form.find('[name="group_dynamics"]').val(data.group_dynamics);
            $.ajax({
                url: formsetRenderUrl,
                method: 'GET',
                data: {
                    id: data.id
                },
                success: (data) => {
                    $('div.user-roles-div').html(data);
                },
                error: (xhr, err) => {
                    // TODO show appropriate message
                    alert(get_error_msg(xhr));
                }
            })
        }
    });
}

function addUploadProgress($form, fileField) {
    const name = fileField.name;
    const rowNum = counter++;
    const html = `
        <div class="row upload-row" data-row-number="${rowNum}">
            <div class="col-lg-3 uploads-name">
                <span class="uploaded-file-name">${name}</span>
            </div>
            <div class="col-lg-9 uploads-progress pt-5">      
                <div class="progress">
                    <div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100"></div>
                </div>
            </div>
        </div>
    `;
    $form.find('div.uploads').append(html);
    uploads.push(rowNum);

    return rowNum;
}

function get_url_from_item_wrapper(obj) {
    let id = obj.data('id').split('-');
    let pattern = id[0] == 'user' ? userUploadPattern : teamUploadPattern;
    return pattern.replace('{REPLACE}', id[1]);
}

function isFormValid($form) {
    let data_filled = false;
    switch (get_form_upload_type($form)) {
        case UPLOAD_TYPE_FILE:
            data_filled = !!$form.find('input[name=file_field]').val();
            break;
        case UPLOAD_TYPE_URL:
            data_filled = !!$form.find('input[name=url_field]').val();
            break;
        case UPLOAD_TYPE_SUMMARY:
            data_filled = !!CKEDITOR.instances[$form.find('.ckedit').attr('id')].getData();
            break;
    }
    let additional_check = true;

    if (pageType  == 'loadMaterials') {
        additional_check = !!$form.find('select[name=trace_name]').val();
    }

    if (pageType == 'event_dtrace' && $form.find('.user-or-team-autocomplete-selector').length) {
        additional_check = !!$form.find('.user-or-team-autocomplete-selector').val();
    }

    return additional_check && data_filled;
}

function setActivateButton($form) {
    let selector = null;
    if (pageType == 'loadMaterials' || pageType == 'eventStructure' || pageType == 'loadMaterials_v2' || pageType == 'event_dtrace') {
        selector = '.add-material-btn';
    } else if (pageType == 'loadUserMaterials') {
        selector = '.save-result-btn';
    }
    if (isFormValid($form)) {
        $form.find(selector).prop('disabled', false);
    }
    else {
        $form.find(selector).prop('disabled', true);
    }
}

function clearFileForm($form) {
    $form.find('span.file-name').html('');
    $form.find('input[name=url_field]').val('');
    $form.find('input[name=file_field]').val('');
    $form.find('[name=comment]').val('');
    $form.find('input[name=is_public]').prop('checked', false);
    let ckeditor_id = $form.find('.ckedit').attr('id');
    if (ckeditor_id)
        CKEDITOR.instances[ckeditor_id].setData('');
        clear_draft_id($form);
    try {
        $form.find('[name$=event_block]').val('');
        clearAutocompleteChoice($form.find('[name$=related_users]'));
        clearAutocompleteChoice($form.find('[name$=related_teams]'));
    }
    catch (e) {
        // do nothing
    }
    if (pageType == 'event_dtrace') {
        yl.jQuery($form.find('select.user-or-team-autocomplete-selector')[0]).val(null).trigger('change');
    }
}

function result_edit_switcher(result, editable) {
    let el, text, html;
    if (editable) {
        result.find('.edit-result-comment').hide();
        el = result.find('.result-comment');
        text = el.html().trim();
        html = `
        <form class="result-comment-edit-form">
            <textarea class="hidden old_comment_value">${text}</textarea>
            <textarea maxlength="255" class="form-control width-80 mb-6 result-comment-edit-input">${text}</textarea>
            <button class="btn btn-success btn-edit-comment-save">Обновить комментарий</button>
            <button  class="btn btn-danger btn-edit-comment-cancel">Отменить</button>
        </form>
        `;
        el.replaceWith(html);
    }
    else {
        result.find('.edit-result-comment').show();
        el = result.find('.result-comment-edit-form');
        text = result.find('.result-comment-edit-input').val();
        html = '<p class="result-comment">' + text + '</p>';
        el.replaceWith(html);
    }
}

function show_trace_name(trace_id) {
    let wrapper = $('div.event-trace-materials-wrapper[data-trace-id=' + trace_id + ']');
    let files_num = wrapper.find('ul.list-group li').length;
    if (wrapper.find('ul.list-group li').length > 0) {
        wrapper.find('.event-trace-name').show();
    }
    else {
        wrapper.find('.event-trace-name').hide();
    }
}

// handlers

$('body').delegate('.delete-material-btn', 'click', (e) => {
    e.preventDefault();
    if ($(':focus').attr('name') == 'material_id' || pageType == 'loadMaterials') {
        if (confirm('Вы действительно хотите удалить этот файл?')) {
            let obj;
            if ($(e.target).prop('tagName') == 'SPAN' && pageType != 'loadMaterials') {
                $obj = $(e.target).parents('button')
            }
            else {
                $obj = $(e.target);
            }
            const trace_id = $obj.parents('div.event-trace-materials-wrapper').data('trace-id');
            const data = {
                csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val() || csrfmiddlewaretoken,
                trace_name: trace_id,
                material_id: $obj.val() || $obj.attr('value')
            }
            if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace') {
                data['labs_result_id'] = $obj.parents('.material-result-div').data('result');
                data['result_item_id'] = $obj.parents('.result-materials-wrapper').data('result-id');
            }
            requestUrl = pageType == 'event_dtrace' ? get_url_from_item_wrapper($obj.parents('.item-result-wrapper')) : '';
            $.ajax({
                type: 'POST',
                data: data,
                url: requestUrl,
                success: (data) => {
                    if (pageType == 'event_dtrace') {
                        if ($obj.parents('.item-result-wrapper').find('li.result-item-li').length == 1)
                            $obj.parents('.item-result-wrapper').remove()
                         else
                            $obj.parents('li.result-item-li').remove();
                    }
                    else if (pageType == 'loadMaterials') {
                        $obj.parents('li.list-group-item').remove();
                        show_trace_name(trace_id);
                    }
                    else {
                        let el = $obj.parents('div.result-items-wrapper');
                        $obj.parent('li').remove();
                        resultFilesNumberHandler(el);
                    }
                },
                error: (xhr, err) => {
                    // TODO show appropriate message
                    alert(get_error_msg(xhr));
                }
            })
        }
    }
}).delegate('.delete-all-files', 'click', (e) => {
    e.preventDefault();
    if (confirm('Вы действительно хотите удалить все файлы результата?')) {
        let $obj = $(e.target);
        const data = {
            csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
            trace_name: $obj.parents('form.trace-form').children('input[name=trace_name]').val(),
            action: 'delete_all',
            result_item_id: $obj.parents('.result-item-li').find('.result-materials-wrapper').data('result-id'),
            labs_result_id: $obj.parents('.material-result-div').data('result')
        }
        $.ajax({
            type: 'POST',
            data: data,
            url: pageType == 'event_dtrace' ? get_url_from_item_wrapper($obj.parents('.item-result-wrapper')) : '',
            success: (data) => {
                if (pageType == 'event_dtrace' && $obj.parents('.item-result-wrapper').find('.result-item-li').length == 1)
                    $obj.parents('.item-result-wrapper').remove();
                else
                    $obj.parents('.result-item-li').remove();
                resultFilesNumberHandler($obj.parents('div.result-items-wrapper'));
            },
            error: (xhr, err) => {
                // TODO show appropriate message
                alert(get_error_msg(xhr));
            }
        })
    }
}).delegate('.edit-result-comment', 'click', (e) => {
    e.preventDefault();
    let $obj = $(e.target);
    result_edit_switcher($obj.parents('.result-item-li'), true);
}).delegate('.btn-edit-comment-save', 'click', (e) => {
    e.preventDefault();
    let $obj = $(e.target);
    const data = {
        csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
        action: 'edit_comment',
        result_item_id: $obj.parents('.result-item-li').find('.result-materials-wrapper').data('result-id'),
        labs_result_id: $obj.parents('.material-result-div').data('result'),
        comment: $obj.parents('.result-comment-edit-form').find('.result-comment-edit-input').val()
    };
    let url = '';
    if (pageType == 'event_dtrace') {
        url = get_url_from_item_wrapper($obj.parents('.item-result-wrapper'));
    }
    $.ajax({
        type: 'POST',
        data: data,
        url: url,
        error: (xhr, err) => {
            // TODO show appropriate message
            let t = $obj.parents('.result-item-li').find('.old_comment_value').val().trim();
            $obj.parents('.result-item-li').find('.result-comment-edit-input').val(t);
            alert(get_error_msg(xhr));
        },
        complete: (xhr, err) => {
            result_edit_switcher($obj.parents('.result-item-li'), false);
        }
    })
}).delegate('.btn-edit-comment-cancel', 'click', (e) => {
    e.preventDefault();
    let $obj = $(e.target);
    result_edit_switcher($obj.parents('.result-item-li'), false);
}).delegate('.move-deleted-result', 'click', (e) => {
    e.preventDefault();
    let $obj = $(e.target);
    let result = $obj.parents('.result-item-li').find('.result-materials-wrapper');
    let labs_result = $obj.parents('.material-result-div');
    requestUrl = pageType == 'event_dtrace' ? get_url_from_item_wrapper($obj.parents('.item-result-wrapper')) : '';
    let type = '';
    if (pageType == 'event_dtrace') {
        type = $obj.parents('.item-result-wrapper').data('id').split('-')[0];
    }
    build_move_result_modal(result, labs_result.data('result'), requestUrl, type);
}).delegate('#btn-move-selected-result', 'click', (e) => {
    let obj = $(e.target);
    obj.prop('disabled', true).attr('disabled', 'disabled');
    let post_data, result, old_result_wrapper;
    let url = $('#move_results_modal').data('request-url');
    if (obj.data('mv-type') == 'result') {
        post_data = {
            csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
            action: 'move',
            result_item_id: $(e.target).data('user_result'),
            labs_result_id: $(e.target).data('labs_result_id'),
            move_to: $('input[name="move-result-radiobox"]:checked').val()
        };
        if (pageType == 'event_dtrace') {
            result = $('.result-materials-wrapper[data-result-id="' + $(e.target).data('user_result') + '"][data-result-type=' + $(e.target).data('result-type') + ']')
            .parents('li.result-item-li');
            old_result_wrapper = result.parents('.item-result-wrapper');
        }
        else {
            result = $('.result-materials-wrapper[data-result-id="' + $(e.target).data('user_result') + '"]').parents('li.result-item-li');
            old_result_wrapper = result.parents('.material-result-div').find('ul.list-group')
        }
    }
    else {
        post_data = {
            csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
            action: 'move_unattached',
            material_id: obj.data('material_id'),
            move_to: $('input[name="move-result-radiobox"]:checked').val()
        };
    }
    $.ajax({
        type: 'POST',
        data: post_data,
        url: url,
        success: (data) => {
            if (obj.data('mv-type') == 'result') {
                if (pageType == 'event_dtrace') {
                    let destination = data.new_result_id;
                    let target_id = result.parents('.item-result-wrapper').data('id');
                    let result_block = $('.material-result-div[data-result="' + destination + '"]');
                    if (result_block.find('.item-result-wrapper[data-id=' + target_id + ']').length == 0) {
                        let description = result.parents('.item-result-wrapper').children('div').html();
                        let html = `
                            <div class="item-result-wrapper" data-id="${target_id}">
                                <div>${description}</div>
                                <ul class="list-group list-group-flush"></ul>
                            </div>
                        `;
                        result_block.append($(html));
                    }
                    target_block = result_block.find('.item-result-wrapper[data-id=' + target_id + ']').find('ul.list-group');
                    target_block.append(result);
                    if (old_result_wrapper.find('.result-item-li').length == 0) {old_result_wrapper.remove();}
                }
                else {
                    let destination = data.new_result_id;
                    let result_block = $('.material-result-div[data-result="' + destination + '"]').find('ul.list-group');
                    result.appendTo(result_block);
                    resultFilesNumberHandler(old_result_wrapper);
                    resultFilesNumberHandler(result_block);
                }
                $('#move_results_modal').modal('hide');
            }
            else {
                let destination = data.item_result_id;
                let result_block = $('.material-result-div[data-result="' + data.result_id + '"]').find('ul.list-group');
                successProcessFile(
                    data,
                    $('.material-result-div[data-result="' + data.result_id + '"]').find('form'),
                    destination
                );
                $('.move-unattached-file[data-file-id="' + obj.data('material_id') + '"]').parents('li.list-group-item').remove();
                $('#move_results_modal').modal('hide');
                resultFilesNumberHandler(result_block);
            }
        },
        error: (xhr, err) => {
            alert(get_error_msg(xhr));
        },
        complete: () => { obj.prop('disabled', false).removeAttr('disabled'); }
    })
}).delegate('.move-unattached-file', 'click', (e) => {
    e.preventDefault();
    build_move_result_modal($(e.target), null);
}).delegate('.add-event-material-assistant', 'click', (e) => {
    $('.add-event-materials-wrapper').removeClass('hidden');
}).delegate('.hide-add-event-materials-form-btn', 'click', (e) => {
    $('.add-event-materials-wrapper').addClass('hidden');
}).delegate('.do-approve-result', 'click', (e) => {
    e.preventDefault();
    let comment_container = $(e.target).parents('.approve-result-block').find('.current-approve-text')
    let post_data = {
        csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
        action: 'approve_result',
        labs_result_id: $(e.target).data('labs-result-id'),
        result_item_id: $(e.target).data('result-id'),
        approve_text: $(e.target).parents('.approve-text-edit').find('.approve-text-edit-input').val(),
        approved: $(e.target).parents('.approve-result-block').find('.approve-radio-btn:checked').val()
    }
    let url = '';
    if (pageType == 'event_dtrace') {
        url = get_url_from_item_wrapper($(e.target).parents('.item-result-wrapper'));
    }
    $.ajax({
        type: 'POST',
        data: post_data,
        url: url,
        success: (data) => {
            comment_container.text(data.approve_text);
            comment_container.parents('.approve-text').show();
            comment_container.parents('.approve-result-block').find('.approve-text-edit').data('approved', data.approved ? 'True' : 'False');
            comment_container.parents('.approve-result-block').find('.approve-text-edit').hide();
        },
        error: (xhr, err) => {
            alert(get_error_msg(xhr));
        },
    })
}).delegate('.approve-radio-btn', 'change', (e) => {
    let target = $(e.target);
    target.parents('.approve-result-block').find('.approve-text').hide();
    target.parents('.approve-result-block').find('.approve-text-edit').show();
}).delegate('.cancel-approve-btn', 'click', (e) => {
    e.preventDefault();
    let target = $(e.target);
    target.parents('.approve-result-block').find('.approve-text').show();
    target.parents('.approve-result-block').find('.approve-text-edit').hide();
    target.parents('.approve-result-block').find('.approve-radio-btn').each((i, el) => { $(el).prop('checked', false); });
    if (target.parents('.approve-result-block').find('.approve-text-edit').data('approved') == 'True') {
        target.parents('.approve-result-block').find('.approve-radio-btn[value=true]').prop('checked', true);
    }
    if (target.parents('.approve-result-block').find('.approve-text-edit').data('approved') == 'False') {
        target.parents('.approve-result-block').find('.approve-radio-btn[value=false]').prop('checked', true);
    }
}).delegate('.start-change-circle-items', 'click', (e) => {
    e.preventDefault();
    $(e.target).parents('.result-selected-circle-items-div').find('.change-circle-items, .cancel-change-circle-items').show();
    $(e.target).hide();
    $(e.target).parents('.result-selected-circle-items-div').find('.result-circle-items[data-can-edit=true]').prop('disabled', false);
}).delegate('.cancel-change-circle-items', 'click', (e) => {
    e.preventDefault();
    disable_circle_items_btns($(e.target).parents('.result-selected-circle-items-div'));
}).delegate('.change-circle-items', 'click', (e) => {
    e.preventDefault();
    let wrapper = $(e.target).parents('.result-selected-circle-items-div');
    let selected_ids = [];
    wrapper.find('.result-circle-items:checked').each((i, el) => { selected_ids.push($(el).val()) });
    let post_data = {
        csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
        action: 'change_circle_items',
        labs_result_id: $(e.target).data('labs-result-id'),
        result_item_id: $(e.target).data('result-id'),
        circle_items: selected_ids.join(',')
    };
    $.ajax({
        method: 'POST',
        data: post_data,
        url: pageType == 'event_dtrace'? get_url_from_item_wrapper(wrapper.parents('.item-result-wrapper')) : '',
        success: (data) => {
            let selected_ids = data['selected_items'].join(',');
            wrapper.data('selected-circle-items', selected_ids);
            disable_circle_items_btns(wrapper);
        },
        error: (xhr, err) => {
            alert(get_error_msg(xhr));
        }
    })
}).delegate('.upload-type-btn', 'shown.bs.tab', (e) => {
    adjust_upload_type($(e.target));
}).delegate('.hide-results-form-btn, .hide-add-event-materials-form-btn', 'click', (e) => {
    let form = $(e.target).parents(formClass);
    if (get_form_upload_type(form) == UPLOAD_TYPE_SUMMARY) {
        let summary_id = form.find('.ckedit').data('draft-id');
        if (summary_id) {
            $.ajax({
                method: 'POST',
                url: deleteSummaryUrl,
                data: {csrfmiddlewaretoken: csrfmiddlewaretoken, id: summary_id},
                complete: () => {
                    clear_draft_id(form);
                }
            });
        }
    }
}).delegate('.edit-result-structure', 'click', (e) => {
    e.preventDefault();
    let $obj = $(e.target);
    const url = pageType == 'event_dtrace' ? get_url_from_item_wrapper($obj.parents('.item-result-wrapper')) : '';
    const result_item_id = $obj.parents('.result-item-li').find('.result-materials-wrapper').data('result-id')
    const labs_id = $obj.parents('.material-result-div').data('result');
    open_structure_edit_window(url, labs_id, result_item_id);
}).delegate('#edit-structure-modal', 'shown.bs.modal', (e) => {
    $('#formset-structure-edit').formset({
        allowEmptyFormset: true,
        uiText: {
            addPrompt: 'Добавить',
            removePrompt: 'Удалить',
        },
        callbacks: {
            onAdd: (elem, index) => {
                $(elem).find('.form-group .col-sm-10').each((i, el) => {
                    $(el).find('span.select2-container').remove()
                    let select = $(el).find('select');
                    if (select && select.data('select2-id')) {
                        let id = select.data('select2-id').replace(new RegExp('id_form-(\\d+)-'), 'id_form-' + index + '-');
                        select.attr('data-select2-id', id);
                    }
                });
                $('#edit-structure-modal').find('select[data-select2-id]').each((i, el) => {
                    window.__dal__initialize($(el))
                });
                check_structure_enabled_selects($(elem));
            },
            postInitialize: (formset) => {
                formset.find('a.delete-row').last().trigger('click');
                $('#edit-structure-modal').css('opacity', 1);
                $(formset).find('.result-individual-structure-item').each((i, el) => {
                    check_structure_enabled_selects($(el))
                });
            }
        }
    });
    watch_edit_structure_selects_state();
}).delegate('.btn-save-edited-structure', 'click', (e) => {
    const formData = new FormData($('#formset-structure-edit').get(0));
    $.ajax({
        method: 'POST',
        url: $('#edit-structure-modal').data('url'),
        data: formData,
        processData: false,
        contentType: false,
        success: (data) => {
            if (data.status == 0) {
                $('#edit-structure-modal').modal('hide');
                let block;
                if (pageType == 'event_dtrace') {
                    block = $('.material-result-div[data-result=' + data['labs_result_id'] + ']')
                    .find('.item-result-wrapper[data-id=' + data['type'] + '-' + data['object_id'] + ']')
                    .find('.result-materials-wrapper[data-result-id=' + data['result_id'] + ']')
                    .parents('.result-item-li')
                    .find('.result-selected-circle-items-div');
                }
                else {
                    block = $('.material-result-div[data-result=' + data['labs_result_id'] + ']')
                    .find('.result-materials-wrapper[data-result-id=' + data['result_id'] + ']')
                    .parents('.result-item-li')
                    .find('.result-selected-circle-items-div');
                }
                let current_tools = [];
                block.find('.result-circle-items').each((i, el) => { current_tools.push(parseInt($(el).val())); })
                for (let tool_id in data['items']) {
                    tool_id = parseInt(tool_id);
                    if (current_tools.indexOf(tool_id) == -1) {
                        let new_tool = `
                        <div class="form-check">
                            <input type="checkbox" class="result-circle-items" value="${tool_id}" id="circle_item_${tool_id}_${data['result_id']}" data-can-edit="true">
                            <label class="result-circle-items-label" for="circle_item_${tool_id}_${data['result_id']}">${data['items'][tool_id]}</label>
                        </div>
                        `;
                        if (block.find('.form-check').length) {
                            block.find('.form-check').last().after($(new_tool));
                        }
                        else {
                            new_tool += `
                                <span class="start-change-circle-items">Изменить</span>
                                <span class="change-circle-items" data-labs-result-id="${data['labs_result_id']}" data-result-id="${data['result_id']}">Сохранить</span>
                                <span class="cancel-change-circle-items">Отменить</span>
                            `;
                            block.append($(new_tool))
                        }
                    }
                }
                block.find('.result-circle-items').each((i, el) => {
                    $(el).prop('checked', data['items'][parseInt($(el).val())] !== undefined).prop('disabled', true);
                });
            }
            else {
                $('#formset-structure-edit').find('.result-individual-structure-item:visible').each((i, form) => {
                    $(form).find('.error-container').remove();
                    $(form).find('.has-error').removeClass('has-error');
                    let errors = data.errors[i];
                    for (let key in errors) {
                        let input = $(form).find('[name$=-' + key + ']');
                        input.parents('.form-group').addClass('has-error').children('div').append($(`
                            <div class="error-container"><span class="small">${errors[key][0]}</span><div>
                        `));
                    }
                });
            }
        },
        error: () => { alert('error'); }
    });
}).delegate('.close-notification', 'click', (e) => {
    e.preventDefault();
    $(e.target).parents('.notification-wrapper').remove();
}).delegate('.edit-summary', 'click', (e) => {
    e.preventDefault();
    let $obj = $(e.target);
    $.ajax({
        method: 'GET',
        url: getFullSummaryUrl,
        data: {
            id: $obj.data('file-id'),
            type: $obj.data('type')
        },
        success: (data) => {
            let current_summary = $obj.parents('.result-item-li').find('.summary-content-short');
            current_summary.hide();
            let html = `
                <div class="summary-editor">
                    <textarea id="edit-summary-${data['id']}">${data['text']}</textarea>
                    <button class="btn btn-success edit-summary-save">Сохранить</button>
                    <button class="btn btn-danger edit-summary-cancel">Отменить</button>
                </div>
            `;
            current_summary.after($(html));
            CKEDITOR.replace('edit-summary-' + data['id']);
        }
    })
}).delegate('.edit-summary-save', 'click', (e) => {
    e.preventDefault();
    let $obj = $(e.target);
    let editor_id = $obj.parents('.summary-editor').find('textarea').attr('id');
    $.ajax({
        method: 'POST',
        url: pageType == 'event_dtrace' ? get_url_from_item_wrapper($obj.parents('.item-result-wrapper')) : '',
        data: {
            csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
            action: 'edit_summary',
            result_item_id: $obj.parents('.result-item-li').find('.result-materials-wrapper').data('result-id'),
            labs_result_id: $obj.parents('.material-result-div').data('result'),
            content: CKEDITOR.instances[editor_id].getData()
        },
        success: (data) => {
            let current_summary = $obj.parents('.result-item-li').find('.summary-content-short');
            let html = `
                <strong>Конспект:</strong> ${data['text']}
            `;
            current_summary.html(html);
            current_summary.show();
            CKEDITOR.instances[editor_id].destroy();
            $obj.parents('.summary-editor').remove();
        },
        error: () => { alert('error'); }
    })
}).delegate('.edit-summary-cancel', 'click', (e) => {
    e.preventDefault();
    $(e.target).parents('.result-item-li').find('.summary-content-short').show();
    let editor_id = $obj.parents('.summary-editor').find('textarea').attr('id')
    CKEDITOR.instances[editor_id].destroy();
    $(e.target).parents('.summary-editor').remove();
});

function watch_edit_structure_selects_state() {
    if (!structureEditSelectDisablerIsSet && pageType == 'loadMaterials_v2') {
        yl.jQuery('body').delegate('#edit-structure-modal select', 'change', (e) => {
            check_structure_enabled_selects($(e.target).parents('.result-individual-structure-item'));
        });
        structureEditSelectDisablerIsSet = true;
    }
}

if (pageType == 'event_dtrace') {
    yl.jQuery('body').delegate('#edit-structure-modal select', 'change', (e) => {
        check_structure_enabled_selects($(e.target).parents('.result-individual-structure-item'));
    });
}

function check_structure_enabled_selects(wrapper) {
    wrapper = yl.jQuery(wrapper);
    const model_chosen = !!wrapper.find('select[name$=metamodel]').val();
    const competence_chosen = !!wrapper.find('select[name$=competence]').val();
    const level_chosen = !!wrapper.find('select[name$=level]').val();
    wrapper.find('select[name$=competence]').prop('disabled', !model_chosen);
    wrapper.find('select[name$=tools]').prop('disabled', !model_chosen);
    wrapper.find('select[name$=level]').prop('disabled', !(model_chosen && competence_chosen));
    wrapper.find('select[name$=sublevel]').prop('disabled', !(model_chosen && competence_chosen && level_chosen));
}

function clear_draft_id(form) {
    form.find('.ckedit').data('draft-id', '');
    let id = form.find('.ckedit').attr('id');
    if (window.summary_observers[id] !== undefined) {
        window.summary_observers[id].destroy();
        delete window.summary_observers[id];
    }
}

function adjust_upload_type(chosen_tab) {
    let hide_comment = chosen_tab.attr('id') == 'v-pills-summary-tab';
    let comment_div = chosen_tab.parents('.row').find('.materials-form-comment-div');
    hide_comment ? comment_div.hide() : comment_div.show();
    setActivateButton(chosen_tab.parents(formClass))
}

$('.upload-type-btn.active').each((i, el) => {
    adjust_upload_type($(el));
})

function disable_circle_items_btns(wrapper) {
    wrapper.find('.change-circle-items, .cancel-change-circle-items').hide();
    wrapper.find('.start-change-circle-items').show();
    let selected_ids = wrapper.data('selected-circle-items').toString().split(',');
    wrapper.find('.result-circle-items').each((i, el) => {
        $(el).prop('checked', selected_ids.indexOf($(el).val()) != -1);
        $(el).prop('disabled', true);
    });
}

if (pageType == 'loadMaterials') {
    $('body').delegate('form.trace-form select[name=trace_name]', 'change', (e) => {
        setActivateButton($(e.target).parents('form.trace-form'));
    })
}

function open_structure_edit_window(url, labs_result_id, result_id) {
    if (!$('#edit-structure-modal').length) {
        html = `
            <div class="modal fade text-left" role="dialog" id="edit-structure-modal">
              <div class="modal-dialog">
                <div class="modal-content">
                  <div class="modal-body">
                  </div>
                  <div class="modal-footer" style="justify-content: space-between">
                      <button class="btn btn-success btn-save-edited-structure">Сохранить</button>
                      <button data-dismiss="modal" class="btn btn-danger">Закрыть</span>
                  </div>
                </div>
              </div>
            </div>
        `;
        $('body').append($(html));
    }
    const request_data = {
        csrfmiddlewaretoken: csrfmiddlewaretoken,
        action: 'init_structure_edit',
        labs_result_id: labs_result_id,
        result_item_id: result_id
    }
    $.post({
        url: url,
        data: request_data,
        method: 'POST',
        success: (data) => {
            $('#edit-structure-modal').find('.modal-body').html(data.html);
            $('#edit-structure-modal').css('opacity', 0);
            $('#edit-structure-modal').data('url', url).data('result_id', result_id).modal('show');
        }
    })
}

function build_move_result_modal(result, labs_result_id, url='', type='') {
    if ($('#move_results_modal').length == 0) {
        let modal = `
            <div id="move_results_modal" class="modal fade" role="dialog" style="max-width: 100vw;">
              <div class="modal-dialog">
                <div class="modal-content">
                  <div class="modal-header">
                    <button type="button" class="close filter-modal-dismiss" data-dismiss="modal"
                          aria-label="Закрыть"><span aria-hidden="true">&times;</span></button>
                  </div>
                  <div class="modal-body">
                    <div class="modal-move-choices"></div>
                    <div>
                        <button class="btn btn-success" id="btn-move-selected-result">Переместить</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
        `;
        $('body').append($(modal));
    }
    $('#move_results_modal').data('request-url', url);
    let items = '';
    let cnt = 0;
    let label;
    let result_type;
    for (let i = 0; i < blocks_structure.length; i++) {
        let block = blocks_structure[i];
        let block_items = '';
        for (let j = 0; j < block.results.length; j++) {
            let res = block.results[j];
            if (res.deleted || block.deleted)
                continue;
            if (labs_result_id && res.id == labs_result_id)
                block_items += `
                    <li><input type="radio" name="move-result-radiobox" value="${res.id}" id="move_item_${cnt}" disabled="disabled">
                    <label for="move_item_${cnt}">${block.title}, ${res.title} (текущий)</label></li>
                `;
            else if (pageType != 'event_dtrace' || (type == 'user' && res['is_personal'] || type == 'team' && res['is_group']))
                block_items += `
                    <li><input type="radio" name="move-result-radiobox" value="${res.id}" id="move_item_${cnt}">
                    <label for="move_item_${cnt}">${block.title}, ${res.title}</label></li>
                `;
            cnt++;
        }
        if (block_items != '')
         items += block_items;
    }
    $('#move_results_modal .modal-move-choices').empty().append($(`<ul class="no-bullets">${items}</ul>`));
    if (labs_result_id)
        $('#btn-move-selected-result').data('labs_result_id', labs_result_id).data('user_result', $(result).data('result-id')).data('mv-type', "result").data('result-type', type);
    else
        $('#btn-move-selected-result').data('labs_result_id', labs_result_id).data('material_id', $(result).data('file-id')).data('mv-type', "file");
    $('#move_results_modal').modal('show');
    check_move_material_btn_availability();
}

$('body').delegate(maxSizeSelector, 'change', (e) => {
    if (window.FileReader && e.target.files && e.target.files[0] && e.target.files[0].size > maxSize * 1024 * 1024) {
        $(e.target).val('');
        alert("Максимальный размер файла не должен превышать " + maxSize + "Мб");
    }
}).delegate('[name=move-result-radiobox]', 'change', check_move_material_btn_availability);

function check_move_material_btn_availability() {
    $('#btn-move-selected-result').prop('disabled', $('[name=move-result-radiobox]:checked').length == 0);
}

$('body').delegate('input[name=file_field]', 'change', (e) => {

    const $obj = $(e.target);

    let $button = null;
    let parentSelector = null;
    
    if (pageType == 'loadMaterials' || pageType == 'eventStructure') {
        $button = $obj.parents('form.trace-form');
        parentSelector = 'div.tab-content';
    }
    else if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace') {
        $button = $obj.parents('div.material-result-div').find('form.user-materials-form');
        parentSelector = 'form';
    } else if (pageType == 'loadUserMaterials') {
        $button = $('#result_form');
        parentSelector = 'div';
    }

    setActivateButton($button);
    
    if ($obj && $obj[0].files.length != 0) {
        let filesName = 'Файл(ы) для загрузки: <br />';
        for (file of $obj[0].files) {
            filesName += `${file.name} <br>`;
        }
        $obj.parents(parentSelector).find('span.file-name').html(filesName);
    }

});

if (pageType == 'event_dtrace') {
    yl.jQuery('select.user-or-team-autocomplete-selector').on('change', (e) => {
        let form = $(e.target).parents('form.user-materials-form')
        form.length ? setActivateButton(form) : null;
    })
}

$('body').delegate('input[name=url_field]', 'keyup change', (e) => {
    if (pageType == 'loadMaterials') {
        setActivateButton($(e.target).parents('form.trace-form'));
    }
    else if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace') {
        setActivateButton($(e.target).parents('form.user-materials-form'));
    } else if (pageType == 'loadUserMaterials') {
        setActivateButton($('#result_form'));
    }
});

$(window).bind('beforeunload', () => {
    if (uploads.length != 0) {
        return 'не все загрузки завершены';
    }
});

// result-file-upload

function doFileSubmit(form, resultId) {
    formSubmitHadler(form[0], resultId);
}

function makeAnchorText(data, l) {
    return `${l} - ${data.result_type_display} - ${data.rating_display} - <a href="#result-entry-${l}">подробнее</a>`;
}

function setAutocompleteChoice(select, val, text) {
    const $select = $(select);
    $select.data("suppressChange", true);

    select.find("option").remove();
    const $option = $("<option></option>").val(val).text(text);
    
    $select.append($option);
    $select.val(val).trigger('change');
    $select.data("suppressChange", false);
}

function clearAutocompleteChoice(select) {
    const $select = $(select);
    $select.data("suppressChange", true);
    select.find("option").remove();
    $select.val(null).trigger('change');
    $select.data("suppressChange", false);
}

function clearForm($form) {
    const names = ['result_id', 'competences', 'result_comment'];
    for (name of names) {
        $form.find(`[name="${name}"]`).val('');
    }
    clearAutocompleteChoice($form.find('[name="result_type"]'));
    $form.find('[name="rating"] option:selected').prop('selected', false);
    if (formsetRenderUrl) {
        $form.find('[name="group_dynamics"]').val('');
        $('.user-roles-div select option:selected').prop('selected', false);
    }
}

function makeResultAnnotation(data) {
    const groupDynamics = formsetRenderUrl ? `<p class="text-muted">Групповая динамика: ${data.group_dynamics}</p>` : '';
    return `
        <div class="col-lg-10">
            <p class="text-muted">Тип: ${data.result_type_display}. Оценка: ${data.rating_display}</p>
            <p class="text-muted">Компетенции: ${data.competences}</p>
            ${groupDynamics}
            <p class="text-muted">Комментарий: ${data.result_comment}</p>
        </div>
        <div class="col-lg-2">
            <button class="btn btn-danger edit-result">Отредактировать</button>
        </div>
    `;
}

function resultFormHandler(e) {
    const $form = $(e.target);
    if (isFormValid($form)) {
        const data = $form.serialize();
        $('.save-result-btn').prop('disabled', true);
        $.ajax({
            url: get_requestUrl($form),
            method: 'POST',
            data: data,
            success: function(data) {
                if (data['created']) {
                    const l = $('.result-entry').length + 1;
                    const wrapper = $(`<div class="result-wrapper-div" data-result="${data.id}"></div>`);
                    const newAnchor = $(`<p class="result-anchor-text" data-result="${data.id}">${makeAnchorText(data, l)}</p>`);
                    $('#results-jumper').append(newAnchor);
                    const header = $(`<h5 class="result-entry" id="result-entry-${l}">Результат ${l}</h5>`);
                    var part1 = `
                        '<div class="row result-annotation">${makeResultAnnotation(data)}</div>
                    `;
                    const part2 = `
                        <div data-result="${data.id}">
                            <ul class="list-group list-group-flush"></ul>
                        </div>
                    `;
                    wrapper.append(header).append(part1).append(part2);
                    wrapper.find('.result-annotation .col-lg-2 button').data('result', data);
                    $('#results').append(wrapper);
                    $form.find('input[name=result_id]').val(data.id);
                    $('#no-loaded-results').remove();
                } else {
                    const $div = $(`.result-wrapper-div[data-result="${data.id}"]`);
                    if ($div.length) {
                        $div.find('.result-annotation').html(makeResultAnnotation(data));
                        $div.find('.col-lg-2 button').data('result', data);
                    }
                    const $p = $(`.result-anchor-text[data-result="${data.id}"]`);
                    if ($p.length) {
                        const l = $('.result-anchor-text').index($p) + 1;
                        $p.html(makeAnchorText(data, l));
                    }
                }
                const files = $form.find('input[name=file_field]')[0].files;
                const filesLength = files ? files.length : 0;
                if (filesLength > 0 || $form.find('input[name=url_field]').val()) {
                    doFileSubmit($form, data.id);
                } else {
                    $('.save-result-btn').prop('disabled', false);
                    clearForm($form);
                }
            },
            error: (xhr, err, a) => {
                // TODO show appropriate message
                alert(get_error_msg(xhr));
                $('.save-result-btn').prop('disabled', false);
            }
        });
    }
}

// ajax 

function successProcessFile(data, $form, result_item_id) {
    const url = data.url;
    const mId = data.material_id;
    const name = data.name;
    const comment = data.comment;
    const page_url = data.result_url;
    const summary = data.summary;
    let items, item;
    if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace') {
        let data_item_id = data['target_item_info']['type'] + '-' + data['target_item_info']['id']
        let labs_result_id = $($form).parents('.material-result-div').data('result');
        if (pageType == 'event_dtrace' && $form.parents('.material-result-div').find('.item-result-wrapper[data-id="' + data_item_id + '"]').length == 0) {
            let item_info_html = '';
            if  (data['target_item_info']['type'] == 'user') {
                item_info_html = `
                <div>
                    <img class="user-img" src="${data['target_item_info']['image'] && data['target_item_info']['image']['Small'] || DEFAULT_USER_IMAGE}" />
                    <strong>${data['target_item_info']['name']}</strong>
                </div>
                `;
            }
            else {
                let users = data['target_item_info']['users'];
                users_html = '';
                for (let i = 0; i < users.length; i++) {
                    users_html += `
                        <div class="inline-user-item">
                            <img class="user-img ${users[i]['enrolled'] ? '': 'opacity-50'}" src="${users[i]['image'] && users[i]['image']['Small'] || DEFAULT_USER_IMAGE}" />
                            <strong class="${users[i]['enrolled']? '' : 'color-grey'}">${users[i]['name']}</strong>
                        </div>
                    `;
                }
                item_info_html = `
                    <div>
                        <div class="inline-user-item"><strong>Группа "${data['target_item_info']['name']}"</strong></div>
                        ${users_html}
                    </div>
                `;
            }
            item_wrapper_html = `
                <div class="item-result-wrapper" data-id="${data_item_id}">
                    ${item_info_html}
                    <ul class="list-group list-group-flush"></ul>
                </div>
            `;
            $($form).parents('.material-result-div').find('.result-items-wrapper').append($(item_wrapper_html));
        }
        if (!$form.parents('div.material-result-div').find('.result-materials-wrapper[data-result-id="' + result_item_id + '"]').length) {

            if (isAssistant) {
                additional_btns = `<span class="glyphicon glyphicon-move result-action-buttons pull-right move-deleted-result" title="Переместить результат"></span>`;
                approve_block = `
                    <div class="clearfix"></div>
                    <div class="approve-result-block">
                        <div class="pull-right">
                            <div class="approve-input-container">
                                <input type="radio" class="approve-radio-btn" name="approved-${result_item_id}" id="${result_item_id}-approved-true" value="true">
                                <label for="${result_item_id}-approved-true">Валидный</label>
                            </div>
                            <div class="approve-input-container">
                                <input type="radio" class="approve-radio-btn" name="approved-${result_item_id}" id="${result_item_id}-approved-false" value="false">
                                <label for="${result_item_id}-approved-false">Невалидный</label>
                            </div>
                        </div>
                        <div class="clearfix"></div>
                        <div class="approve-text pull-right">
                            <p class="current-approve-text text-muted"></p>
                        </div>
                        <div class="clearfix"></div>
                        <div class="approve-text-edit" style="display: none;" data-approved="None">
                            <input type="text" maxlength="255" class="approve-text-edit-input" placeholder="Комментарий (опционально)">
                            <div class="clearfix"></div>
                            <button class="btn btn-success do-approve-result pull-left" data-labs-result-id="${labs_result_id}" data-result-id="${result_item_id}">Сохранить</button>
                            <button class="btn btn-danger cancel-approve-btn pull-right">Отменить</button>
                        </div>
                    </div>
                `;
            }
            else {
                additional_btns = '';
                approve_block = ``;
            }
            let circle_items_div = ``;
            if (data['circle_items'].length) {
                    let ids = [];
                    let checkboxes = ``;
                    for (let i = 0; i < data['circle_items'].length; i++) {
                        let cid = data['circle_items'][i]['id'];
                        let title = data['circle_items'][i]['tool'];
                        ids.push(cid);
                        let checked = data['selected_circle_items'].indexOf(cid) != -1 ? `checked="checked"` : ``;
                        checkboxes += `
                            <div class="form-check">
                                <input type="checkbox" class="result-circle-items" value="${cid}" id="circle_item_${cid}_${result_item_id}" data-can-edit="true" ${checked} disabled>
                                <label class="result-circle-items-label" for="circle_item_${cid}_${result_item_id}">${title}</label>
                            </div>
                        `;
                    }
                    let selected_ids = data['selected_circle_items'].join(',');
                circle_items_div = `
                    <div class="row result-selected-circle-items-div" data-selected-circle-items="${selected_ids}">
                        ${checkboxes}
                        <span class="start-change-circle-items">Изменить</span>
                        <span class="change-circle-items" data-labs-result-id="${labs_result_id}" data-result-id="${result_item_id}">Сохранить</span>
                        <span class="cancel-change-circle-items">Отменить</span>
                    </div>
                `;
            }
            let html_wrapper = `
                <li class="list-group-item no-left-padding result-item-li">
                    <div class="row">
                        <div class="col-md-9">
                            <ul class="no-bullets result-materials-wrapper no-left-padding" data-result-id="${result_item_id}" data-result-type="${data['target_item_info']['type']}">
                            </ul>
                            <p class="result-comment"></p>
                        </div>
                        <div class="col-md-3">
                            <div class="result-helper-block">
                                <span class="glyphicon glyphicon-remove result-action-buttons pull-right delete-all-files" title="Удалить результат"></span>
                                ${summary ?
                                `<span class="glyphicon glyphicon-pencil result-action-buttons pull-right edit-summary" data-file-id="${data['target_item_info']['material_id']}" data-type="${data['target_item_info']['type']}" title="Редактировать конспект"></span>`
                                :
                                `<span class="glyphicon glyphicon-pencil result-action-buttons pull-right edit-result-comment" title="Добавить/редактировать комментарий"></span>`
                                }
                                ${isAssistant ? `<span class="glyphicon glyphicon-tags result-action-buttons pull-right edit-result-structure" title="Редактировать структуру результата"></span>` : ``}
                                <span data-url="${page_url}" class="glyphicon glyphicon-eye-open result-action-buttons pull-right view-result-page" title="Перейти на страницу результата"></span>
                                ${additional_btns}
                            </div>
                            ${approve_block}
                        </div>
                    </div>
                    ${circle_items_div}
                </li>
            `;
            if (pageType == 'event_dtrace') {
                $form.parents('.material-result-div')
                .find('.item-result-wrapper[data-id="' + data_item_id + '"]')
                .find('ul.list-group').prepend($(html_wrapper));
            }
            else {
                $form.parents('div.material-result-div').find('ul.list-group').prepend($(html_wrapper));
            }
        }
        if (pageType == 'event_dtrace') {
            item = $form.parents('.material-result-div')
            .find('.item-result-wrapper[data-id="' + data_item_id + '"]')
            .find('ul.list-group').find('.result-materials-wrapper[data-result-id="' + result_item_id + '"]');
        }
        else {
            item = $form.parents('div.material-result-div').find('.result-materials-wrapper[data-result-id="' + result_item_id + '"]');
        }
    }
    else {
        items = $('.event-trace-materials-wrapper[data-trace-id=' + data.trace_id + ']').find('ul.list-group');
    }
    const data_attrs = data.data_attrs;
    let html = null;
    if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace') {
        html = `
            <li>
                ${summary ?
                `<p class="summary-content-short"><strong>Конспект:</strong> ${summary}</p>`
                :
                `<a class="link_preview" href="${url}" ${data_attrs}>${name}</a>&nbsp;`}
                ${summary ? `` :
                `<button name="material_id" value="${mId}" class="btn-transparent delete-material-btn pull-right">
                    <span class="glyphicon glyphicon-remove"></span>
                </button>`
                }
            </li>
        `
    }
    else if (data.can_set_public) {
        // TODO remove &nbsp;
        html = `
            <li class="list-group-item">
                <a href="${url}">${name}</a>
                &nbsp;
                <label>
                    Публичный
                    <input type="checkbox" data-link-id="${mId}" class="upload_is_public" ${data.is_public ? 'checked' : ''}>
                </label>
                &nbsp;
                <button name="material_id" value="${mId}" class="btn btn-warning btn-sm pull-right delete-material-btn">
                    Удалить
                </button>
            </li>
            <div>
                <span>${comment}</span>
            </div>
        `;
    } else {
        if (pageType == 'eventStructure') {
            html = `
                <li class="list-group-item ${data.uploader_name && isAssistant ? 'assistant-team-link' : ''}">
                    <a href="${url}">${name}</a>
                    &nbsp;
                    <button name="material_id" value="${mId}" class="btn btn-warning btn-sm pull-right delete-material-btn">
                        Удалить
                    </button>
                    &nbsp;
                    ${data.uploader_name ? '<div>(' + data.uploader_name + ')</div>' : ''}
                    <div>
                        <span class="text-muted assistant-info-string">${data.info_string}</span>
                    </div>
                </li>
            `;
        } else {
            let edit_btn = ``;
            if (isAssistant || summary) {
                edit_btn = `
                    <span value="${mId}" ${summary ? `data-is-summary="true" data-can-edit="true" data-type="event" data-file-id="${data['material_id']}"` : ``} class="glyphicon glyphicon-pencil result-action-buttons pull-right edit-event-block-material">
                    </span>`
            }
            html = `
                <li class="list-group-item ${data.uploader_name ? 'assistant-team-link' : ''}" data-comment="${data.comment}" data-material-id="${mId}">
                    <div class="row">
                        <div class="col-sm-10">
                            ${summary ?
                            `<p class="summary-content-short"><strong>Конспект:</strong> ${summary}</p>`
                            :
                            `<a class="link_preview" href="${url}" ${data_attrs}>${name}</a>`
                            }
                        </div>
                        <div class="col-sm-2">
                            <span name="material_id" value="${mId}" class="glyphicon glyphicon-remove result-action-buttons pull-right delete-material-btn">
                            </span>
                            ${edit_btn}
                        </div>
                    </div>
                    <div>
                        <span class="text-muted assistant-info-string">${data.info_string}</span>
                    </div>
                    <div class="info-string-edit"></div>
                </li>
            `;
        }
    }
    if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace') {
        item.prepend($(html));
        item.parent('div').find('.result-comment').html(comment);
        resultFilesNumberHandler(item.parents('div.result-items-wrapper'));
    }
    else {
        items.append($(html));
        show_trace_name(data.trace_id);
    }
    if (pageType == 'loadUserMaterials') {
        $('.save-result-btn').prop('disabled', false);
        clearForm($form); 
    }
    apply_preview_icons();
    if (pageType == 'event_dtrace' || pageType == 'loadMaterials_v2') {
        if (!$form.find('.uploads').html().trim()) {
            success_html = `
                <div class="notification-wrapper bg-info">
                    <span class="close-notification pull-right">×</span>
                    Результат сохранен. Посмотреть его можно <a href="${page_url}">тут</a>
                </div>
            `;
            $form.append($(success_html));
        }
    }
}

function xhrProcessFile(num) {
    const xhr = new window.XMLHttpRequest();
    if (num > -1) {
        xhr.upload.addEventListener("progress", (e) => {
            if (e.lengthComputable) {
                const percentComplete = parseInt((e.loaded / e.total) * 100);
                $(`div.upload-row[data-row-number="${num}"]`).find('.progress-bar').css('width', percentComplete + '%');
            }
        }, false);
    }  
    return xhr;
}

function completeProcessFile(num, $form = null) {
    if (num > -1) {
        $(`div.upload-row[data-row-number="${num}"]`).remove();
        const index = uploads.indexOf(num);
        if (index > -1) {
            uploads.splice(index, 1);
        }
        if (pageType == 'loadUserMaterials') {
            if (uploads.length == 0) {
                $('.save-result-btn').prop('disabled', false);
                clearForm($form);
            }
        }
        if (uploads.length == 0)
            setActivateButton($form);
    }  
}

function errorProcessFile(xhr, err) {
    // TODO show appropriate message
    alert(get_error_msg(xhr));
}

function processUrl(form, result_item_id, type=UPLOAD_TYPE_URL) {
    const $form = $(form);
    const formData = new FormData($(form).get(0));
    formData.append('add_btn', '');
    formData.delete('file_field');
    formData.delete(type == UPLOAD_TYPE_URL ? 'summary' : 'url_field');
    if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace')
        formData.append('result_item_id', result_item_id);
    if (pageType == 'loadMaterials' && type == UPLOAD_TYPE_SUMMARY) {
        let text_field = $form.find('.ckedit');
        formData.delete('summary');
        formData.append('summary', CKEDITOR.instances[text_field.attr('id')].getData());
    }
    requestUrl = get_requestUrl(form);
    $.ajax({
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        url: requestUrl,
        success: (data) => {
            successProcessFile(data, $form, result_item_id);
            clearFileForm($form);
            setActivateButton($form);
        },
        error: errorProcessFile
    })
}

// file-upload

function get_requestUrl(form) {
    if (pageType == 'event_dtrace') {
        if (!$(form).find('select.user-or-team-autocomplete-selector').length) {
            return userUploadPattern.replace('{REPLACE}', UNTI_ID);
        }
        let val = $(form).find('select.user-or-team-autocomplete-selector').val();
        if (val) {
            let pattern = '';
            switch (val.split('-')[0]) {
                case userContentId:
                    pattern = userUploadPattern;
                    break;
                case teamContentId:
                    pattern = teamUploadPattern;
                    break;
            }
            return pattern.replace('{REPLACE}', val.split('-')[1]);
        }
        return ''
    }
    return form.attr('action') || ''
}

function processFile(form, file, filesLength, result_item_id) {
    const $form = $(form);
    const formData = new FormData($(form).get(0));
    formData.delete('url_field');
    formData.delete('summary');
    if (filesLength) {
        formData.delete('file_field');
        formData.append('file_field', file, file.name);
    }
    formData.append('add_btn', '');
    if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace')
        formData.append('result_item_id', result_item_id);
    const num = filesLength ? addUploadProgress($form, file) : null;
    requestUrl = get_requestUrl(form);
    $.ajax({
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        url: requestUrl,
        xhr: () => {
            // xhrProcessFile(num);
            const xhr = new window.XMLHttpRequest();
            if (num > -1) {
                xhr.upload.addEventListener("progress", (e) => {
                    if (e.lengthComputable) {
                        const percentComplete = parseInt((e.loaded / e.total) * 100);
                        $(`div.upload-row[data-row-number="${num}"]`).find('.progress-bar').css('width', percentComplete + '%');
                    }
                }, false);
            }  
            return xhr;            
        },
        success: (data) => {
            completeProcessFile(num, $form);
            successProcessFile(data, $form, result_item_id);
        },
        error: (xhr, err) => {
            errorProcessFile(xhr, err);
            completeProcessFile(num, $form);
        }
    })
}

function get_form_upload_type(form) {
    switch (form.find('.upload-type-btn.active').attr('id')) {
        case 'v-pills-home-tab':
            return UPLOAD_TYPE_FILE;
        case 'v-pills-profile-tab':
            return UPLOAD_TYPE_URL;
        case 'v-pills-summary-tab':
            return UPLOAD_TYPE_SUMMARY;
    }
}

function formSubmitHadler(form, resultId = null) {
    const $form = $(form);
    if (!isFormValid($form)) {
        setActivateButton($form);
        return false;
    }
    if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace')
        $form.find('.add-material-btn').prop('disabled', true);
    if (isFormValid($form)) {
        if (pageType == 'loadMaterials_v2' || pageType == 'event_dtrace') {
        let tools = [];
        $form.parents('.material-result-div').find('.upload-circle-items-wrapper .result-circle-items:checked').each((i, e) => { tools.push($(e).val()) });
            let data = {
                csrfmiddlewaretoken: csrfmiddlewaretoken,
                action: 'init_result',
                labs_result_id: $form.find('[name=labs_result_id]').val(),
                circle_items: tools.join(','),
                comment: $form.find('[name=comment]').val()
            };
            $.ajax({
                method: 'POST',
                data: data,
                url: get_requestUrl($form),
                success: function(data) {
                    formSubmitHandler_inner($form, resultId, data.result_id);
                },
                error: function(xhr, err) { alert(get_error_msg(xhr)); }
            })
        }
        else {
            formSubmitHandler_inner($form, resultId);
        }
    };
}

function formSubmitHandler_inner($form, resultId=null, result_item_id=null) {
    const fileField = $form.find('input[name=file_field]');
    const upload_type = get_form_upload_type($form);
    if (upload_type == UPLOAD_TYPE_FILE && fileField && fileField[0].files.length) {
        const filesLength = fileField[0].files ? fileField[0].files.length : 0;
        if (!((uploads.length + filesLength) > maxParallelUploads && filesLength)) {
            for (file of fileField[0].files) {
                processFile($form, file, filesLength, result_item_id);
            }
            clearFileForm($form);
        } else {
            alert(`Максимальное количество одновременно загружаемых файлов не может превышать ${maxParallelUploads}`);
        }
    }
    else if (upload_type == UPLOAD_TYPE_URL && $form.find('input[name=url_field]').val()) {
        processUrl($form, result_item_id);
    }
    else if (upload_type == UPLOAD_TYPE_SUMMARY) {
        processUrl($form, result_item_id, UPLOAD_TYPE_SUMMARY);
    }
}

function resultFilesNumberHandler(item) {
    // меняет надпись на кнопке загрузки в соответствии с тем, есть ли для результата загруженные файлы,
    // удаляет результат, если был удален его последний файл
    if (pageType == 'loadMaterials_v2') {
        let results_li = item.find('li.result-item-li');
        for (li of results_li) {
            if ($(li).find('ul.result-materials-wrapper li').length == 0)
                $(li).remove();
        }
        if (item.find('li.result-item-li').length) {
            item.parents('.material-result-div').find('.load-results-btn').text('Загрузить еще один результат');
        }
        else {
            item.parents('.material-result-div').find('.load-results-btn').text('Загрузить');
        }
    }
}
