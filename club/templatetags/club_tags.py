from django import template

register = template.Library()


@register.inclusion_tag('club/includes/verified_badge.html')
def verified_badge(user):
    return {'email_verified': getattr(user, 'email_verified', False)}
