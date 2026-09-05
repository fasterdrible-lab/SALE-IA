"""Provider Python do Promptfoo — ponte para o Coach Agent real da SALEIA.

Nao reimplementa a logica de chamada de IA (regra do PROMPT MESTRE:
"evoluir a arquitetura existente, nao criar sistemas paralelos"): importa
e executa agent.multiagente.coach_agent.analisar_coach diretamente, o
mesmo codigo que roda em producao dentro de analisar_fragmento_multi
(agent/multiagente/orquestrador.py).

Cada avaliacao e uma chamada real de IA — usa o provedor configurado no
.env do ambiente onde o eval roda (api/ai_router.py), com custo real.
"""

import asyncio
import json
import sys
from pathlib import Path

_SALEIA_ROOT = Path(__file__).resolve().parents[2]
if str(_SALEIA_ROOT) not in sys.path:
    sys.path.insert(0, str(_SALEIA_ROOT))

from agent.multiagente.coach_agent import analisar_coach  # noqa: E402


def call_api(prompt, options, context):
    vars_ = (context or {}).get("vars", {}) or {}
    transcricao = vars_.get("transcricao", prompt)

    try:
        resultado = asyncio.run(
            analisar_coach(
                transcricao_parcial=transcricao,
                historico=vars_.get("historico", ""),
                resumo_vivo=vars_.get("resumo_vivo", ""),
                diagnostico_atual=vars_.get("diagnostico_atual", {}) or {},
                eventos=vars_.get("eventos", []) or [],
                skill_context=vars_.get("skill_context", ""),
                client_context=vars_.get("client_context", ""),
            )
        )
    except Exception as exc:  # melhor esforco: promptfoo trata "error" como falha do teste
        return {"error": f"{type(exc).__name__}: {exc}"}

    return {"output": json.dumps(resultado, ensure_ascii=False)}
