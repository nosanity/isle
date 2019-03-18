setSort(sortAsc);

$('#choose-date').val(date);

$('#btn-date-refresh').click((e) => {
    e.preventDefault();
    window.location.replace(
        queryStringUrlReplacement(window.location.href, 'date', $('#choose-date').val())
    );
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