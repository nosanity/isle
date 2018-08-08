$(document).ready(function() {

    COUNTER = 0;
    UPLOADS = [];

    function add_upload_progress(form, file_field) {
        var name = file_field.name;
        var num = COUNTER++;
        var div = '<div class="row upload-row" data-row-number="' + num + '">' +
            '<div class="col-lg-3 uploads-name">' +
                '<span class="uploaded-file-name">' + name + '</span>' +
            '</div>' +
            '<div class="col-lg-9 uploads-progress" style="padding-top: 5px">' +
                '<div class="progress">' +
                    '<div class="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100"></div>' +
                '</div></div></div>';
        div = $(div);
        form.find('div.uploads').append(div);
        UPLOADS.push(num);
        return num;
    }

    $('#result_form').submit(function(e) {
        e.preventDefault();
        var form = $(e.target);
        if (!form_valid(form)) return;
        var data = form.serialize();
        $('.save-result-btn').prop('disabled', true);

        $.ajax({
            url: form.attr('action'),
            method: 'POST',
            data: data,
            success: function(data) {
                if (data['created']) {
                    var l = $('.result-entry').length + 1;
                    var wrapper = $('<div class="result-wrapper-div" data-result="' + data.id + '"></div>');
                    var new_anchor = $('<p class="result-anchor-text" data-result="' + data.id + '">' + make_anchor_text(data, l) + '</p>');
                    $('#results-jumper').append(new_anchor);
                    var header = $('<h5 class="result-entry" id="result-entry-' + l + '">Результат ' + l + '</h5>');
                    var s = '' +
                        '<div class="row result-annotation">' + make_result_annotation(data) + '</div>';
                    var s2 = '' +
                        '<div data-result="' + data.id + '">' +
                            '<ul class="list-group list-group-flush"></ul></div>';
                    wrapper.append(header).append($(s)).append($(s2));
                    wrapper.find('.result-annotation .col-lg-2 button').data('result', data);
                    $('#results').append(wrapper);
                    form.find('input[name=result_id]').val(data.id);
                    $('#no-loaded-results').remove();
                }
                else {
                    var div = $('.result-wrapper-div[data-result="' + data.id + '"]');
                    if (div.length) {
                        div.find('.result-annotation').html(make_result_annotation(data));
                        div.find('.col-lg-2 button').data('result', data);
                    }
                    var p = $('.result-anchor-text[data-result="' + data.id + '"]');
                    if (p.length) {
                        var l = $('.result-anchor-text').index(p) + 1;
                        p.html(make_anchor_text(data, l));
                    }
                }
                var files_len = form.find('input[name=file_field]')[0].files;
                files_len = files_len ? files_len.length : 0;
                if (files_len > 0 || form.find('input[name=url_field]').val()) {
                    do_file_submit(form, data.id);
                }
                else {
                    $('.save-result-btn').prop('disabled', false);
                    clear_form(form);
                }
            },
            error: function() {
                alert('error');
                $('.save-result-btn').prop('disabled', false);
            }
        });
        return false;
    });

    function make_result_annotation(data) {
        return '<div class="col-lg-10">' +
            '<p class="text-muted">Тип: ' + data.result_type_display + '. Оценка: ' + data.rating_display + '</p>' +
            '<p class="text-muted">Компетенции: ' + data.competences + '</p>' +
            (FORMSET_RENDER_URL ? ('<p class="text-muted">Групповая динамика: ' + data.group_dynamics + '</p>') : '') +
            '<p class="text-muted">Комментарий: ' + data.result_comment + '</p>' +
        '</div>' +
        '<div class="col-lg-2">' +
            '<button class="btn btn-danger edit-result">Отредактировать</button>' +
        '</div>';
    }

    function make_anchor_text(data, l) {
        return '' + l + ' - ' + data.result_type_display + ' - ' + data.rating_display + ' - <a href="#result-entry-' + l + '">подробнее</a>';
    }

    function do_file_submit(form, result_id) {
        var files_len = form.find('input[name=file_field]')[0].files;
        files_len = files_len ? files_len.length : 0;
        if ((UPLOADS.length + files_len) > MAX_PARALLEL_UPLOADS && files_len) {
            alert('Максимальное количество одновременно загружаемых файлов не может превышать ' + MAX_PARALLEL_UPLOADS);
            return;
        }

        var file_field = form.find('input[name=file_field]')[0].files;
        var self = form[0];
        for (var i = 0; i < (file_field.length ? file_field.length : 1); i++) {

            (function () {
                var formData = new FormData(self);
                if (file_field.length) {
                    formData.delete('file_field');
                    formData.append('file_field', file_field[i], file_field[i].name);
                }
                formData.append('add_btn', '');
                if (file_field.length)
                    var num = add_upload_progress(form, file_field[i]);
                else
                    num = undefined;

                $.ajax({
                    type: 'POST',
                    data: formData,
                    processData: false,
                    contentType: false,
                    xhr: function () {
                        var xhr = new window.XMLHttpRequest();
                        if (num === undefined) return xhr;
                        xhr.upload.addEventListener("progress", function (evt) {
                            if (evt.lengthComputable) {
                                var percentComplete = evt.loaded / evt.total;
                                percentComplete = parseInt(percentComplete * 100);
                                $('div.upload-row[data-row-number="' + num + '"]').find('.progress-bar').css('width', percentComplete + '%');
                            }
                        }, false);
                        return xhr;
                    },
                    success: function (data) {
                        var url = data.url;
                        var m_id = data.material_id;
                        var name = data.name;
                        var comment = data.comment;
                        var items = $('#results .result-wrapper-div div[data-result="' + result_id + '"] ul.list-group');
                        var s;
                        if (data.can_set_public) {
                            s = '<li class="list-group-item"><a href="' + url + '">' + name + '</a>&nbsp; ' +
                                '<label>Публичный<input type="checkbox" data-link-id="' + m_id + '" class="upload_is_public"  ' + (data.is_public ? 'checked' : '') + '></label>' +
                                '&nbsp;<button name="material_id" value="' + m_id + '" class="btn btn-warning btn-sm pull-right delete-material-btn">Удалить</button></li>' +
                                '<div><span>' + comment + '</span></div>';
                        }
                        else {
                            s = '<li class="list-group-item ' + (data.uploader_name && IS_ASSISTANT ? 'assistant-team-link' : '') + '"><a href="' + url + '">' + name + '</a>&nbsp;<button name="material_id" value="' + m_id + '" class="btn btn-warning btn-sm pull-right delete-material-btn">Удалить</button>' +
                                (data.uploader_name ? ('<div>(' + data.uploader_name + ')</div>') : '') +
                                '<div><span>' + comment + '</span></div></li>';
                        }
                        items.append($(s));
                        if (num === undefined) {
                            $('.save-result-btn').prop('disabled', false);
                            clear_form(form);
                        }
                    },
                    complete: function () {
                        if (num === undefined) return;
                        $('div.upload-row[data-row-number="' + num + '"]').remove();
                        var index = UPLOADS.indexOf(num);
                        if (index > -1) {
                            UPLOADS.splice(index, 1);
                        }
                        if (UPLOADS.length == 0) {
                            $('.save-result-btn').prop('disabled', false);
                            clear_form(form);
                        }
                    },
                    error: function (xhr, err) {
                        alert('error')
                    }
                })
            })()
        }
        form.find('span.file-name').html('');
        form.find('input[name=url_field]').val('');
        form.find('input[name=file_field]').val('');
        form.find('input[name=comment]').val('');
        form.find('input[name=is_public]').prop('checked', false);

    }

    $('body').delegate('.edit-result', 'click', function(e) {
        e.preventDefault();
        if (UPLOADS.length > 0) {
            alert('Дождитесь окончания загрузки файлов');
            return
        }
        var data = $(this).data('result');
        clear_form();
        var form = $('#result_form');
        form.find('[name="result_id"]').val(data.id);
        setAutocompleteChoice(form.find('[name="result_type"]'), data.result_type, data.result_type_display);
        form.find('[name="rating"] option[value="' + data.rating + '"]').prop('selected', true);
        form.find('[name="competences"]').val(data.competences);
        form.find('[name="result_comment"]').val(data.result_comment);
        window.scrollTo(0, 0);
        if (FORMSET_RENDER_URL) {
            form.find('[name="group_dynamics"]').val(data.group_dynamics);
            $.ajax({
                url: FORMSET_RENDER_URL,
                method: 'GET',
                data: {id: data.id},
                success: function (data) {
                    $('div.user-roles-div').html(data);
                },
                error: function() {
                    alert('error');
                }
            })
        }
    });

    function setAutocompleteChoice(select, val, text) {
        $(select).data("suppressChange", true);
        select.find("option").remove();
        var option = $("<option></option>").val(val).text(text);
        $(select).append(option);
        $(select).val(val).trigger('change');
        $(select).data("suppressChange", false);
    }

    function clearAutocompleteChoice(select) {
        $(select).data("suppressChange", true);
        select.find("option").remove();
        $(select).val(null).trigger('change');
        $(select).data("suppressChange", false);
    }

    function clear_form() {
        var form = $('#result_form');
        var names = ['result_id', 'competences', 'result_comment'];
        for (var i = 0; i < names.length; i++)
            form.find('[name="' + names[i] + '"]').val('')
        clearAutocompleteChoice(form.find('[name="result_type"]'));
        form.find('[name="rating"] option:selected').prop('selected', false);
        if (FORMSET_RENDER_URL) {
            form.find('[name="group_dynamics"]').val('');
            $('.user-roles-div select option:selected').prop('selected', false);
        }
    }

    $('body').delegate('button.delete-material-btn', 'click', function(e) {

        e.preventDefault();
        if ($(':focus').attr('name') != 'material_id') return;
        var c = confirm('Вы действительно хотите удалить этот файл?');
        if (!c) return;
        var btn = $(this);
        var form = btn.parents('form.trace-form');
        var data = {
            trace_name: form.children('input[name=trace_name]').val(),
            csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val(),
            material_id: btn.val()
        };
        $.ajax({
            type: 'POST',
            data: data,
            success: function(data) {
                btn.parent('li').remove();
            },
            error: function (xhr, err) {alert('error')}
        })
    });

    $('body').delegate('#result_form input[type=file]', 'change', function(e) {
        if (window.FileReader && this.files && this.files[0] && this.files[0].size > MAX_SIZE * 1024 * 1024) {
            $(this).val('');
            alert("Максимальный размер файла не должен превышать " + MAX_SIZE + "Мб");
        }
    });

    $('body').delegate('input[name=url_field]', 'keyup change', function(e) {
        activate_btn($('#result_form'));
    });
    $('body').delegate('input[name=file_field]', 'change', function(e) {
        activate_btn($('#result_form'));

        if ($(this)[0].files.length != 0){
          var files_name = 'Файл(ы) для загрузки: <br />';
            for (var i = 0; i < $(this)[0].files.length; i++){
                files_name += $(this)[0].files[i].name + " <br />";
            }
            $(this).parents('div').find('span.file-name').html(files_name);
      }

    });

    function form_valid(form) {
        var url_field = form.find('input[name=url_field]');
        var file_field = form.find('input[name=file_field]');
        var url_filled = !!url_field.first().val();
        var file_filled = !!(file_field && !!file_field.val());
        return !(url_filled && file_filled);
    }

    function activate_btn(form) {
        if (form_valid(form)) {
            form.find('.save-result-btn').removeAttr('disabled').prop('disabled', false);
        }
        else {
            form.find('.save-result-btn').attr('disabled', 'disabled').prop('disabled', true);
        }
    }

    $(window).bind('beforeunload', function() {
        if (UPLOADS.length != 0) {
            return 'не все загрузки завершены'
        }
    })
});
