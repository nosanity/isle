$('input[name=name]').on('keyup change', submitButtonControl);
$('input[name=users]').on('change', submitButtonControl);

$('#team-form').submit((e) => {
    e.preventDefault();
    teamFormSubmit(e.target);
});

function isTeamFormValid() {
    const $teamForm = $('#team-form');
    // TODO to simplify this later
    return !!$teamForm.find('input[name=name]').val() && $teamForm.find('input[name=users]:checked').length;
}

function submitButtonControl() {
    const $submit = $('#submit');
    if (isTeamFormValid()) {
        $submit.prop('disabled', false);
    } else {
        $submit.prop('disabled', true);
    }
}

function teamFormSubmit(obj) {
    if (isTeamFormValid()) {
        $.ajax({
            method: 'POST',
            data: new FormData(obj),
            processData: false,
            contentType: false,
            success: (data) => {
                window.location = data.redirect;
            },
            error: (xhr, err) => {
                // TODO show appropriate message
                alert('error');
            }
        })
    }
}



