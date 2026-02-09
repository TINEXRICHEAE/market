from django import template

register = template.Library()

@register.filter
def sum_subtotals(items):
    """Sum the subtotals of cart items"""
    return sum(item.subtotal for item in items)