setSort(sortAsc);

$('#choose-date-min').val(date_min);
$('#choose-date-max').val(date_max);
limit_min_dt();
limit_max_dt();

$('body').delegate('#choose-date-min', 'mouseenter', () => {
    $('#choose-date-min').attr('type', 'date')
}).delegate('#choose-date-min', 'mouseleave', () => {
    if (!$('#choose-date-min').val())
        $('#choose-date-min').attr('type', 'text')
}).delegate('#choose-date-min', 'change', limit_max_dt
).delegate('#choose-date-max', 'change', limit_min_dt
).delegate('#choose-date-max', 'mouseenter', () => {
    $('#choose-date-max').attr('type', 'date')
}).delegate('#choose-date-max', 'mouseleave', () => {
    if (!$('#choose-date-max').val())
        $('#choose-date-max').attr('type', 'text')
});

function limit_min_dt() {
    let min_dt = $('#choose-date-min');
    let max_val = $('#choose-date-max').val();
    max_val ? min_dt.attr('max', max_val) : min_dt.removeAttr('max');
}

function limit_max_dt() {
    let max_dt = $('#choose-date-max');
    let min_val = $('#choose-date-min').val();
    min_val ? max_dt.attr('min', min_val) : max_dt.removeAttr('min');
}

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

$('#select-view-mode').on('change', (e) => {
    setCookie('index-view-mode', $(e.target).val(), 1);
    window.location.reload();
});

function setCookie(name,value,days) {
    var expires = "";
    if (days) {
        var date = new Date();
        date.setTime(date.getTime() + (days*24*60*60*1000));
        expires = "; expires=" + date.toUTCString();
    }
    document.cookie = name + "=" + (value || "")  + expires + "; path=/";
}

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