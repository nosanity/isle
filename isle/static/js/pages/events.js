$('#i-was-here').click(() => { 
    $('.approve-text').removeClass('d-none');
});

$('.hide-text-btn').click(() => {
    $('.approve-text').addClass('d-none');
});

$('.approve-text-btn').click((e) => {
    e.preventDefault();
    approveTextButton();
});

if (isAssistant) {
    $('input.attendance').on('change', (e) => {
        inputAttendanceChange(e.target);
    });

    $('#event-users-table').delegate('.btn-delete-attendance', 'click', (e) => {
        e.preventDefault();
        deleteAttendance(e.target);
    });
}

$('.prepare-csv-export').on('click', (e) => {
    e.preventDefault();
    let obj = $(e.target);
    if (obj[0].tagName == 'SPAN')
        obj = obj.parent('a');
    $('.export-format-selector').show();
});

$('.export-format-selector').on('change', (e) => {
    e.preventDefault();
    var obj = $(e.target);
    if (!obj.val()) return;
    obj.prop('disabled', true);
    var url = $('.prepare-csv-export').attr('href') + '?check_empty=1';
    $.ajax({
        method: 'GET',
        url: url,
        success: (data) => {
            if (data.has_contents)
                window.location = $('.prepare-csv-export').attr('href') + '?format=' + obj.val();
            else
                alert('Ни одного файла или результата не загружено в мероприятие');
        },
        error: () => { alert('Произошла ошибка'); },
        complete: () => {
            obj.prop('disabled', false).hide().val('');
        }
    })
});

$('.delete-team-btn').on('click', (e) => {
    e.preventDefault();
    let target = $(e.target);
    if (confirm('Удалить команду?')) {
        if (target[0].tagName == 'I')
            target = target.parent();
        $.ajax({
            method: 'POST',
            url: target.data('action-url'),
            data: {csrfmiddlewaretoken: csrfmiddlewaretoken},
            success: (data) => {
                try {
                    if (data['status'] === 0) {
                        target.parents('tr').remove();
                    }
                }
                catch (e) { alert('Произошла ошибка'); }
            },
            error: () => { alert('Произошла ошибка'); },
        })
    }
});

$('.self-enroll-btn').on('click', (e) => {
    e.preventDefault();
    $.ajax({
        method: 'POST',
        url: enrollUrl,
        data: {csrfmiddlewaretoken: csrfmiddlewaretoken},
        success: (data) => { window.location.href = data['redirect']; },
        error: () => { alert('Произошла ошибка'); }
    })
});

$('body').delegate('.btn-confirm-delete-entry', 'click', (e) => {
    e.preventDefault();
    const data = {
        csrfmiddlewaretoken: csrfmiddlewaretoken,
        user_id: $(e.target).data('user-id'),
        confirm: 1
    };
    $.ajax({
        url: removeUserUrl,
        method: 'POST',
        data: data,
        success: () => {
            window.location.reload();
        },
        error: () => {
            // TODO show appropriate message
            alert('error');
        }
    });
});

function inputAttendanceChange(obj) {
    const $obj = $(obj);
    const isChecked = $obj.prop('checked');
    const data = {
        csrfmiddlewaretoken: csrfmiddlewaretoken, 
        user_id: $obj.data('user'), 
        status: isChecked
    };      
    $.ajax({
        url: updateAttendanceViewUrl,
        method: 'POST',
        data: data,
        success: (data) => {
            if (!data.success) {
                $obj.prop('checked', !isChecked);
            }
        },
        error: () => {
            // TODO show appropriate message
            alert('error');
            $obj.prop('checked', !isChecked);
        }
    });    
}

function deleteAttendance(obj) {
    const $obj = $(obj);
    const data = {
        csrfmiddlewaretoken: csrfmiddlewaretoken, 
        user_id: $obj.data('user-id')
    };
    $.ajax({
        url: removeUserUrl,
        method: 'POST',
        data: data,
        success: (data) => {
            show_delete_entry_modal(data);
        },
        error: () => {
            // TODO show appropriate message
            alert('error');
        }
    });
}

function show_delete_entry_modal(data) {
    if ($('#delete-entry-modal').length) {
        $('#delete-entry-modal').remove();
    }
    let user_id = data.user_id;
    let msg = 'Вы точно хотите удалить из мероприятия этого пользователя?'
    if (data.has_results)
        msg += ' Он загружал цифровой след для этого мероприятия.'
    html = `
        <div class="modal fade text-left" tabindex="-1" role="dialog" id="delete-entry-modal">
          <div class="modal-dialog">
            <div class="modal-content">
              <div class="modal-body">
                <p>${msg}</p>
                <button data-user-id="${user_id}" class="btn btn-success btn-confirm-delete-entry pull-right">Подтверждаю</button>
                <button data-dismiss="modal" class="btn btn-danger pull-left">Отменить</button>
              </div>
            </div>
          </div>
        </div>
    `;
    $('body').append($(html));
    $('#delete-entry-modal').modal('show');
}

function approveTextButton() {
    const data = {
        approve_text: $('#approve_text_data').val(), 
        csrfmiddlewaretoken: csrfmiddlewaretoken 
    };
    $.ajax({
        url: approveTextEdit,
        method: 'POST',
        data: data,
        success: () => {
            $('.approve-text').addClass('d-none');
        },
        error: () => {
            // TODO show appropriate message
            alert('error');
        }
    });
}