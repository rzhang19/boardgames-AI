from django import template

register = template.Library()


@register.filter
def dict_lookup(dictionary, key):
    return dictionary.get(key)


@register.inclusion_tag('club/includes/verified_badge.html')
def verified_badge(user):
    return {
        'email_verified': getattr(user, 'email_verified', False),
        'verified_icon': getattr(user, 'verified_icon', None),
    }
