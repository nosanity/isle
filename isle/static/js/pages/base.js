$(document).ready(function() {
    $('.context-switching-select').on('change', function(e) {
        var context_id = $(this).val();
        var url = $(this).data('url');
        $.ajax({
            url: url,
            method: 'POST',
            data: {context_id: context_id, csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(), url: window.location.pathname},
            success: function(data) {
                window.location = data.redirect;
            }
        })
    })
});
