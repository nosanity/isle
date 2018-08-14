$('#i-was-here').click(() => { 
    $('.approve-text').removeClass('d-none');
});

$('.hide-text-btn').click(() => {
    $('.approve-text').addClass('d-none');
});

$('.approve-text-btn').click(() => {
    e.preventDefault();
    approveTextButton();
});

if (isAssistant) {
    $('#refresh, #refresh-check-ins').on('click', (e) => {
        e.preventDefault();
        refresh(e.target);
    });

    $('.btn-confirm-team').on('click', (e) => {
        e.preventDefault();
        confirmTeam(e.target);
    });

    $('input.attendance').on('change', (e) => {
        inputAttendanceChange(e.target);
    });

    $('#event-users-table').delegate('.btn-delete-attendance', 'click', (e) => {
        e.preventDefault();
        deleteAttendance(e.target);
    });
}

function refresh(obj) {
    const $obj = $(obj);
    $obj.prop('disabled', true);
    $.ajax({
        url: $obj.data('url'),
        type: 'GET',
        success: function(data) {
            if (data.success) {
                window.location.reload();
            }
        },
        complete: function(xhr, status) {
            $obj.prop('disabled', false);
        }
    });
}

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
        success: function(data) {
            if (!data.success) {
                $obj.prop('checked', !isChecked);
            }
        },
        error: function() {
            // TODO show appropriate message
            alert('error');
            $obj.prop('checked', !isChecked);
        }
    });    
}

function confirmTeam(obj) {
    const $obj = $(obj);
    const data = {
        csrfmiddlewaretoken: csrfmiddlewaretoken, 
        team_id: $obj.val()
    };
    $.ajax({
        url: confirmTeamUrl,
        method: 'POST',
        data: data,
        success: function() {
            $obj.parents('tr').addClass('confirmed-team-link');
            $obj.remove();
        },
        error: function() {
            // TODO show appropriate message
            alert('error');
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
        success: function() {
            window.location.reload();
        },
        error: function() {
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
        success: function() {
            $('.approve-text').addClass('d-none');
        },
        error: function() {
            // TODO show appropriate message
            alert('error');
        }
    });
}