"""Provider Python do Promptfoo — ponte para o Finance Agent real da SALEIA.

Mesmo principio do coach_provider.py: importa e executa
agent.multiagente.finance_agent.analisar_finance diretamente, sem
duplicar a logica de chamada de IA.
"""

import asyncio
import json
import sys
from pathlib import Path

_SALEIA_ROOT = Path(__file__).resolve().parents[2]
if str(_SALEIA_ROOT) not in sys.path:
    sys.path.insert(0, str(_SALEIA_ROOT))

from agent.multiagente.finance_agent import analisar_finance  # noqa: E402


def call_api(prompt, options, context):
    vars_ = (context or {}).get("vars", {}) or {}
    transcricao = vars_.get("transcricao", prompt)

    try:
        resultado = asyncio.run(
            analisar_finance(
                transcricao_parcial=transcricao,
                historico=vars_.get("historico", ""),
                mapa_financeiro=vars_.get("mapa_financeiro", {}) or {},
            )
        )
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}

    return {"output": json.dumps(resultado, ensure_ascii=False)}
