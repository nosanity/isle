function show_export_modal(text) {
    if ($('#events_csv_export_modal').length == 0) {
        let modal = `
            <div id="events_csv_export_modal" class="modal fade" role="dialog" style="max-width: 100vw;">
              <div class="modal-dialog">
                <div class="modal-content">
                  <div class="modal-header">
                    <button type="button" class="close filter-modal-dismiss" data-dismiss="modal"
                          aria-label="Закрыть"><span aria-hidden="true">&times;</span></button>
                  </div>
                  <div class="modal-body">
                    <p>${text}<p>
                  </div>
                </div>
              </div>
            </div>
        `;
        $('body').append($(modal));
    }
    else {
        $('#events_csv_export_modal div.modal-body').empty().append($(`<p>${text}</p>`));
    }
    $('#events_csv_export_modal').modal('show');
}

$('.prepare-csv-export').on('click', (e) => {
    e.preventDefault();
    let obj = $(e.target);
    if (obj[0].tagName == 'SPAN')
        obj = obj.parent('a');
    $('.export-format-selector').show();
});

$('.export-format-selector').on('change', (e) => {
    e.preventDefault();
    var obj = $(e.target);
    if (!obj.val()) return;
    obj.prop('disabled', true);
    let url = $('.prepare-csv-export').attr('href') + window.location.search;
    let url_check = queryStringUrlReplacement(url, 'check_empty', '1');
    let url_request = queryStringUrlReplacement(url, 'format', obj.val());
    $.ajax({
        method: 'GET',
        url: url_check,
        success: (data) => {
            if (data.has_contents) {
                if (data.sync) {
                    window.location = url_request;
                }
                else {
                    let modal_text;
                    if (data.can_generate) {
                        let num = data.max_num;
                        let result_url = data.page_url;
                        $.ajax({
                            method: 'GET',
                            url: url_request,
                            success: (data) => {
                                modal_text = `
                                    Выгрузка содержит более ${num} материалов.
                                    По окончании генерации вы сможете скачать результат на странице <a href="${result_url}">"Мои выгрузки"</a>
                                `;
                                show_export_modal(modal_text);
                            },
                            error: () => { alert('Произошла ошибка'); }
                        })
                    }
                    else {
                        let max_csv = data.max_csv;
                        modal_text = `
                            Нелья заказать генерацию более ${max_csv} выгрузок одновременно.
                            Дождитесь окончания генерации выгрузки.
                        `;
                        show_export_modal(modal_text);
                    }
                }
            }
            else
                alert('Ни одного файла или результата не загружено в выбранные мероприятия');
        },
        error: () => { alert('Произошла ошибка'); },
        complete: () => {
            obj.prop('disabled', false).hide().val('');
        }
    })
});
