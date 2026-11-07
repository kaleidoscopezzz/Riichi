"""Exact, reusable configuration validation; no match scoring here."""
import re
from decimal import Decimal, InvalidOperation, localcontext

from django.core.exceptions import ValidationError


def default_uma():
    return ["30", "10", "-10", "-30"]


def canonical_uma(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValidationError("Uma 必须按第一至第四名顺序包含四项。")
    result = []
    for item in value:
        # JSON floating point is deliberately rejected: callers send decimal strings.
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise ValidationError("Uma 请使用整数或精确十进制字符串。")
        text = str(item)
        if len(text) > 64 or not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", text):
            raise ValidationError("Uma 必须为最多64字符的有限十进制数，不使用科学计数法。")
        try:
            number = Decimal(text)
        except InvalidOperation:
            raise ValidationError("Uma 数值无效。") from None
        result.append(format(number, "f"))
    return result


def validate_uma(value):
    canonical_uma(value)


def canonical_oka(value):
    """None derives Oka; zero is an explicit override, never a missing value."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValidationError("头名赏 Oka 请使用整数或精确十进制字符串。")
    text = str(value)
    if len(text) > 64 or not re.fullmatch(r"[+]?[0-9]+(?:\.[0-9]+)?", text):
        raise ValidationError("头名赏 Oka 必须为最多64字符的非负十进制数，0 表示无头名赏，不使用科学计数法。")
    number = Decimal(text)
    return "0" if number == 0 else format(number, "f")


def validate_oka(value):
    canonical_oka(value)


def derive_oka(starting_points, return_points):
    with localcontext() as context:
        context.prec = 80
        return format(Decimal(4) * (Decimal(return_points) - Decimal(starting_points)) / Decimal(1000), "f")
