$('#my-activities').on('change', (e) => {
    $obj = $(e.target);
    const base = `${window.location.protocol}//${window.location.host}${window.location.pathname}`;
    window.location.replace($obj.prop('checked') ? (`${base}?activities=my`) : base);
})