$('.list-group-item a.link_preview').each(function (i, element) {
    const icon = element.dataset.icon.substring(1, element.dataset.icon.length-1);
    const html = `<i class ="fa ${icon}"></i>${element.text}`;
    $(element).html(html);
});

$('.list-group-item a.link_preview').on('click', (e) => {
    e.preventDefault();
    linkPreview(e.target);
});

// TODO rewrite using jquery
function linkPreview(obj) {
    
    obj.dataset.target = '#modal_link_preview';
    obj.dataset.toggle = 'modal';
    
    if (element) {
        delete element;
    }

    $('#modal-link-preview-footer').text('');

    if (obj.dataset.file_type == '"pdf"') {
        const element = document.createElement("object");
        element.data = obj.href;
        element.type = "application/pdf";
        element.width = "100%";
        element.height = element.width;
    }
    if (obj.dataset.file_type == '"image"') {
        const element = document.createElement('img');
        element.src = obj.href;
        element.style.width = "100%";
    }
    if (obj.dataset.file_type == '"video"') {
        const element = document.createElement('video');
        element.src = obj.href;
        element.controls = 'true';
        element.preload = 'metadata';
        element.muted = 'true';
        element.playsinline = 'true';
        element.style.width = "100%";
    }
    if (obj.dataset.file_type == '"audio"') {
        const element = document.createElement('audio');
        element.src = obj.href;
        element.controls = 'true';
        element.style.width = "100%";
    }
    if (obj.dataset.file_type == '"other"') {
        const element = document.createElement('a');
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