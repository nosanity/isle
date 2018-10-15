function init_formset() {
    $('.form-row').formset({
        addText: '<span class="glyphicon glyphicon-plus-sign"></span> Добавить',
        addCssClass: 'add-formset-btn',
        deleteText: 'Удалить',
        deleteCssClass: 'delete-formset-btn'
    });
}
init_formset();

$('body').delegate('#blocks-form', 'submit', (e) => {

    if (!isBlockFormReadyToSubmit(e.target)) {
        e.preventDefault();
    }
}).delegate('.delete-block-form', 'submit', (e) => {
    e.preventDefault();
    var form = $(e.target);
    $.ajax({
        method: 'GET',
        url: form.attr('action'),
        success: function(data) {
            if (data.has_materials) {
                $('#info-block-modal button.btn-confirm-delete').data('url', form.attr('action')).show();
                $('#info-block-modal button.btn-confirm-import').hide();
                $('#info-block-modal p.modal-info').html('К данному блоку уже есть прикрепленные материалы. Если вы его удалите, эти материалы потеряют привязку к блоку структуры мероприятия.');
                $('#info-block-modal').modal('show');
            }
            else {
                $.post(form.attr('action'), form.serialize(), (data) => {window.location = data.redirect});
            }
        },
        error: function() {
            alert('error');
        }
    });
});

$('.btn-confirm-delete').on('click', (e) => {
    $.post($(e.target).data('url'), {csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val()}, (data) => {window.location = data.redirect});
})

function isBlockFormReadyToSubmit(obj) {
    $('.field-error').removeClass('field-error');
    for (row of $(obj).find('.form-row')) {
        blockCheckFormRow(row);
    }
    return ($('.field-error').length ? false : true);
}

function blockCheckFormRow(formRow) {
    const $formRow = $(formRow);
    const inputs = [
        $formRow.find('input[name$=duration]'), 
        $formRow.find('input[name$=title]'), 
        $formRow.find('select[name$=block_type]')
    ];
    for (input of inputs) {
        if (!input.val()) {
            $(input).addClass('field-error');
        }
    }
}

$('#open-import-popup').on('click', function(e) {
    $('#import-structure-modal').modal('show');
});

function doImport() {
    var form = $('#import-structure-form');
    $.ajax({
        method: 'GET',
        url: form.attr('action'),
        data: form.serialize(),
        success: function (data) {
            $('#import-structure-modal').modal('hide');
            $('#blocks-form').replaceWith($(data));
            init_formset();
            $('#blocks-form div.form-inline').last().find('a.delete-formset-btn').trigger('click');
        },
        error: function() {
            alert('error');
        }
    })
}

$('#import-structure-form').on('submit', function(e) {
    e.preventDefault();
    $.ajax({
        method: 'GET',
        url: hasBlocksWithMaterialsUrl,
        success: function(data) {
            if (data.blocks_with_materials) {
                $('#info-block-modal button.btn-confirm-import').show();
                $('#info-block-modal button.btn-confirm-delete').hide();
                $('#info-block-modal p.modal-info').html('К некоторым блокам мероприятия уже прикреплены материалы. Если вы импортируете структуру из другого мероприятия, эти материалы потеряют привязку к блокам структуры. ');
                $('#info-block-modal').modal('show');
            }
            else {
                doImport();
            }
        }
    });
});

$('.btn-confirm-import').on('click', (e) => {
    $('#info-block-modal').modal('hide');
    doImport();
});
