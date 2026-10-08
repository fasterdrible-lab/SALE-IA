"""Alerta de IA fora do ar (08/10/2026).

De 06/10 13:32 UTC a 08/10 nenhum provedor respondeu (DeepSeek sem saldo,
OpenAI sem créditos, Anthropic com crédito baixo, chave do Gemini
inválida) e ninguém percebeu: o `/health` dizia "online" (contava
"degradado" como disponível) e os alertas existentes eram por provedor
("breaker aberto, fallback para o próximo"), sem dizer que TODOS tinham
caído nem por quê.

Funções puras — zero IA, zero banco, zero Telegram. Quem guarda o estado
e envia é `api/ai_router.py`.
"""

CAUSA_SEM_SALDO = "sem_saldo"
CAUSA_CHAVE_INVALIDA = "chave_invalida"
CAUSA_LIMITE_DE_USO = "limite_de_uso"
CAUSA_SEM_CHAVE = "sem_chave"
CAUSA_OUTRA = "outra"

_PADROES_SEM_SALDO = (
    "402", "insufficient balance", "insufficient_quota", "no credits",
    "credit balance is too low", "billing", "payment required",
)
_PADROES_CHAVE_INVALIDA = (
    "401", "api key not valid", "invalid_api_key", "invalid api key",
    "incorrect api key", "authentication", "unauthorized", "permission_denied",
)
_PADROES_LIMITE = ("429", "rate limit", "ratelimit", "too many requests", "resource_exhausted")

ACAO_POR_CAUSA = {
    CAUSA_SEM_SALDO: "recarregar saldo/créditos",
    CAUSA_CHAVE_INVALIDA: "gerar chave nova e salvar em Configurações → APIs",
    CAUSA_LIMITE_DE_USO: "aguardar o limite de uso ou subir o plano",
    CAUSA_SEM_CHAVE: "cadastrar a chave em Configurações → APIs",
    CAUSA_OUTRA: "ver o journal (`journalctl -u saleia`)",
}


def classificar_causa(erro: str | None) -> str:
    """Causa provável a partir da mensagem de erro do provedor. Saldo vem
    antes de limite de uso: a OpenAI devolve `429` com `insufficient_quota`
    quando acaba o crédito, e isso não passa esperando."""
    texto = (erro or "").lower()
    if not texto:
        return CAUSA_OUTRA
    if any(p in texto for p in _PADROES_SEM_SALDO):
        return CAUSA_SEM_SALDO
    if any(p in texto for p in _PADROES_CHAVE_INVALIDA):
        return CAUSA_CHAVE_INVALIDA
    if any(p in texto for p in _PADROES_LIMITE):
        return CAUSA_LIMITE_DE_USO
    return CAUSA_OUTRA


def resumir_estado(provedores: dict[str, dict], falhas_para_abrir: int) -> dict:
    """`provedores`: `{nome: {"configurado", "falhas", "ultimo_erro"}}`.
    A IA está disponível se algum provedor configurado está abaixo do
    limite de falhas que abre o breaker. É o último estado conhecido: depois
    de recarregar saldo, só volta a "disponível" na 1ª chamada real."""
    causas: dict[str, str] = {}
    disponivel = False
    for nome, p in provedores.items():
        if not p.get("configurado"):
            causas[nome] = CAUSA_SEM_CHAVE
            continue
        if (p.get("falhas") or 0) < falhas_para_abrir:
            disponivel = True
            continue
        causas[nome] = classificar_causa(p.get("ultimo_erro"))
    return {"ia_disponivel": disponivel, "causas": {} if disponivel else causas}


def montar_alerta_ia_fora(causas: dict[str, str], minutos_fora: int) -> str:
    linhas = [f"• *{nome}*: {causa.replace('_', ' ')} → {ACAO_POR_CAUSA.get(causa, ACAO_POR_CAUSA[CAUSA_OUTRA])}"
              for nome, causa in causas.items()]
    tempo = "agora" if minutos_fora < 1 else f"há {minutos_fora} min"
    return (
        f"🚨 *IA FORA DO AR* ({tempo}) — todos os provedores falharam.\n"
        "Vendedores em reunião estão sem sugestão.\n"
        + "\n".join(linhas)
    )


def montar_alerta_ia_voltou(provedor: str, minutos_fora: int) -> str:
    return f"✅ IA voltou via *{provedor}* depois de {minutos_fora} min fora do ar."
