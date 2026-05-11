"""Column sizing helpers for Qt table-like widgets."""

from __future__ import annotations


def scaled_column_widths(
    base_widths: tuple[int, ...],
    available_width: int,
    *,
    min_width: int,
) -> list[int]:
    """Scale columns so their total width fills the available viewport."""
    if available_width <= 0:
        return list(base_widths)
    base = [max(width, min_width) for width in base_widths]
    min_total = min_width * len(base)
    base_total = sum(base)
    target = max(available_width, min_total)
    if target == base_total:
        return base
    if target < base_total:
        flexible = [max(width - min_width, 0) for width in base]
        extra = target - min_total
        return [min_width + share for share in distribute_width(extra, flexible)]

    extra = target - base_total
    return [
        width + share
        for width, share in zip(
            base,
            distribute_width(extra, base),
            strict=False,
        )
    ]


def distribute_width(total: int, weights: list[int]) -> list[int]:
    """Distribute integer pixels exactly according to column weights."""
    if not weights:
        return []
    if total <= 0:
        return [0 for _ in weights]
    weight_total = sum(weights)
    if weight_total <= 0:
        base = total // len(weights)
        shares = [base for _ in weights]
        for index in range(total - sum(shares)):
            shares[index] += 1
        return shares
    raw = [(total * weight) / weight_total for weight in weights]
    shares = [int(value) for value in raw]
    remainder = total - sum(shares)
    order = sorted(
        range(len(weights)),
        key=lambda index: raw[index] - shares[index],
        reverse=True,
    )
    for index in order[:remainder]:
        shares[index] += 1
    return shares
