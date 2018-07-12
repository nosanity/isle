$(document).ready(function() {
    var forms = $('form.trace-form');
    for (var i = 0; i < forms.length; i++){
        $(forms[i]).areYouSure();
    }

    forms.submit(function(e) {
        e.preventDefault();
        var formData = new FormData(this);
        formData.append('add_btn', '');
        var form = $(e.target);
        if (!form_valid(form)) return;
        var progress_wrapper = form.find('div.progress');
        progress_wrapper.show();
        var progress = progress_wrapper.children('.progress-bar');
        progress.css('width', '0%');
        // имитация "грязного" поля для areYouSure
        form.append('<input name="dirty-input" type="hidden" val="1" data-ays-orig="">');
        form.trigger('checkform.areYouSure');
        $.ajax({
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            xhr: function() {
                var xhr = new window.XMLHttpRequest();

                xhr.upload.addEventListener("progress", function(evt) {
                  if (evt.lengthComputable) {
                    var percentComplete = evt.loaded / evt.total;
                    percentComplete = parseInt(percentComplete * 100);
                    progress.css('width', percentComplete + '%');
                  }
                }, false);

                return xhr;
            },
            success: function(data) {
                var url = data.url;
                var m_id = data.material_id;
                var items = form.children('ul.list-group').children('li');
                var item = $(items[items.length - 1]);
                item.before($('<li class="list-group-item"><a href="' + url + '">' + url + '</a>&nbsp;<button name="material_id" value="' + m_id + '" class="btn btn-warning btn-sm pull-right delete-material-btn">Удалить</button></li>'));
                form.find('input[name=url_field]').val('');
                form.find('input[name=file_field]').val('');
                form.find('input[name=comment]').val('');
                form.find('span.file-name').html('');
                activate_btn(form);
            },
            complete: function() {
                progress_wrapper.hide();
                form.find('input[name=dirty-input]').remove();
                form.trigger('checkform.areYouSure');
            },
            error: function (xhr, err) {alert('error')}
        })
    });

    $('body').delegate('button.delete-material-btn', 'click', function(e) {
        e.preventDefault();
        var c = confirm('Вы действительно хотите удалить этот файл?');
        if (!c) return;
        var btn = $(this);
        if ($(':focus').attr('name') != 'material_id') return;
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
        if ($(this)[0].files[0])
            $(this).parents('li').find('span.file-name').html($(this)[0].files[0].name);
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
});
