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

$('.export_event_csv').on('click', (e) => {
    e.preventDefault();
    var obj = $(e.target);
    if (obj[0].tagName == 'SPAN')
        obj = obj.parent('a');
    var url = obj.attr('href') + '?check_empty=1';
    $.ajax({
        method: 'GET',
        url: url,
        success: (data) => {
            if (data.has_contents)
                window.location = obj.attr('href');
            else
                alert('Ни одного файла или результата не загружено в мероприятие');
        },
        error: () => { alert('Произошла ошибка'); }
    })
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
        success: () => {
            window.location.reload();
        },
        error: () => {
            // TODO show appropriate message
            alert('error');
        }
    });
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