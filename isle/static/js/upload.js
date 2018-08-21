const counter = 0;
const uploads = [];

let maxSizeSelector = null;

if (pageType == 'loadMaterials') {
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
        clearForm();
        const $form = $('#result_form');
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
                error: () => {
                    // TODO show appropriate message
                    alert('error');
                }
            })
        }
    });
}

function addUploadProgress(form, fileField) {
    const name = fileField.name;
    const num = counter++;
    const html = `
        <div class="row upload-row" data-row-number="${num}">
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
    form.find('div.uploads').append(html);
    uploads.push(num);
    return num;
}

function isFormValid(form) {
    const urlField = form.find('input[name=url_field]');
    const fileField = form.find('input[name=file_field]');
    const urlFilled = !!urlField.first().val();
    const fileFilled = !!(fileField && !!fileField.val());

    return !(urlFilled && fileFilled);
}

function setActivateButton(form) {
    let selector = null;
    if (pageType == 'loadMaterials') {
        selector = '.add-material-btn';
    } else if (pageType == 'loadUserMaterials') {
        selector = '.save-result-btn';
    }
    if (isFormValid(form)) {
        form.find(selector).prop('disabled', false);
    }
    else {
        form.find(selector).prop('disabled', true);
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

// handlers

$('body').delegate('button.delete-material-btn', 'click', (e) => {
    e.preventDefault();
    if ($(':focus').attr('name') == 'material_id') {
        if (confirm('Вы действительно хотите удалить этот файл?')) {
            const $obj = $(e.target);
            const data = {
                csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
                trace_name: $obj.parents('form.trace-form').children('input[name=trace_name]').val(),
                material_id: $obj.val()
            }
            $.ajax({
                type: 'POST',
                data: data,
                success: (data) => {
                    $obj.parent('li').remove();
                },
                error: (xhr, err) => {
                    // TODO show appropriate message
                    alert('error');
                }
            })
        }
    }
});

$('body').delegate(maxSizeSelector, 'change', (e) => {
    if (window.FileReader && e.target.files && e.target.files[0] && e.target.files[0].size > maxSize * 1024 * 1024) {
        $(e.target).val('');
        alert("Максимальный размер файла не должен превышать " + maxSize + "Мб");
    }
});

$('body').delegate('input[name=file_field]', 'change', (e) => {

    const $obj = $(e.target);

    let $button = null;
    let parentSelector = null;
    
    if (pageType == 'loadMaterials') {
        $button = $obj.parents('form.trace-form');
        parentSelector = 'li';
    } else if (pageType == 'loadUserMaterials') {
        $button = $('#result_form');
        parentSelector = 'div';
    }

    setActivateButton($button);
    
    if ($obj && $obj[0].files.length != 0) {
        let filesName = 'Файл(ы) для загрузки: <br />';
        for (file of $obj[0].files) {
            filesName += `${file.name} <br /`;
        }
        $obj.parents(parentSelector).find('span.file-name').html(filesName);
    }

});

$('body').delegate('input[name=url_field]', 'keyup change', (e) => {
    if (pageType == 'loadMaterials') {
        setActivateButton($(e.target).parents('form.trace-form'));
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

function clearForm() {
    const $form = $('#result_form');
    const names = ['result_id', 'competences', 'result_comment'];
    for (name of names) {
        $form.find(`[name="${name}"]`).val('');
    }
    clearAutocompleteChoice(form.find('[name="result_type"]'));
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
                    wrapper.append(header).append($(part1)).append($(part2));
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
            error: () => {
                // TODO show appropriate message
                alert('error');
                $('.save-result-btn').prop('disabled', false);
            }
        });
    }
}

// ajax 

function successProcessFile(data, form) {
    const url = data.url;
    const mId = data.material_id;
    const name = data.name;
    const comment = data.comment;
    const items = form.children('ul.list-group').children('li');
    const item = $(items[items.length - 1]);
    let html = null;
    if (data.can_set_public) {
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
    }
    else if (!isAssistant) {
        html = `
            <li class="list-group-item">
                <a href="${url}">${name}</a>
                &nbsp;
                <button name="material_id" value="${mId}" class="btn btn-warning btn-sm pull-right delete-material-btn">
                    Удалить
                </button>
                ${data.uploader_name ? '<div>(' + data.uploader_name + ')</div>' : ''}
                <div>
                    <span>${comment}</span>
                </div>
            </li>
        `;
    } else {
        html = `
            <li class="list-group-item ${data.uploader_name && isAssistant ? 'assistant-team-link' : ''}">
                <a href="${url}">${name}</a>
                &nbsp;
                <button name="material_id" value="${mId}" class="btn btn-warning btn-sm pull-right delete-material-btn">
                    Удалить
                </button>
                &nbsp;
                <button value="${mId}" class="btn btn-success btn-sm pull-right edit-event-block-material">
                    Редактировать
                </button>
                ${data.uploader_name ? '<div>(' + data.uploader_name + ')</div>' : ''}
                <div>
                    <span class="text-muted assistant-info-string">${data.info_string}</span>
                </div>
                <div class="info-string-edit"></div>
            </li>
        `;
    }
    item.before($(html));    
    if (page == 'loadUserMaterials') {
        if (!num) {
            $('.save-result-btn').prop('disabled', false);
            clearForm(form); 
        }
    }
}

function xhrProcessFile(num) {
    const xhr = new window.XMLHttpRequest();
    if (num) {
        xhr.upload.addEventListener("progress", (e) => {
            if (e.lengthComputable) {
                const percentComplete = parseInt((e.loaded / e.total) * 100);
                $(`div.upload-row[data-row-number="${num}"]`).find('.progress-bar').css('width', percentComplete + '%');
            }
        }, false);
    }  
    return xhr;
}

function completeProcessFile(form = null) {
    if (num) {
        $(`div.upload-row[data-row-number="${num}"]`).remove();
        const index = uploads.indexOf(num);
        if (index > -1) {
            uploads.splice(index, 1);
        }
        if (page == 'loadUserMaterials') {
            if (uploads.length == 0) {
                $('.save-result-btn').prop('disabled', false);
                clearForm(form);
            }
        }
    }  
}

function errorProcessFile(xhr, err) {
    // TODO show appropriate message
    alert('error');
}

// file-upload

function processFile(form, file, filesLength) {
    const formData = new FormData(form);
    if (filesLength) {
        formData.delete('file_field');
        formData.append('file_field', file, file.name);
    }
    formData.append('add_btn', '');
    const num = filesLength ? addUploadProgress(form, file) : null;
    setActivateButton(form);
    $.ajax({
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        xhr: () => {
            xhrProcessFile(num)
        },
        success: (data) => {
            successProcessFile(data, form);
        },
        complete: () => {
            completeProcessFile(form);
        },
        error: errorProcessFile
    })
}

function formSubmitHadler(form, resultId = null) {
    const $form = $(form);
    if (isFormValid($form)) {
        const fileField = $form.find('input[name=file_field]');
        if (fileField) {
            const filesLength = fileField[0].files ? fileField[0].files.length : 0;
            if (!((uploads.lenght + filesLength) > maxParallelUploads && filesLength)) {
                for (file of fileField[0].files) {
                    processFile(form, file, filesLength);
                }
                clearFileForm($form);
            } else {
                alert(`Максимальное количество одновременно загружаемых файлов не может превышать ${maxParallelUploads}`);
            }
        }
    };
}