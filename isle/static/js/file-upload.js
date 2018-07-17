$(document).ready(function() {
    var forms = $('form.trace-form');
    for (var i = 0; i < forms.length; i++){
        $(forms[i]).areYouSure();
    }

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

    forms.submit(function(e) {
        e.preventDefault();
        var form = $(e.target);
        if (!form_valid(form)) return;
        var files_len = form.find('input[name=file_field]')[0].files;
        files_len = files_len ? files_len.length : 0;
        if ((UPLOADS.length + files_len) > MAX_PARALLEL_UPLOADS && files_len) {
            alert('Максимальное количество одновременно загружаемых файлов не может превышать ' + MAX_PARALLEL_UPLOADS);
            return;
        };

        file_field = form.find('input[name=file_field]')[0].files;
        var self = this;
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

                activate_btn(form);

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
                        var items = form.children('ul.list-group').children('li');
                        var item = $(items[items.length - 1]);
                        var s;
                        if (data.can_set_public) {
                            s = '<li class="list-group-item"><a href="' + url + '">' + name + '</a>&nbsp;<span>' + comment + '</span>' +
                                '<label>Публичный<input type="checkbox" data-link-id="' + m_id + '" class="upload_is_public"  ' + (data.is_public ? 'checked' : '') + '></label>' +
                                '&nbsp;<button name="material_id" value="' + m_id + '" class="btn btn-warning btn-sm pull-right delete-material-btn">Удалить</button></li>';
                        }
                        else {
                            s = '<li class="list-group-item"><a href="' + url + '">' + name + '</a>&nbsp;<span>' + comment + '</span>&nbsp;<button name="material_id" value="' + m_id + '" class="btn btn-warning btn-sm pull-right delete-material-btn">Удалить</button></li>';
                        }
                        item.before($(s));
                    },
                    complete: function () {
                        if (num === undefined) return;
                        $('div.upload-row[data-row-number="' + num + '"]').remove();
                        var index = UPLOADS.indexOf(num);
                        if (index > -1) {
                            UPLOADS.splice(index, 1);
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

    });

    $('body').delegate('button.delete-material-btn', 'click', function(e) {

        e.preventDefault();
        if ($(':focus').attr('name') != 'material_id') return;
        var c = confirm('Вы действительно хотите удалить этот файл?');
        if (!c) return;
        var btn = $(this);
        var form = btn.parents('form.trace-form');
        var data = {
            trace_name: form.children('input[name=trace_name]').val(),
            csrfmiddlewaretoken: form.children('input[name=csrfmiddlewaretoken]').val(),
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

    $('body').delegate('form.trace-form input[type=file]', 'change', function(e) {
        if (window.FileReader && this.files && this.files[0] && this.files[0].size > MAX_SIZE * 1024 * 1024) {
            $(this).val('');
            alert("Максимальный размер файла не должен превышать " + MAX_SIZE + "Мб");
        }
    });

    $('body').delegate('input[name=url_field]', 'keyup change', function(e) {
        activate_btn($(this).parents('form.trace-form'));
    });
    $('body').delegate('input[name=file_field]', 'change', function(e) {
        activate_btn($(this).parents('form.trace-form'));

        if ($(this)[0].files.length != 0){
          var files_name = 'Файл(ы) для загрузки: <br />';
            for (var i = 0; i < $(this)[0].files.length; i++){
                files_name += $(this)[0].files[i].name + " <br />";
            }
            $(this).parents('li').find('span.file-name').html(files_name);
      }

    });
    $('body').delegate('input.upload_is_public', 'change', function(e) {
        var is_public = this.checked;
        var token = $(this).parents('form.trace-form').find('input[name=csrfmiddlewaretoken]').val();
        var trace_id = $(this).data('link-id');
        var self = this;
        $.ajax({
            url: CHANGE_STATE,
            method: 'POST',
            data: {csrfmiddlewaretoken: token, trace_id: trace_id, is_public: is_public},
            error: function () {
                self.checked = !is_public;
            }
        })
    });

    function form_valid(form) {
        var url_field = form.find('input[name=url_field]');
        var file_field = form.find('input[name=file_field]');
        var url_filled = !!url_field.first().val();
        var file_filled = !!(file_field && !!file_field.val());
        return url_filled != file_filled;
    }

    function activate_btn(form) {
        if (form_valid(form)) {
            form.find('.add-material-btn').removeAttr('disabled').prop('disabled', false);
        }
        else {
            form.find('.add-material-btn').attr('disabled', 'disabled').prop('disabled', true);
        }
    }

    $(window).bind('beforeunload', function() {
        if (UPLOADS.length != 0) {
            return 'не все загрузки завершены'
        }
    })
});
