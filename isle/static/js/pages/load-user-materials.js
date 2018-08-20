$('trace-ul').delegate('.my-material-btn', 'click', (e) => {
    e.preventDefault();
    setOwnership(e.target);
});

$('body').delegate('.my-material-btn', 'click', function(e) {
    e.preventDefault();
    var is_owner = this.hasAttribute('data-owner');
    var self = $(this);
    var data = {csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(), confirm: !is_owner};
    $.ajax({
        url: self.data('url'),
        method: 'POST',
        data: data,
        success: function(data) {
            if (data.is_owner) {
                self.attr('data-owner', '').text('Это не мое').addClass('btn-danger').removeClass('btn-success');
            }
            else {
                self.removeAttr('data-owner').text('Это мое').addClass('btn-success').removeClass('btn-danger');
            }
            if (data.owners) {
                self.parents('li').find('.material-owners').html('Связан с: ' + data.owners);
            }
            else {
                self.parents('li').find('.material-owners').html('');
            }
        }
    })
});