from django import template
from isle.forms import EventMaterialForm

register = template.Library()


@register.filter
def add_class(value, arg):
    old_class = value.field.widget.attrs.get('class')
    if old_class:
        new_class = '{} {}'.format(old_class, arg)
    else:
        new_class = arg
    value.field.widget.attrs.update({'class': new_class})
    return value


@register.filter
def set_placeholder(value, arg):
    value.field.widget.attrs['placeholder'] = arg
    return value


@register.inclusion_tag('_material_event_block.html')
def render_event_block_form(prefix, event):
    """
    отрисовка форм с различными префиксами, чтобы автокомплиты не конфликтовали
    """
    return {'blocks_form': EventMaterialForm(event=event, prefix=prefix)}
