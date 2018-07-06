$(document).ready(function() {
    $('form.trace-form').submit(function(e) {
        e.preventDefault();
        var formData = new FormData(this);
        formData.append('add_btn', '');
        var form = $(e.target);
        if (!form_valid(form)) return;
        $.ajax({
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function(data) {
                var url = data.url;
                var m_id = data.material_id;
                var items = form.children('ul.list-group').children('li');
                var item = $(items[items.length - 1]);
                item.before($('<li class="list-group-item"><a href="' + url + '">' + url + '</a>&nbsp;<button name="material_id" value="' + m_id + '" class="btn btn-danger delete-material-btn">Удалить</button></li>'));
                form.find('input[name=url_field]').val('');
                form.find('input[name=file_field]').val('');
                activate_btn(form);
            },
            error: function (xhr, err) {alert('error')}
        })
    });

    $('body').delegate('button.delete-material-btn', 'click', function(e) {
        e.preventDefault();
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
