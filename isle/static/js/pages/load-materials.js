$('trace-ul').delegate('.my-material-btn', 'click', (e) => {
    e.preventDefault();
    setOwnership(e.target);
});

if (isAssistant) {
    if (teamUpload) {
        $('.confirm-material-btn').on('click', (e) => {
            e.preventDefault();
            confirmTeamUpload(e.target);
        });
    }
    if (eventUpload) {
        $('.transfer-material-btn').on('click', (e) => {
            e.preventDefault();
            $('#transfer-modal').data('material-id', $(this).val()).modal('show');
        });     
        $('.transfer-from-event').on('click', (e) => {
            e.preventDefault();
            const $obj = $(e.target);
            const data = {
                material_id: $('#transfer-modal').data('material-id'),
                dest_id: $obj.val(),
                type: $obj.data('type-to'),
            }
            transfer(
                $obj, 
                data,
                'Вы уверены, что хотите переместить файл?',
                () => {
                    const materialId = $('#transfer-modal').data('material-id');
                    $(`.transfer-material-btn[value=${materialId}]`).parents('li').remove();
                    $('#transfer-modal').modal('hide');
                }
            );
        });           
    } else {
        $('.transfer-material-btn').on('click', (e) => {
            e.preventDefault();
            const $obj = $(e.target);
            const data = {
                material_id: $obj.val(),
                type: 'event',
                from_user: fromUser,
            }
            $('#transfer-modal').data('material-id', $obj.val()).modal('show');
            transfer(
                $obj, 
                data,
                'Вы уверены, что хотите переместить этот файл в файлы мероприятия?',
                () => {
                    $obj.parents('li').remove();
                }
            );
        });
    }
}

function confirmTeamUpload(obj) {
    const $obj = $(obj);
    $.ajax({
        url: confirmTeamUpload,
        method: 'POST',
        data: {
            material_id: $obj.val(),
            csrfmiddlewaretoken: csrfmiddlewaretoken,
        },
        success: () => {
            $obj.parents('li').addClass('confirmed-team-link');
            $obj.remove();
        },
        error: () => {
            // TODO show appropriate message
            alert('error');
        }
    });
}

function transfer($obj, data, msg, success) {
    if (confirm(msg)) {
        data['csrfmiddlewaretoken'] = csrfmiddlewaretoken;
        $.ajax({
            url: transferUrl,
            method: 'POST',
            data: data,
            success: success,
            error: () => {
                // TODO show appropriate message
                alert('error');
            }
        });
    }
}

function setOwnership(obj) {
    const $obj = $(obj);
    const isOwner = $obj.attr('data-owner');
    $.ajax({
        url: $obj.data('url'),
        method: 'POST',
        data: {
            csrfmiddlewaretoken: csrfmiddlewaretoken,
            confirm: !isOwner,
        },
        success: (data) => {
            if (data.is_owner) {
                $obj.attr('data-owner', '').text('Это не мое').addClass('btn-danger').removeClass('btn-success');
            } else {
                $obj.removeAttr('data-owner').text('Это мое').addClass('btn-success').removeClass('btn-danger');
            }
            if (data.owners) {
                $obj.parents('li').find('.material-owners').html('Связан с: ' + data.owners);
            } else {
                $obj.parents('li').find('.material-owners').html('');
            }
        }
    });
}

