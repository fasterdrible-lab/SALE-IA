"""
agent/data_classification_rules.py

Tarefa 18.3 do "PROMPT MESTRE — SALE-IA V2": classificação de dados +
redação de segredos em logs. Mesmo padrão de `*_rules.py` (função pura,
zero IA/banco) já usado nas Fases 1-17.

Três partes:

1. `DATA_CLASSIFICATION_LEVELS` + `CLASSIFICACAO_CAMPOS_PADRAO` — os 5
   níveis literais do prompt mestre e uma tabela de referência (não
   exaustiva, sobrescrevível) mapeando campos reais do SALEIA a um
   nível. Documentação/contrato, não impõe nenhum comportamento sozinha.
2. `redigir_segredos()`/`redigir_dict()` — a garantia real de "nunca
   logar senha/token/Authorization header/API key". Nunca bloqueia nem
   levanta exceção — sempre retorna algo seguro de logar. Conectado ao
   choke-point real de logging do sistema em `api/main.py::
   _JsonFormatter`, mesmo espírito arquitetural de
   `agent/prompt_injection_rules.py` (Tarefa 18.2): um único ponto que
   intercepta ~100% dos logs em vez de confiar em cada call site.
3. `RETENTION_SUGERIDA_DIAS_PADRAO` — mapeamento de nível → prazo
   sugerido em dias. É só um contrato de referência: NÃO existe job de
   expiração/limpeza automática. Definir prazo de retenção real de
   dado pessoal é decisão de produto/jurídica, fora do escopo desta
   tarefa — os valores aqui são ponto de partida documentado, não
   política vigente.
"""
import re

DATA_CLASSIFICATION_LEVELS = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "PII", "SENSITIVE")

# Tabela de referência — não exaustiva. classificar_campo() nunca inventa
# um nível para um campo desconhecido (retorna None), só reconhece o que
# já foi explicitamente catalogado aqui.
CLASSIFICACAO_CAMPOS_PADRAO = {
    # PUBLIC — visível ao próprio cliente sem autenticação (ex.: /cenario/*)
    "cenario_publico": "PUBLIC",
    "dashboard_publico": "PUBLIC",

    # INTERNAL — uso operacional da equipe, sem dado pessoal/sensível
    "metricas_uso_ia": "INTERNAL",
    "status_provedores": "INTERNAL",
    "workspace_resumo": "INTERNAL",

    # CONFIDENTIAL — inteligência comercial: não é segredo de credencial
    # nem identifica uma pessoa sozinho, mas nunca deveria sair da equipe
    "transcript_full": "CONFIDENTIAL",
    "transcript_buffer": "CONFIDENTIAL",
    "accumulated_summary": "CONFIDENTIAL",
    "current_diagnosis": "CONFIDENTIAL",
    "mapa_financeiro": "CONFIDENTIAL",
    "sales_memory": "CONFIDENTIAL",
    "playbook": "CONFIDENTIAL",

    # PII — identifica uma pessoa real (cliente ou vendedor)
    "nome_cliente": "PII",
    "email": "PII",
    "whatsapp": "PII",
    "telefone": "PII",
    "cpf": "PII",
    "data_nascimento": "PII",
    "usuario_id": "PII",

    # SENSITIVE — credencial/segredo vivo; nunca deve ser persistido em
    # log nem devolvido ao frontend em texto puro
    "senha": "SENSITIVE",
    "password": "SENSITIVE",
    "token": "SENSITIVE",
    "oauth_token_encrypted": "SENSITIVE",
    "api_key": "SENSITIVE",
    "authorization": "SENSITIVE",
    "smtp_pass": "SENSITIVE",
}

# Sugestão de referência — NÃO é uma política aplicada automaticamente.
# None = sem prazo sugerido ainda (decisão de produto pendente para esse
# nível, ou o conceito de "expirar" não se aplica: SENSITIVE é credencial,
# que se rotaciona/nunca deveria persistir em texto puro, não "expira").
RETENTION_SUGERIDA_DIAS_PADRAO = {
    "PUBLIC": None,
    "INTERNAL": None,
    "CONFIDENTIAL": 365,
    "PII": 180,
    "SENSITIVE": None,
}


def classificar_campo(nome_campo: str) -> str | None:
    """Retorna o nível de classificação conhecido para `nome_campo`, ou
    None se o campo não estiver catalogado em CLASSIFICACAO_CAMPOS_PADRAO
    — nunca adivinha um nível para campo desconhecido."""
    if not nome_campo:
        return None
    return CLASSIFICACAO_CAMPOS_PADRAO.get(nome_campo.strip().lower())


_MASCARA = "***REDACTED***"

# Padrões "label = valor" / "label: valor" — mascaram só o valor, mantendo
# o rótulo (label) intacto pra não perder contexto de depuração.
_SECRET_LABEL_PATTERNS = [
    re.compile(r"(?i)([a-z_\-]*(senha|password|pwd)[a-z_\-]*\s*[:=]\s*[\"']?)([^\s\"',}]+)"),
    re.compile(r"(?i)([a-z_\-]*token[a-z_\-]*\s*[:=]\s*[\"']?)([^\s\"',}]+)"),
    re.compile(r"(?i)([a-z_\-]*api[_-]?key[a-z_\-]*\s*[:=]\s*[\"']?)([^\s\"',}]+)"),
    re.compile(r"(?i)(authorization\s*[:=]\s*[\"']?)([^\r\n\"']+)"),
]

# Padrões que aparecem sozinhos no texto, sem um rótulo "campo=" na frente.
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+\S+")
_RAW_KEY_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"),       # OpenAI/Anthropic/DeepSeek-style
    re.compile(r"\bAIza[0-9A-Za-z_\-]{10,}\b"),   # Google/Gemini-style
    re.compile(r"\bgsk_[A-Za-z0-9]{10,}\b"),      # Groq
]


def redigir_segredos(texto: str) -> str:
    """Mascara senha/token/Authorization header/API key em texto livre.
    Nunca levanta exceção, nunca remove o texto inteiro — só substitui o
    valor do segredo por `***REDACTED***`. Texto sem nenhum padrão
    suspeito volta inalterado."""
    if not texto:
        return texto or ""

    resultado = texto
    for padrao in _SECRET_LABEL_PATTERNS:
        resultado = padrao.sub(lambda m: f"{m.group(1)}{_MASCARA}", resultado)
    resultado = _BEARER_PATTERN.sub(f"Bearer {_MASCARA}", resultado)
    for padrao in _RAW_KEY_PATTERNS:
        resultado = padrao.sub(_MASCARA, resultado)
    return resultado


_CHAVES_SECRETAS_EXATAS = {
    "senha", "password", "pwd", "token", "access_token", "refresh_token",
    "oauth_token", "oauth_token_encrypted", "api_key", "apikey",
    "authorization", "client_secret", "secret", "smtp_pass",
}


def _chave_e_secreta(chave: str) -> bool:
    chave_lower = (chave or "").lower()
    if chave_lower in _CHAVES_SECRETAS_EXATAS:
        return True
    return any(termo in chave_lower for termo in ("token", "senha", "password", "api_key", "api-key"))


def redigir_dict(dados):
    """Percorre dict/list recursivamente mascarando valores de chaves
    reconhecidas como secretas (ver _CHAVES_SECRETAS_EXATAS) e aplicando
    `redigir_segredos` em toda string restante. Mesmo estilo de
    caminhada recursiva de `api/ai_router.py::_sanitize_ai_payload`."""
    if isinstance(dados, dict):
        return {
            chave: (_MASCARA if _chave_e_secreta(chave) else redigir_dict(valor))
            for chave, valor in dados.items()
        }
    if isinstance(dados, list):
        return [redigir_dict(item) for item in dados]
    if isinstance(dados, str):
        return redigir_segredos(dados)
    return dados
