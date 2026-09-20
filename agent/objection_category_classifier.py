"""Bloco 1 / Tarefa 1.2 de docs/tasks-sales-reasoning-engine-completo.md
— classifica a categoria de uma objeção já detectada pelo Finance
(`resultado["objecao_detectada"]`, `agent/multiagente/finance_agent.py`)
num dos 13 valores fechados de `agent/objection_rules.py::
OBJECTION_TIPOS`.

Achado que motivou este módulo (investigado antes de codar, mesma
disciplina do resto do projeto): o Finance já detecta que existe uma
objeção e já traz a transcrição real dela (`objecao_detectada.objecao`
— evidência real, reaproveitável), mas **nunca classifica em qual das
13 categorias** ela se encaixa. Sem categoria, `agent/
objection_rules.py::_validar_objection_spoken()` recusa o fato — não
dá pra "traduzir de graça" como se pensou inicialmente. Usuário
confirmou: 1 chamada de IA nova, pequena e barata, só pra essa
classificação (nunca reclassifica se já existe objeção detectada — só
decide a categoria).

Separado em módulo próprio (não dentro de
`agent/objecao_detectada_para_objection_rules.py`) porque é a única
peça desta tarefa que chama IA — o resto é função pura, testável sem
mock de rede."""

import json
from pathlib import Path
from typing import Optional

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from agent.objection_rules import OBJECTION_TIPOS
from api import ai_features

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "objecao_categoria_classificacao.txt"

_SYSTEM_PROMPT = (
    "Você classifica a categoria de objeções de venda. Responda SEMPRE "
    "em JSON válido, sem texto antes ou depois."
)


async def classificar_categoria_objecao_async(
    objecao_texto: str,
    usuario_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> Optional[str]:
    """Classifica `objecao_texto` (a transcrição real da objeção, de
    `objecao_detectada.objecao`) num dos 13 valores de `OBJECTION_
    TIPOS`, ou `None` quando a IA não conseguir classificar com clareza
    (nunca força a categoria mais parecida) ou responder algo fora do
    vocabulário fechado — mesma disciplina de nunca inventar categoria.
    Propaga exceção de IA de verdade (os 4 provedores + fallback Claude
    esgotados) — o chamador decide se isso é best-effort ou não."""
    if not (objecao_texto or "").strip():
        return None

    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{objecao_texto}", objecao_texto)

    resposta = await chamar_ia_com_fallback_claude(
        _SYSTEM_PROMPT,
        prompt,
        usuario_id,
        feature=ai_features.OBJECTION_CATEGORIA_CLASSIFICACAO,
        meeting_id=meeting_id,
    )

    categoria = (resposta or {}).get("category")
    if categoria not in OBJECTION_TIPOS:
        return None
    return categoria
