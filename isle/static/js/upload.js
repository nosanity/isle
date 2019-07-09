let counter = 0;
const uploads = [];

let maxSizeSelector = null;

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
else if (pageType == 'loadMaterials_v2') {
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

function isFormValid($form) {
    const $urlField = $form.find('input[name=url_field]');
    const $fileField = $form.find('input[name=file_field]');
    const urlFilled = !!$urlField.first().val();
    const fileFilled = !!($fileField && !!$fileField.val());

    if (pageType  == 'loadMaterials') {
        return !!$form.find('select[name=trace_name]').val() && !(urlFilled == fileFilled);
    }

    return !(urlFilled == fileFilled);
}

function setActivateButton($form) {
    let selector = null;
    if (pageType == 'loadMaterials' || pageType == 'eventStructure' || pageType == 'loadMaterials_v2') {
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
    try {
        $form.find('[name$=event_block]').val('');
        clearAutocompleteChoice($form.find('[name$=related_users]'));
        clearAutocompleteChoice($form.find('[name$=related_teams]'));
    }
    catch (e) {
        // do nothing
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
            if (pageType == 'loadMaterials_v2') {
                data['labs_result_id'] = $obj.parents('.material-result-div').data('result');
                data['result_item_id'] = $obj.parents('.result-materials-wrapper').data('result-id');
            }
            try {
                requestUrl = fileBlocksUploadUrl;
            }
            catch(e) { requestUrl = ''; }
            $.ajax({
                type: 'POST',
                data: data,
                url: requestUrl,
                success: (data) => {
                    let el = $obj.parents('div.result-items-wrapper');
                    $obj.parent('li').remove();
                    resultFilesNumberHandler(el);
                    if (pageType == 'loadMaterials') {
                        show_trace_name(trace_id);
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
            url: '',
            success: (data) => {
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
    $.ajax({
        type: 'POST',
        data: data,
        url: '',
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
    build_move_result_modal(result, labs_result.data('result'));
}).delegate('#btn-move-selected-result', 'click', (e) => {
    let obj = $(e.target);
    obj.prop('disabled', true).attr('disabled', 'disabled');
    let post_data, result, old_result_wrapper;
    if (obj.data('mv-type') == 'result') {
        post_data = {
            csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
            action: 'move',
            result_item_id: $(e.target).data('user_result'),
            labs_result_id: $(e.target).data('labs_result_id'),
            move_to: $('input[name="move-result-radiobox"]:checked').val()
        };
        result = $('.result-materials-wrapper[data-result-id="' + $(e.target).data('user_result') + '"]').parents('li.result-item-li');
        old_result_wrapper = result.parents('.material-result-div').find('ul.list-group')
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
        url: '',
        success: (data) => {
            if (obj.data('mv-type') == 'result') {
                let destination = data.new_result_id;
                let result_block = $('.material-result-div[data-result="' + destination + '"]').find('ul.list-group');
                result.appendTo(result_block);
                $('#move_results_modal').modal('hide');
                resultFilesNumberHandler(old_result_wrapper);
                resultFilesNumberHandler(result_block);
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
});

if (pageType == 'loadMaterials') {
    $('body').delegate('form.trace-form select[name=trace_name]', 'change', (e) => {
        setActivateButton($(e.target).parents('form.trace-form'));
    })
}

function build_move_result_modal(result, labs_result_id) {
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
    let items = '';
    let cnt = 0;
    let label;
    for (let i = 0; i < blocks_structure.length; i++) {
        let block = blocks_structure[i];
        for (let j = 0; j < block.results.length; j++) {
            let res = block.results[j];
            if (res.deleted || block.deleted)
                continue;
            if (labs_result_id && res.id == labs_result_id)
                items += `
                    <li><input type="radio" name="move-result-radiobox" value="${res.id}" id="move_item_${cnt}" disabled="disabled">
                    <label for="move_item_${cnt}">${block.title}, ${res.title} (текущий)</label></li>
                `;
            else
                items += `
                    <li><input type="radio" name="move-result-radiobox" value="${res.id}" id="move_item_${cnt}">
                    <label for="move_item_${cnt}">${block.title}, ${res.title}</label></li>
                `;
            cnt++;
        }
    }
    $('#move_results_modal .modal-move-choices').empty().append($(`<ul class="no-bullets">${items}</ul>`));
    if (labs_result_id)
        $('#btn-move-selected-result').data('labs_result_id', labs_result_id).data('user_result', $(result).data('result-id')).data('mv-type', "result");
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
    else if (pageType == 'loadMaterials_v2') {
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

$('body').delegate('input[name=url_field]', 'keyup change', (e) => {
    if (pageType == 'loadMaterials') {
        setActivateButton($(e.target).parents('form.trace-form'));
    }
    else if (pageType == 'loadMaterials_v2') {
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
            url: $form.attr('action'),
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
    let items, item;
    if (pageType == 'loadMaterials_v2') {
        if (!$form.parents('div.material-result-div').find('.result-materials-wrapper[data-result-id="' + result_item_id + '"]').length) {

            if (isAssistant)
                additional_btns = `<span class="glyphicon glyphicon-move result-action-buttons pull-right move-deleted-result"></span>`;
            else
                additional_btns = '';
            let html_wrapper = `
                <li class="list-group-item no-left-padding result-item-li">
                    <div class="row">
                        <div class="col-md-9">
                            <ul class="no-bullets result-materials-wrapper no-left-padding" data-result-id="${result_item_id}">
                            </ul>
                            <p class="result-comment"></p>
                        </div>
                        <div class="col-md-3">
                            <div class="result-helper-block">
                                <span class="glyphicon glyphicon-remove result-action-buttons pull-right delete-all-files"></span>
                                <span class="glyphicon glyphicon-pencil result-action-buttons pull-right edit-result-comment"></span>
                                <span data-url="${page_url}" class="glyphicon glyphicon-eye-open result-action-buttons pull-right view-result-page"></span>
                                ${additional_btns}
                            </div>
                        </div>
                    </div>
                </li>
            `;
            $form.parents('div.material-result-div').find('ul.list-group').prepend($(html_wrapper));
        }
        item = $form.parents('div.material-result-div').find('.result-materials-wrapper[data-result-id="' + result_item_id + '"]');
    }
    else {
        items = $('.event-trace-materials-wrapper[data-trace-id=' + data.trace_id + ']').find('ul.list-group');
    }
    const data_attrs = data.data_attrs;
    let html = null;
    if (pageType == 'loadMaterials_v2') {
        html = `
            <li>
                <a class="link_preview" href="${url}" ${data_attrs}>${name}</a>&nbsp;
                <button name="material_id" value="${mId}" class="btn-transparent delete-material-btn pull-right">
                    <span class="glyphicon glyphicon-remove"></span>
                </button>
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
            if (isAssistant) {
                edit_btn = `
                    <span value="${mId}" class="glyphicon glyphicon-pencil result-action-buttons pull-right edit-event-block-material">
                    </span>`
            }
            html = `
                <li class="list-group-item ${data.uploader_name ? 'assistant-team-link' : ''}" data-comment="${data.comment}" data-material-id="${mId}">
                    <a class="link_preview" href="${url}" ${data_attrs}>${name}</a>
                    &nbsp;
                    <span name="material_id" value="${mId}" class="glyphicon glyphicon-remove result-action-buttons pull-right delete-material-btn">
                    </span>
                    ${edit_btn}
                    <div>
                        <span class="text-muted assistant-info-string">${data.info_string}</span>
                    </div>
                    <div class="info-string-edit"></div>
                </li>
            `;
        }
    }
    if (pageType == 'loadMaterials_v2') {
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

function processUrl(form, result_item_id) {
    const $form = $(form);
    const formData = new FormData($(form).get(0));
    formData.append('add_btn', '');
    if (pageType == 'loadMaterials_v2')
        formData.append('result_item_id', result_item_id);
    try {
        requestUrl = fileBlocksUploadUrl;
    }
    catch(e) { requestUrl = ''; }
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

function processFile(form, file, filesLength, result_item_id) {
    const $form = $(form);
    const formData = new FormData($(form).get(0));
    if (filesLength) {
        formData.delete('file_field');
        formData.append('file_field', file, file.name);
    }
    formData.append('add_btn', '');
    if (pageType == 'loadMaterials_v2')
        formData.append('result_item_id', result_item_id);
    const num = filesLength ? addUploadProgress($form, file) : null;
    try {
        requestUrl = fileBlocksUploadUrl;
    }
    catch(e) { requestUrl = ''; }
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
            successProcessFile(data, $form, result_item_id);
        },
        complete: () => {
            completeProcessFile(num, $form);
        },
        error: errorProcessFile
    })
}

function formSubmitHadler(form, resultId = null) {
    const $form = $(form);
    if (!isFormValid($form)) {
        setActivateButton($form);
        return false;
    }
    if (pageType == 'loadMaterials_v2')
        $form.find('.add-material-btn').prop('disabled', true);
    if (isFormValid($form)) {
        if (pageType == 'loadMaterials_v2') {
            let data = {
                csrfmiddlewaretoken: csrfmiddlewaretoken,
                action: 'init_result',
                labs_result_id: $form.find('[name=labs_result_id]').val(),
                comment: $form.find('[name=comment]').val()
            };
            $.ajax({
                method: 'POST',
                data: data,
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
    if (fileField && fileField[0].files.length) {
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
    else {
        processUrl($form, result_item_id);
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
