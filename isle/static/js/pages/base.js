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

    $('.context-switching-select option').each(function () {
        let max_length = 100
        var text = $(this).text();
        if (text.length > max_length) {
            text = text.substring(0, max_length - 1) + '...';
            $(this).text(text);
        }
    });
});
