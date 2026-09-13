"""Provider Python do Promptfoo — ponte para o SalesReasoningEngine real
da SALEIA (Fase 7 / Tarefa 7.1 do "PROMPT MESTRE — SALE-IA V2").

Mesmo principio do coach_provider.py/finance_provider.py: importa e
executa agent.sales_reasoning_engine.raciocinar_async diretamente, o
mesmo codigo que rodaria em producao quando esse motor for plugado num
ponto de chamada real — nenhuma logica de raciocinio duplicada aqui.

Cada avaliacao e uma chamada real de IA (via chamar_ia_com_fallback_
claude, mesmo caminho dos 5 agentes de agent/multiagente/) — usa o
provedor configurado no .env do ambiente onde o eval roda, com custo
real.
"""

import asyncio
import json
import sys
from pathlib import Path

_SALEIA_ROOT = Path(__file__).resolve().parents[2]
if str(_SALEIA_ROOT) not in sys.path:
    sys.path.insert(0, str(_SALEIA_ROOT))

from agent.sales_reasoning_engine import SALES_REASONING_INPUT_CAMPOS, raciocinar_async  # noqa: E402


def call_api(prompt, options, context):
    vars_ = (context or {}).get("vars", {}) or {}

    entrada = {campo: vars_.get(campo) for campo in SALES_REASONING_INPUT_CAMPOS}

    # "context": narrativa livre do cenario do dataset — nao faz parte
    # do contrato de 11 campos do SalesReasoningEngine, entao e dobrada
    # dentro de meeting_memory pra virar sinal real pro motor (mesmo
    # papel que MeetingMemory.accumulated_summary tem em producao).
    contexto_narrativo = vars_.get("context")
    if contexto_narrativo:
        meeting_memory = entrada.get("meeting_memory")
        if not isinstance(meeting_memory, dict):
            meeting_memory = {}
        entrada["meeting_memory"] = {**meeting_memory, "contexto_cenario": contexto_narrativo}

    try:
        resultado = asyncio.run(raciocinar_async(entrada))
    except Exception as exc:  # melhor esforco: promptfoo trata "error" como falha do teste
        return {"error": f"{type(exc).__name__}: {exc}"}

    return {"output": json.dumps(resultado, ensure_ascii=False)}
