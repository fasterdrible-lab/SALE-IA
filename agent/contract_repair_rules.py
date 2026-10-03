"""
SALEIA — agent/contract_repair_rules.py

Tarefa D5 de docs/tasks-prompt-mestre-v2-restante.md (seção 29 do prompt
mestre): resposta inválida de LLM → **rejeitar → reparar → registrar →
fallback seguro**, para que JSON quebrado nunca chegue à sidebar. Função
pura, zero IA/banco.

Duas camadas:

1. **`reparar_json(texto)`** — usado por `api/ai_router.py::_extract_json`
   quando `json.loads` falha. Reparos só **sintáticos e conservadores**,
   nunca inventam conteúdo: cercas de código no meio do texto, texto
   antes/depois do objeto (extrai o 1º objeto `{...}` balanceado),
   vírgula sobrando antes de `}`/`]`. Se nada disso resolve → rejeita
   (`None`) e o roteador segue para o próximo provedor, como antes.

2. **`reparar_contrato_sidebar(resultado)`** — valida o que a extensão de
   fato lê (`chrome-extension/content.js::atualizarSidebarComResposta`/
   `renderizarNBQ`) e conserta tipo por tipo: texto que não é texto vira
   texto (lista de textos → unidos; número → `str`; objeto → descartado,
   nunca `[object Object]`), `confidence` fora de número em [0,1] vira
   `None` (nunca `NaN%`), `next_best_action` sem `message` utilizável cai
   no fallback inteiro. Cada conserto vira um código em `reparos`, que o
   chamador registra.
"""

import json
import re
from typing import Optional

# Campos de texto do next_best_action que a sidebar renderiza.
NBA_CAMPOS_TEXTO = (
    "message", "title", "type", "category", "objective", "reason",
    "evite", "risk_if_ignored", "follow_up", "expected_effect",
)
NBA_TYPES = frozenset({"question", "insight", "warning", "next_step"})
# Campos de topo que a sidebar escreve como texto.
TOPO_CAMPOS_TEXTO = ("alerta_urgente", "resumo_vivo", "recapitulacao", "texto_falavel", "proxima_pergunta", "proxima_fala")
TOPO_CAMPOS_DICT = ("perfil_disc", "mapa_financeiro")

_CERCA = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_VIRGULA_SOBRANDO = re.compile(r",\s*([}\]])")


def _primeiro_objeto(texto: str) -> Optional[str]:
    """1º objeto `{...}` balanceado, respeitando strings JSON."""
    inicio = texto.find("{")
    while inicio != -1:
        profundidade, em_string, escape = 0, False, False
        for i in range(inicio, len(texto)):
            c = texto[i]
            if em_string:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    em_string = False
            elif c == '"':
                em_string = True
            elif c == "{":
                profundidade += 1
            elif c == "}":
                profundidade -= 1
                if profundidade == 0:
                    return texto[inicio:i + 1]
        inicio = texto.find("{", inicio + 1)
    return None


def _tentar(candidato: str) -> Optional[dict]:
    try:
        valor = json.loads(candidato)
    except (ValueError, TypeError):
        return None
    return valor if isinstance(valor, dict) else None


def reparar_json(texto) -> tuple[Optional[dict], list]:
    """`(objeto, reparos)` — `objeto` é `None` quando não há reparo
    seguro (rejeita). `reparos` lista o que foi feito, para registro."""
    if not isinstance(texto, str) or not texto.strip():
        return None, []
    original = texto.strip()

    direto = _tentar(original)
    if direto is not None:
        return direto, []

    reparos = []
    candidato = original
    cerca = _CERCA.search(candidato)
    if cerca:
        candidato = cerca.group(1).strip()
        reparos.append("cerca_de_codigo")
        obj = _tentar(candidato)
        if obj is not None:
            return obj, reparos

    objeto = _primeiro_objeto(candidato)
    if objeto is not None and objeto != candidato:
        reparos.append("texto_em_volta")
        candidato = objeto
        obj = _tentar(candidato)
        if obj is not None:
            return obj, reparos

    sem_virgula = _VIRGULA_SOBRANDO.sub(r"\1", candidato)
    if sem_virgula != candidato:
        obj = _tentar(sem_virgula)
        if obj is not None:
            return obj, reparos + ["virgula_sobrando"]

    return None, []


def _como_texto(valor) -> tuple[Optional[str], Optional[str]]:
    """`(texto, problema)` — problema `None` quando já era texto."""
    if valor is None or isinstance(valor, str):
        return valor, None
    if isinstance(valor, bool):
        return None, "booleano"
    if isinstance(valor, (int, float)):
        return str(valor), "numero"
    if isinstance(valor, (list, tuple)) and all(isinstance(v, str) for v in valor):
        unido = "; ".join(v.strip() for v in valor if v.strip())
        return (unido or None), "lista"
    return None, "objeto"


def _como_confianca(valor) -> tuple[Optional[float], Optional[str]]:
    if valor is None:
        return None, None
    if isinstance(valor, bool):
        return None, "booleano"
    if isinstance(valor, (int, float)):
        numero = float(valor)
        problema = None
    elif isinstance(valor, str):
        try:
            numero = float(valor.strip().rstrip("%").replace(",", "."))
        except ValueError:
            return None, "texto_nao_numerico"
        problema = "texto_numerico"
        if valor.strip().endswith("%"):
            numero /= 100
    else:
        return None, "objeto"
    if numero != numero:  # NaN
        return None, "nan"
    if 1.0 < numero <= 100.0:
        return numero / 100, problema or "percentual"
    if not 0.0 <= numero <= 1.0:
        return None, "fora_do_intervalo"
    return numero, problema


def reparar_next_best_action(nba, fallback: dict) -> tuple[dict, list]:
    """NBA sempre utilizável pela sidebar. Sem `message` textual não
    vazia depois do reparo → fallback inteiro (`fallback_aplicado`)."""
    if not isinstance(nba, dict):
        return dict(fallback), ["next_best_action:nao_e_objeto:fallback_aplicado"]

    reparado, reparos = dict(nba), []
    for campo in NBA_CAMPOS_TEXTO:
        if campo not in reparado:
            continue
        texto, problema = _como_texto(reparado[campo])
        if problema:
            reparos.append(f"next_best_action.{campo}:{problema}")
            reparado[campo] = texto

    if reparado.get("type") is not None and reparado["type"] not in NBA_TYPES:
        reparos.append("next_best_action.type:fora_do_vocabulario")
        reparado["type"] = "insight"

    if "confidence" in reparado:
        confianca, problema = _como_confianca(reparado["confidence"])
        if problema:
            reparos.append(f"next_best_action.confidence:{problema}")
        reparado["confidence"] = confianca

    if not (reparado.get("message") or "").strip():
        return dict(fallback), reparos + ["next_best_action.message:vazio:fallback_aplicado"]
    return reparado, reparos


def reparar_contrato_sidebar(resultado: dict, fallback_nba: dict) -> tuple[dict, list]:
    """Aplica o contrato da sidebar sobre o resultado já normalizado do
    ciclo. Nunca levanta; devolve `(resultado, reparos)`."""
    if not isinstance(resultado, dict):
        return {"next_best_action": dict(fallback_nba)}, ["resultado:nao_e_objeto:fallback_aplicado"]

    reparos = []
    nba, reparos_nba = reparar_next_best_action(resultado.get("next_best_action"), fallback_nba)
    resultado["next_best_action"] = nba
    reparos += reparos_nba

    for campo in TOPO_CAMPOS_TEXTO:
        if campo in resultado:
            texto, problema = _como_texto(resultado[campo])
            if problema:
                reparos.append(f"{campo}:{problema}")
                resultado[campo] = texto

    for campo in TOPO_CAMPOS_DICT:
        if campo in resultado and not isinstance(resultado[campo], dict):
            reparos.append(f"{campo}:nao_e_objeto")
            resultado[campo] = {}

    disc = resultado.get("perfil_disc")
    if isinstance(disc, dict) and "tipo" in disc:
        tipo, problema = _como_texto(disc["tipo"])
        if problema:
            reparos.append(f"perfil_disc.tipo:{problema}")
            disc["tipo"] = tipo
    return resultado, reparos


def violacoes_do_contrato_sidebar(resultado) -> list:
    """Verificação (sem consertar) do que a sidebar exige — usada pelos
    contract tests para provar que nada inválido passa."""
    if not isinstance(resultado, dict):
        return ["resultado:nao_e_objeto"]
    violacoes = []
    nba = resultado.get("next_best_action")
    if not isinstance(nba, dict) or not isinstance(nba.get("message"), str) or not nba["message"].strip():
        violacoes.append("next_best_action.message")
    else:
        for campo in NBA_CAMPOS_TEXTO:
            if nba.get(campo) is not None and not isinstance(nba[campo], str):
                violacoes.append(f"next_best_action.{campo}")
        conf = nba.get("confidence")
        if conf is not None and (isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1):
            violacoes.append("next_best_action.confidence")
    for campo in TOPO_CAMPOS_TEXTO:
        if resultado.get(campo) is not None and not isinstance(resultado[campo], str):
            violacoes.append(campo)
    for campo in TOPO_CAMPOS_DICT:
        if campo in resultado and not isinstance(resultado[campo], dict):
            violacoes.append(campo)
    return violacoes
