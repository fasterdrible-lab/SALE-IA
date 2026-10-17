"""
Módulo de gerenciamento de sessões em tempo real.
Salva transcrições acumuladas e análises da IA no MySQL para
revisão posterior no dashboard.
"""
import json
import logging
import os

import pymysql

logger = logging.getLogger(__name__)

# Teto só de segurança: MEDIUMTEXT guarda 16 MB (~4M caracteres em utf8mb4)
# e 3h de reunião dão ~200 mil. O teto antigo de 60 mil cortava o início
# de 58 das 63 reuniões medidas em 11/10/2026.
LIMITE_TRANSCRICAO_SESSAO = 2_000_000


def acumular_transcricao(atual: str | None, parcial: str) -> str:
    """Anexa o trecho novo; acima do teto, descarta o início."""
    return ((atual or "") + "\n\n" + parcial)[-LIMITE_TRANSCRICAO_SESSAO:]


def _get_conn():
    required = ("DB_HOST", "DB_USER", "DB_PASS", "DB_NAME")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Variaveis de banco ausentes: {', '.join(missing)}")

    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        connect_timeout=10,
    )


def criar_tabela_sessoes():
    """Cria a tabela sessoes se não existir."""
    sql = """
    CREATE TABLE IF NOT EXISTS sessoes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        meeting_id VARCHAR(200) NOT NULL,
        transcricao_acumulada MEDIUMTEXT,
        ultima_analise JSON,
        disc_identificado VARCHAR(10),
        num_analises INT DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_meeting (meeting_id),
        INDEX idx_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        conn.close()
        logger.info("[Sessões] Tabela sessoes criada/verificada.")
    except Exception as e:
        logger.error("[Sessões] Erro ao criar tabela: %s", e)


# Sessão ativa = atualizada nas últimas 6h. Era "criada nas últimas 6h":
# reunião mais longa que isso parava de gravar sem erro (auditoria T01, P4).
_SQL_SESSAO_ATIVA = """SELECT id, transcricao_acumulada, num_analises FROM sessoes
                       WHERE meeting_id = %s AND updated_at >= NOW() - INTERVAL 6 HOUR
                       ORDER BY updated_at DESC LIMIT 1"""


def salvar_analise(meeting_id: str, transcricao_parcial: str, analise: dict):
    """
    Salva a última análise da IA na sessão ativa (cria a sessão se não
    houver). Não mexe na transcrição: antes anexava `transcricao_parcial`
    — a janela das últimas 60 falas — a cada ciclo, 2x por ciclo, e 83%
    das linhas de `sessoes` eram repetição (auditoria T01, P1). A
    transcrição entra só por `salvar_transcricao_bruta`. O parâmetro fica
    pela compatibilidade dos chamadores.
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(_SQL_SESSAO_ATIVA, (meeting_id,))
            row = cur.fetchone()

            analise = analise or {}
            disc = (analise.get("perfil_disc") or {}).get("tipo", "") or ""
            analise_json = json.dumps(analise, ensure_ascii=False)

            if row:
                sessao_id, _transcricao, num = row
                cur.execute(
                    """UPDATE sessoes
                       SET ultima_analise = %s,
                           disc_identificado = %s,
                           num_analises = %s,
                           updated_at = NOW()
                       WHERE id = %s""",
                    (analise_json, disc, (num or 0) + 1, sessao_id),
                )
                logger.info("[Sessões] Sessão %s atualizada (análise #%s).", sessao_id, (num or 0) + 1)
            else:
                cur.execute(
                    """INSERT INTO sessoes
                       (meeting_id, transcricao_acumulada, ultima_analise, disc_identificado, num_analises)
                       VALUES (%s, '', %s, %s, 1)""",
                    (meeting_id, analise_json, disc),
                )
                logger.info("[Sessões] Nova sessão criada para meeting_id=%s.", meeting_id)

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("[Sessões] Erro ao salvar análise: %s", e)


def listar_sessoes(limite: int = 200) -> list:
    """Lista sessões mais recentes com preview da transcrição.

    Enriquece cada sessão com cliente/empresa vinculados (client_meetings +
    client_profiles, Sales Brain Fase 4) quando existir, para permitir busca
    por cliente no dashboard sem precisar de coluna nova em `sessoes`.
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT s.id, s.meeting_id, s.disc_identificado, s.num_analises,
                          s.created_at, s.updated_at, s.encerrada_em,
                          LEFT(s.transcricao_acumulada, 300) AS preview,
                          (SELECT cp.nome FROM client_meetings cm
                             JOIN client_profiles cp ON cp.id = cm.client_id
                            WHERE cm.meeting_id = s.meeting_id
                            ORDER BY cm.data DESC LIMIT 1) AS cliente_nome,
                          (SELECT cp.empresa FROM client_meetings cm
                             JOIN client_profiles cp ON cp.id = cm.client_id
                            WHERE cm.meeting_id = s.meeting_id
                            ORDER BY cm.data DESC LIMIT 1) AS cliente_empresa
                   FROM sessoes s
                   ORDER BY s.created_at DESC
                   LIMIT %s""",
                (limite,),
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        # Serializar datetimes
        for r in rows:
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
        return rows
    except Exception as e:
        logger.error("[Sessões] Erro ao listar: %s", e)
        return []


def _limpar_e_deduplicar(meeting_id: str, atual: str, parcial: str) -> str:
    """Mesmas regras da MeetingMemory (auditoria T01, P2): sem texto de
    tela, sem legenda parcial, sem reenvio do mesmo delta e sem a segunda
    cópia da fala que veio do áudio."""
    from agent.transcript_dedup_rules import compactar_transcricao, deduplicar_fragmento

    corpos_audio: set = set()
    try:
        from api.database import corpos_de_audio_recentes
        corpos_audio = corpos_de_audio_recentes(meeting_id)
    except Exception as e:
        logger.debug("[Sessões] sem corpos de áudio: %s", e)
    limpo = compactar_transcricao(parcial or "")
    aceito, _ = deduplicar_fragmento(atual or "", limpo, corpos_audio=corpos_audio)
    return aceito


def salvar_transcricao_bruta(meeting_id: str, transcricao_parcial: str):
    """Salva/atualiza transcrição ANTES do GPT, para garantir persistência.
    Só o que é fala nova entra (`_limpar_e_deduplicar`)."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(_SQL_SESSAO_ATIVA, (meeting_id,))
            row = cur.fetchone()
            if row:
                sessao_id, atual, _num = row
                aceito = _limpar_e_deduplicar(meeting_id, atual, transcricao_parcial)
                if not aceito:
                    conn.close()
                    return
                nova = acumular_transcricao(atual, aceito)
                cur.execute(
                    "UPDATE sessoes SET transcricao_acumulada = %s, updated_at = NOW(), encerrada_em = NULL WHERE id = %s",
                    (nova, sessao_id),
                )
            # Sessão não existe (foi deletada ou nunca criada): não recriar aqui.
            # A criação acontece exclusivamente via registrar_sessao() chamado pelo content.js.
        conn.commit()
        conn.close()
        logger.info("[Sessões] Transcrição bruta salva para meeting_id=%s.", meeting_id)
    except Exception as e:
        logger.error("[Sessões] Erro ao salvar transcrição bruta: %s", e)


def deletar_sessao(sessao_id: int) -> bool:
    """Remove a sessão pelo ID. Retorna True se deletada."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessoes WHERE id = %s", (sessao_id,))
            afetadas = cur.rowcount
        conn.commit()
        conn.close()
        logger.info("[Sessões] Sessão %s deletada.", sessao_id)
        return afetadas > 0
    except Exception as e:
        logger.error("[Sessões] Erro ao deletar sessão %s: %s", sessao_id, e)
        return False


def obter_ultima_analise(meeting_id: str) -> dict:
    """Retorna a última análise salva para o meeting_id (sessão ativa nas últimas 6h)."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT ultima_analise, disc_identificado, num_analises, updated_at
                   FROM sessoes
                   WHERE meeting_id = %s AND updated_at >= NOW() - INTERVAL 6 HOUR
                   ORDER BY updated_at DESC LIMIT 1""",
                (meeting_id,),
            )
            row = cur.fetchone()
        conn.close()
        if not row:
            return {}
        analise_raw, disc, num, updated_at = row
        analise = {}
        if analise_raw:
            analise = json.loads(analise_raw) if isinstance(analise_raw, str) else analise_raw
        analise["_meta"] = {
            "meeting_id": meeting_id,
            "disc": disc,
            "num_analises": num,
            "updated_at": updated_at.isoformat() if updated_at else None,
        }
        return analise
    except Exception as e:
        logger.error("[Sessões] Erro ao obter análise: %s", e)
        return {}


def registrar_sessao(meeting_id: str) -> int:
    """
    Cria uma sessão vazia imediatamente ao iniciar a extensão no Meet.
    Retorna o id da sessão criada (ou existente se o mesmo meeting_id
    já foi registrado na última hora).
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(_SQL_SESSAO_ATIVA, (meeting_id,))
            row = cur.fetchone()
            if row:
                # V.1.4.181: voltou para a reunião (ou recarregou a página).
                cur.execute("UPDATE sessoes SET encerrada_em = NULL, updated_at = updated_at WHERE id = %s", (row[0],))
                conn.commit()
                conn.close()
                return row[0]
            cur.execute(
                """INSERT INTO sessoes (meeting_id, transcricao_acumulada, num_analises)
                   VALUES (%s, '', 0)""",
                (meeting_id,),
            )
            sessao_id = cur.lastrowid
        conn.commit()
        conn.close()
        logger.info("[Sessões] Sessão %s pré-registrada para meeting_id=%s.", sessao_id, meeting_id)
        return sessao_id
    except Exception as e:
        logger.error("[Sessões] Erro ao registrar sessão: %s", e)
        return 0


def migrar_colunas_embedding_metadata_base_conhecimento():
    """Garante que a tabela base_conhecimento exista com as colunas de
    metadados de embedding (provider/model/dim). Não há criar_tabela_*
    centralizada para base_conhecimento hoje (só existia via o CREATE TABLE
    inline aqui) — esta função cobre tanto bases novas quanto a migração de
    bases existentes, e deve ser chamada no startup independente de alguém
    já ter exportado uma sessão."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS base_conhecimento (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    titulo VARCHAR(255) NOT NULL,
                    tipo VARCHAR(50) DEFAULT 'reuniao',
                    texto MEDIUMTEXT NOT NULL,
                    embedding JSON,
                    embedding_provider VARCHAR(20),
                    embedding_model VARCHAR(100),
                    embedding_dim INT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_tipo (tipo),
                    INDEX idx_created (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            for nome, tipo_sql in (
                ("embedding_provider", "VARCHAR(20)"),
                ("embedding_model", "VARCHAR(100)"),
                ("embedding_dim", "INT"),
                # Arquivo original preservado à parte do texto extraído (download na Base).
                # Nulos para documentos legados que só têm texto — sem arquivo para baixar.
                ("arquivo_nome_original", "VARCHAR(255)"),
                ("arquivo_path", "VARCHAR(500)"),
                ("arquivo_mime", "VARCHAR(100)"),
                ("arquivo_tamanho", "INT"),
            ):
                cur.execute("SHOW COLUMNS FROM base_conhecimento LIKE %s", (nome,))
                if cur.fetchone() is None:
                    cur.execute(f"ALTER TABLE base_conhecimento ADD COLUMN {nome} {tipo_sql}")
                    logger.info("[Base] Coluna %s adicionada à tabela base_conhecimento.", nome)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("[Base] Erro ao migrar colunas de metadados de embedding: %s", e)


def exportar_para_base_conhecimento(sessao_id: int, titulo: str = "", tipo: str = "reuniao") -> dict:
    """
    Exporta a transcrição acumulada de uma sessão para a base de conhecimento da IA.
    Gera embedding via o EmbeddingProvider configurado e insere na tabela
    base_conhecimento. Se a geração do embedding falhar, a linha ainda é
    salva sem embedding (mesmo padrão de degradação graciosa de POST /base)
    em vez de falhar a exportação inteira.
    """
    import json as _json

    from services.embeddings import get_embedding_provider

    try:
        # Buscar transcrição da sessão
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT transcricao_acumulada, meeting_id FROM sessoes WHERE id = %s",
                (sessao_id,),
            )
            row = cur.fetchone()
        conn.close()

        if not row or not row[0]:
            return {"ok": False, "erro": "Sessão não encontrada ou transcrição vazia"}

        transcricao, meeting_id = row
        titulo_final = titulo or f"Reunião {meeting_id}"
        chars = len(transcricao)

        embedding_json = None
        embedding_provider = embedding_model = embedding_dim = None
        try:
            provider = get_embedding_provider()
            resultado = provider.embed(transcricao[:8000])
            if resultado is not None:
                embedding_json = _json.dumps(resultado.vector)
                embedding_provider = resultado.provider
                embedding_model = resultado.model
                embedding_dim = resultado.dimension
            else:
                logger.warning("[Base] Embedding não gerado para sessão %s — salvando sem embedding.", sessao_id)
        except Exception as e:
            logger.warning("[Base] Erro ao gerar embedding para sessão %s, salvando sem: %s", sessao_id, e)

        # Inserir na base_conhecimento
        migrar_colunas_embedding_metadata_base_conhecimento()
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO base_conhecimento
                   (titulo, tipo, texto, embedding, embedding_provider, embedding_model, embedding_dim)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (titulo_final, tipo, transcricao, embedding_json,
                 embedding_provider, embedding_model, embedding_dim),
            )
            novo_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Invalidar cache do RAG
        try:
            from agent.base_conhecimento import invalidar_cache
            invalidar_cache()
        except Exception:
            pass

        logger.info("[Base] Sessão %s exportada para base_conhecimento id=%s (%s chars).", sessao_id, novo_id, chars)
        return {"ok": True, "id": novo_id, "chars": chars}
    except Exception as e:
        logger.error("[Base] Erro ao exportar sessão %s: %s", sessao_id, e)
        return {"ok": False, "erro": str(e)}


def criar_tabela_usuarios():
    """Cria a tabela usuarios se não existir."""
    sql = """
    CREATE TABLE IF NOT EXISTS usuarios (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        nome VARCHAR(200) NOT NULL,
        email VARCHAR(200) NOT NULL,
        senha_hash VARCHAR(255) NOT NULL,
        perfil VARCHAR(50) NOT NULL DEFAULT 'operador',
        plano VARCHAR(50) NOT NULL DEFAULT 'free',
        status VARCHAR(50) NOT NULL DEFAULT 'pendente',
        data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
        ultimo_acesso DATETIME NULL,
        UNIQUE INDEX idx_email (email),
        INDEX idx_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        conn.close()
        logger.info("[Auth] Tabela usuarios criada/verificada.")
    except Exception as e:
        logger.error("[Auth] Erro ao criar tabela usuarios: %s", e)


def migrar_colunas_sessoes():
    """V.1.4.181: `encerrada_em` — o vendedor saiu da chamada. Antes a
    sessão só deixava de aparecer "Ao vivo" no Dashboard 5 min depois do
    último envio, e uma aba esquecida aberta seguia "ao vivo"."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            try:
                cur.execute("ALTER TABLE sessoes ADD COLUMN encerrada_em DATETIME NULL DEFAULT NULL")
                conn.commit()
            except Exception:
                conn.rollback()  # coluna já existe
            # V.1.4.185: relatório pós-reunião automático (api/relatorio_automatico.py).
            try:
                cur.execute("ALTER TABLE sessoes ADD COLUMN relatorio_status VARCHAR(20) NULL DEFAULT NULL")
                # Só quando a coluna nasce: as sessões que já existiam não geram
                # relatório sozinhas (testes de 15-16/10 virariam cliente falso).
                cur.execute("UPDATE sessoes SET relatorio_status = 'anterior', updated_at = updated_at")
                conn.commit()
            except Exception:
                conn.rollback()
            for sql in ("ALTER TABLE sessoes ADD COLUMN relatorio_em DATETIME NULL DEFAULT NULL",
                        "ALTER TABLE sessoes ADD COLUMN relatorio_detalhe VARCHAR(200) NULL DEFAULT NULL",
                        # V.1.4.186: "quem é quem" (agent/participantes_rules.py).
                        "ALTER TABLE sessoes ADD COLUMN participantes_json TEXT NULL"):
                try:
                    cur.execute(sql)
                    conn.commit()
                except Exception:
                    conn.rollback()
        conn.close()
    except Exception as e:
        logger.error("[Sessões] Erro ao migrar colunas de sessoes: %s", e)


def salvar_participantes(meeting_id: str, participantes_json: str) -> bool:
    """V.1.4.186: guarda o "quem é quem" na sessão ativa (só se mudou).
    Não mexe em `updated_at` nem reabre sessão encerrada."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sessoes SET participantes_json = %s, updated_at = updated_at
                   WHERE id = (SELECT id FROM (SELECT id FROM sessoes WHERE meeting_id = %s
                               AND updated_at >= NOW() - INTERVAL 6 HOUR
                               ORDER BY updated_at DESC LIMIT 1) AS ativa)
                     AND NOT (participantes_json <=> %s)""",
                (participantes_json, meeting_id, participantes_json),
            )
            mudou = cur.rowcount > 0
        conn.commit()
        conn.close()
        return mudou
    except Exception as e:
        logger.error("[Sessões] Erro ao salvar participantes: %s", e)
        return False


def obter_participantes(meeting_id: str) -> str:
    """JSON do "quem é quem" da sessão mais recente da reunião ('' se não há)."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT participantes_json FROM sessoes WHERE meeting_id = %s
                   ORDER BY updated_at DESC LIMIT 1""",
                (meeting_id,),
            )
            row = cur.fetchone()
        conn.close()
        return (row[0] or "") if row else ""
    except Exception as e:
        logger.debug("[Sessões] sem participantes para %s: %s", meeting_id, e)
        return ""


def encerrar_sessao(meeting_id: str) -> bool:
    """Marca a sessão ativa da reunião como encerrada (vendedor saiu da
    chamada ou fechou a aba). Não mexe em `updated_at`. Qualquer fala nova
    ou a extensão abrindo de novo na reunião reabre (encerrada_em = NULL)."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(_SQL_SESSAO_ATIVA, (meeting_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return False
            cur.execute(
                "UPDATE sessoes SET encerrada_em = NOW(), updated_at = updated_at WHERE id = %s",
                (row[0],),
            )
        conn.commit()
        conn.close()
        logger.info("[Sessões] Sessão %s encerrada (meeting_id=%s).", row[0], meeting_id)
        return True
    except Exception as e:
        logger.error("[Sessões] Erro ao encerrar sessão: %s", e)
        return False


def migrar_colunas_usuarios():
    """Adiciona colunas de reset de senha à tabela usuarios se ainda não existirem."""
    alteracoes = [
        "ALTER TABLE usuarios ADD COLUMN reset_token VARCHAR(128) NULL DEFAULT NULL",
        "ALTER TABLE usuarios ADD COLUMN reset_token_exp DATETIME NULL DEFAULT NULL",
    ]
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            for sql in alteracoes:
                try:
                    cur.execute(sql)
                    conn.commit()
                except Exception:
                    # coluna já existe — ignorar
                    conn.rollback()
        conn.close()
        logger.info("[Auth] Colunas reset_token e reset_token_exp verificadas.")
    except Exception as e:
        logger.error("[Auth] Erro ao migrar colunas de reset: %s", e)


def obter_transcricao_mais_recente(meeting_id: str) -> str:
    """Retorna a transcrição acumulada mais recente para um meeting_id (sem limite de 6h).

    Usado pelo piloto Claude Account Mode (analisar reunião sob demanda),
    diferente de salvar_analise/obter_ultima_analise que só olham sessões
    ativas nas últimas 6h.
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT transcricao_acumulada FROM sessoes
                   WHERE meeting_id = %s
                   ORDER BY created_at DESC LIMIT 1""",
                (meeting_id,),
            )
            row = cur.fetchone()
        conn.close()
        return (row[0] if row else "") or ""
    except Exception as e:
        logger.error("[Sessões] Erro ao obter transcrição por meeting_id=%s: %s", meeting_id, e)
        return ""


def buscar_sessao(sessao_id: int) -> dict:
    """Busca sessão completa pelo ID incluindo transcrição e análise."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, meeting_id, transcricao_acumulada, ultima_analise,
                          disc_identificado, num_analises, created_at, updated_at
                   FROM sessoes WHERE id = %s""",
                (sessao_id,),
            )
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
        conn.close()
        if not row:
            return {}
        d = dict(zip(cols, row))
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        if d.get("ultima_analise") and isinstance(d["ultima_analise"], str):
            try:
                d["ultima_analise"] = json.loads(d["ultima_analise"])
            except Exception:
                pass
        return d
    except Exception as e:
        logger.error("[Sessões] Erro ao buscar sessão %s: %s", sessao_id, e)


def obter_nomes_usuarios(ids: list) -> dict:
    """Busca nome/email/plano de usuários por id, para enriquecer agregados
    de custo de IA (Cost Intelligence Fase 2/3 — `plano` alimenta a margem
    por plano da Fase 3).

    Recebe uma lista de ids (pode conter None, que é ignorado) e devolve
    {id: {"nome": ..., "email": ..., "plano": ...}}. Lista vazia não bate
    no banco.
    """
    ids_validos = [i for i in (ids or []) if i]
    if not ids_validos:
        return {}
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(ids_validos))
            cur.execute(
                f"SELECT id, nome, email, plano FROM usuarios WHERE id IN ({placeholders})",
                tuple(ids_validos),
            )
            rows = cur.fetchall()
        conn.close()
        return {str(uid): {"nome": nome, "email": email, "plano": plano} for uid, nome, email, plano in rows}
    except Exception as e:
        logger.error("[Sessões] Erro ao obter nomes de usuarios: %s", e)
        return {}


def usuario_esta_ativo(usuario_id: str) -> bool:
    """Tarefa B8: usado antes de renovar o token da extensão — usuário
    inativado/excluído nunca tem a sessão estendida. Banco indisponível
    → False (na dúvida, não renova; o token atual segue válido até
    expirar)."""
    if not usuario_id:
        return False
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM usuarios WHERE id = %s", (usuario_id,))
            row = cur.fetchone()
        conn.close()
        return bool(row) and row[0] == "ativo"
    except Exception as e:
        logger.error("[Sessões] Erro ao checar status do usuario: %s", e)
        return False


def obter_usuarios_ativos_por_plano() -> dict:
    """Conta usuários com status='ativo' agrupados por plano (Cost
    Intelligence Fase 3 — base de "usuários ativos" da margem por plano).

    Devolve {plano: total}. Nunca lanca excecao — degrada para {} se o
    banco estiver indisponivel (mesmo padrao dos demais helpers deste
    modulo).
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT plano, COUNT(*) FROM usuarios WHERE status = 'ativo' GROUP BY plano")
            rows = cur.fetchall()
        conn.close()
        return {plano: total for plano, total in rows}
    except Exception as e:
        logger.error("[Sessões] Erro ao contar usuarios ativos por plano: %s", e)
        return {}


def obter_clientes_por_reunioes(meeting_ids: list) -> dict:
    """Busca cliente/empresa vinculados a uma lista de meeting_ids (client_meetings +
    client_profiles), mesma técnica de subquery de `listar_sessoes`, para enriquecer
    a tabela de "reuniões mais caras" do Cost Intelligence.

    Devolve {meeting_id: {"cliente_nome": ..., "cliente_empresa": ...}}.
    """
    ids_validos = [m for m in (meeting_ids or []) if m]
    if not ids_validos:
        return {}
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(ids_validos))
            cur.execute(
                f"""SELECT cm.meeting_id, cp.nome, cp.empresa
                    FROM client_meetings cm
                    JOIN client_profiles cp ON cp.id = cm.client_id
                    WHERE cm.meeting_id IN ({placeholders})
                    ORDER BY cm.data DESC""",
                tuple(ids_validos),
            )
            rows = cur.fetchall()
        conn.close()
        resultado = {}
        for meeting_id, nome, empresa in rows:
            # ORDER BY cm.data DESC + só grava se ainda não existe -> mantém o mais recente
            resultado.setdefault(meeting_id, {"cliente_nome": nome, "cliente_empresa": empresa})
        return resultado
    except Exception as e:
        logger.error("[Sessões] Erro ao obter clientes por reunioes: %s", e)
        return {}
        return {}
