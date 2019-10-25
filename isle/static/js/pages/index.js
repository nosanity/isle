setSort(sortAsc);

create_dt_warning_tooltip();
$('#choose-date-min').val(date_min);
$('#choose-date-max').val(date_max);
limit_min_dt();
limit_max_dt();
check_dt_limits();

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
    check_dt_limits();
}

function limit_max_dt() {
    let max_dt = $('#choose-date-max');
    let min_val = $('#choose-date-min').val();
    min_val ? max_dt.attr('min', min_val) : max_dt.removeAttr('min');
    check_dt_limits();
}

$('#btn-filter-events').click((e) => {
    e.preventDefault();
    if (!check_dt_limits()) return;
    let url = window.location.href;
    url = queryStringUrlReplacement(url, 'date_min', $('#choose-date-min').val() || '');
    url = queryStringUrlReplacement(url, 'date_max', $('#choose-date-max').val() || '');
    url = queryStringUrlReplacement(url, 'search', $('#search-events').val() || '');
    url = queryStringUrlReplacement(url, 'page', 1);
    window.location.replace(url)
});

function check_dt_limits() {
    let min_dt = $('#choose-date-min').val() || '';
    let max_dt = $('#choose-date-max').val() || '';
    if (min_dt && max_dt && min_dt > max_dt) {
        show_dt_warning();
        return false;
    }
    return true;
}

function show_dt_warning() {
    $('.dt-warning-tooltip').css('opacity', 1)
    setTimeout(() => {$('.dt-warning-tooltip').css('opacity', 0);}, 2000);
}

function create_dt_warning_tooltip() {
    $('body').append($(`
        <div class="dt-warning-tooltip">
            "Дата: от" не должна быть больше, чем "Дата: до"
        </div>
    `))
    let dt_min_coordinates = findPosition($('#choose-date-min')[0]);
    $('.dt-warning-tooltip').css('left', dt_min_coordinates[0] + 'px')
        .css('top', (dt_min_coordinates[1] - $('.dt-warning-tooltip').height() - 15) + 'px');
}

function findPosition(obj) {
   var curleft = curtop = 0;
   if (obj.offsetParent) {
      do {
         curleft += obj.offsetLeft;
         curtop += obj.offsetTop;
      } while (obj = obj.offsetParent);
   }

   return [curleft, curtop];
}

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

$('.events-filter-cancel-btn').on('click', (e) => {
    e.preventDefault();
    let btn = $(e.target);
    btn = btn.first().tagName == 'A' ? btn : btn.parents('a');
    window.location = btn.attr('href');
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
