$('.form-row').formset({
    addText: '<span class="glyphicon glyphicon-plus-sign"></span> Добавить',
    addCssClass: 'add-formset-btn',
    deleteText: 'Удалить',
    deleteCssClass: 'delete-formset-btn'
});

$('#blocks-form').on('submit', (e) => {
    if (!isBlockFormReadyToSubmit(e.target)) {
        e.preventDefault();
    }
});

function isBlockFormReadyToSubmit(obj) {
    const $fieldError = $('.field-error');
    $fieldError.removeClass('field-error');
    for (row of $(obj).find('.form-row')) {
        blockCheckFormRow(row);
    }
    return ($fieldError.length ? false : true);
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