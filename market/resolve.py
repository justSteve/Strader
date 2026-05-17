from __future__ import annotations
from market.entities.chain import Chain, strike_key
from market.entities.spread import ButterflyTemplate, ButterflyInstance


class ResolutionError(Exception):
    """Required strike unavailable in the chain."""


def resolve_butterfly(template: ButterflyTemplate, chain: Chain) -> ButterflyInstance:
    """Resolve a ButterflyTemplate against a Chain into a ButterflyInstance.

    Raises ResolutionError if any leg strike is absent.
    """
    center = _resolve_center(template, chain)
    lower  = center - template.width
    upper  = center + template.width

    source = chain.calls if template.contract_type == "CALL" else chain.puts
    for s in (lower, center, upper):
        if strike_key(s) not in source:
            raise ResolutionError(
                f"Strike {s} not in {chain.underlying} {chain.expiry} {template.contract_type} chain"
            )

    lc = source[strike_key(lower)]
    cc = source[strike_key(center)]
    uc = source[strike_key(upper)]

    net_debit  = round(lc.mid - 2 * cc.mid + uc.mid, 4)
    max_profit = round(template.width - net_debit, 4)
    max_loss   = round(net_debit, 4)
    be_lower   = round(lower + net_debit, 4)
    be_upper   = round(upper - net_debit, 4)

    return ButterflyInstance(
        template=template, lower=lc, center=cc, upper=uc,
        net_debit=net_debit, max_profit=max_profit, max_loss=max_loss,
        breakeven_lower=be_lower, breakeven_upper=be_upper,
    )


def _resolve_center(template: ButterflyTemplate, chain: Chain) -> float:
    spec = template.center.strip()
    if spec == "ATM":
        return _nearest(chain.underlying_price, chain, template.contract_type)
    if spec.startswith("ATM"):
        sign   = 1 if "+" in spec else -1
        offset = float(spec.replace("ATM+", "").replace("ATM-", "")) * sign
        return _nearest(chain.underlying_price + offset, chain, template.contract_type)
    return float(spec)


def _nearest(price: float, chain: Chain, side: str) -> float:
    source = chain.calls if side == "CALL" else chain.puts
    best   = min(source.keys(), key=lambda k: abs(k - strike_key(price)))
    return source[best].strike
