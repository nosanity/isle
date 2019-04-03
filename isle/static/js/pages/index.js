setSort(sortAsc);

$('#choose-date-min').val(date_min);
$('#choose-date-max').val(date_max);

$('body').delegate('#choose-date-min', 'mouseenter', () => {
    $('#choose-date-min').attr('type', 'date')
}).delegate('#choose-date-min', 'mouseleave', () => {
    if (!$('#choose-date-min').val())
        $('#choose-date-min').attr('type', 'text')
}).delegate('#choose-date-max', 'mouseenter', () => {
    $('#choose-date-max').attr('type', 'date')
}).delegate('#choose-date-max', 'mouseleave', () => {
    if (!$('#choose-date-max').val())
        $('#choose-date-max').attr('type', 'text')
});

$('#btn-filter-events').click((e) => {
    e.preventDefault();
    let url = window.location.href;
    url = queryStringUrlReplacement(url, 'date_min', $('#choose-date-min').val() || '');
    url = queryStringUrlReplacement(url, 'date_max', $('#choose-date-max').val() || '');
    url = queryStringUrlReplacement(url, 'search', $('#search-events').val() || '');
    url = queryStringUrlReplacement(url, 'page', 1);
    window.location.replace(url)
});

$('span.cancel-activity').on('click', () => {
    window.location.replace(queryStringUrlReplacement(window.location.href, 'activity', ''));
});

$('span.sort-col').on('click', (e) => {
    const isAsc = $(e.target).hasClass('glyphicon-sort-by-attributes-alt');
    window.location.replace(queryStringUrlReplacement(window.location.href, 'sort', isAsc ? 'asc': 'desc'));
});

function queryStringUrlReplacement(url, param, value) {
    const re = new RegExp(`[\\?&]${param}=([^&#]*)`, "i");
    const match = re.exec(url);

    let newString = null;
    if (match === null) {
        // append new param
        const hasQuestionMark = /\?/.test(url);
        const delimiter = hasQuestionMark ? "&" : "?";
        newString = `${url}${delimiter}${param}=${value}`;
    } else {
        const delimiter = match[0].charAt(0);
        newString = url.replace(re, `${delimiter}${param}=${value}`);
    }

    return newString;
}

function setSort(asc) {
    $('span.sort-col').addClass(
        asc ? 'glyphicon-sort-by-attributes' : 'glyphicon-sort-by-attributes-alt'
    );
}