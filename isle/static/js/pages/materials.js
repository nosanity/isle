$('trace-ul').delegate('.my-material-btn', 'click', (e) => {
    e.preventDefault();
    setOwnership(e.target);
});

if (isAssistant) {
    if (teamUpload && canUpload) {
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
        $('body').delegate('.edit-event-block-material', 'click', (e) => {
            e.preventDefault();
            const $obj = $(e.target);
            const id = $obj.val();
            $.get({
                url: eventBlockEditRendererUrl,
                method: 'GET',
                data: { 
                    id: id 
                },
                success: (data) => {
                    const html = `
                        <div>
                            <button class="save-edited-block btn btn-sm btn-danger">
                                Сохранить
                            </button> 
                            <button class="cancel-block-edit btn btn-sm btn-gray">
                                Отменить
                            </button>
                        </div>
                    `;
                    $obj.parents('li').find('div.info-string-edit').html(data).append($(s));
                },
                error: () => {
                    // TODO show appropriate message
                    alert('error');
                }
            })
            }).delegate('.cancel-block-edit', 'click', (e) => {
                e.preventDefault();
                $(e.target).parents('div.info-string-edit').html('');
            }).delegate('.save-edited-block', 'click', (e) => {
                e.preventDefault();
                const $obj = $(e.target);
                const data = $obj.parents('form').serialize();
                $.post({
                    url: addEventBlockUrl,
                    method: 'POST',
                    data: data,
                    success: (data) => {
                        $obj.parents('li').find('span.assistant-info-string').html(data.info_string);
                        $obj.parents('div.info-string-edit').html('');
                    },
                    error: () => {
                        // TODO show appropriate message
                        alert('error');
                    }
                })
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

$('.load-results-btn').on('click', (e) => {
    e.preventDefault();
    let div = $(e.target).parents('.material-result-div');
    div.find('form').removeClass('hidden');
    $(e.target).hide();
});

$('.hide-results-form-btn').on('click', (e) => {
    e.preventDefault();
    $(e.target).parents('.material-result-div').find('form').addClass('hidden');
    $(e.target).parents('.material-result-div').find('.load-results-btn').show();
});

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

function confirmTeamUpload(obj) {
    const $obj = $(obj);
    $.ajax({
        url: confirmTeamUploadUrl,
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

$(document).ready(function() {
    $('body').delegate('.view-result-page', 'click', function(e) {
        e.preventDefault();
        if ($(this).data('url')) {
            window.location = $(this).data('url');
        }
    })
});
