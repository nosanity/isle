function apply_preview_icons() {
    $('.list-group-item a.link_preview').each(function (i, element) {
        if (!$(element).find('i.fa').length) {
            const icon = element.dataset.icon
            const html = `<i class ="fa ${icon}"></i>&nbsp;${element.text}`;
            $(element).html(html);
        }
    });
}

apply_preview_icons();

$('body').delegate('.list-group-item a.link_preview', 'click', (e) => {
    e.preventDefault();
    linkPreview(e.target);
});

// TODO rewrite using jquery
function linkPreview(obj) {
    
    obj.dataset.target = '#modal_link_preview';
    obj.dataset.toggle = 'modal';

    $('#modal-link-preview-footer').text('');

    let element = null;
    
    if (obj.dataset.file_type == 'pdf') {
        element = document.createElement("object");
        element.data = obj.href;
        element.type = "application/pdf";
        element.width = "100%";
        element.height = element.width;
    }
    if (obj.dataset.file_type == 'image') {
        element = document.createElement('img');
        element.src = obj.href;
        element.style.width = "100%";
    }
    if (obj.dataset.file_type == 'video') {
        element = document.createElement('video');
        element.src = obj.href;
        element.controls = 'true';
        element.preload = 'metadata';
        element.muted = 'true';
        element.playsinline = 'true';
        element.style.width = "100%";
    }
    if (obj.dataset.file_type == 'audio') {
        element = document.createElement('audio');
        element.src = obj.href;
        element.controls = 'true';
        element.style.width = "100%";
    }
    if (obj.dataset.file_type == 'other') {
        element = document.createElement('a');
        element.innerText = "Скачать файл";
        $(element).addClass('btn');
        element.href = obj.href;
        element.style.width = "100%"
    }
    $('#modal_link_preview').on('hide.bs.modal', (e) => {
        $(element).remove();
    });
    $('#modal_link_preview_title').html(obj.innerHTML);
    document.querySelector('div.preview').innerHTML = '';
    document.querySelector('div.preview').appendChild(element);
}