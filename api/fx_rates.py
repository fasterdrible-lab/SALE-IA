"""
SALEIA — api/fx_rates.py
Conversao USD -> BRL para o Cost Intelligence (Fase 3).

Cotacao de referencia estatica, sobrescrevivel via env (FX_USD_BRL_RATE) —
deliberadamente NAO busca cotacao em tempo real de nenhuma API externa
(evitaria uma dependencia/ponto de falha que o projeto nao tem hoje em
lugar nenhum). Mesma filosofia de api/pricing_catalog.py: valor com um
default razoavel, ajustavel sem deploy.
"""

import os

_USD_BRL_RATE_DEFAULT = 5.40


def taxa_usd_brl() -> float:
    """Cotacao USD->BRL em uso — env FX_USD_BRL_RATE ou o default."""
    return float(os.environ.get("FX_USD_BRL_RATE", _USD_BRL_RATE_DEFAULT))


def usd_para_brl(valor_usd: float) -> float:
    return round((valor_usd or 0.0) * taxa_usd_brl(), 2)
