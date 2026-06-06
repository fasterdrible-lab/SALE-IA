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


def salvar_analise(meeting_id: str, transcricao_parcial: str, analise: dict):
    """
    Salva ou atualiza a sessão com a transcrição acumulada e última análise.
    Se o meeting_id já existe e foi criado há menos de 6 horas, atualiza.
    Caso contrário, cria nova sessão.
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            # Verificar se existe sessão ativa (criada nas últimas 6 horas)
            cur.execute(
                """SELECT id, transcricao_acumulada, num_analises
                   FROM sessoes
                   WHERE meeting_id = %s
                   AND created_at >= NOW() - INTERVAL 6 HOUR
                   ORDER BY created_at DESC LIMIT 1""",
                (meeting_id,),
            )
            row = cur.fetchone()

            disc = (analise.get("perfil_disc") or {}).get("tipo", "") or ""
            analise_json = json.dumps(analise, ensure_ascii=False)

            if row:
                sessao_id, transcricao_atual, num = row
                # Acumular transcrição (limite de 60 000 chars)
                nova_transcricao = ((transcricao_atual or "") + "\n\n" + transcricao_parcial)
                nova_transcricao = nova_transcricao[-60000:]
                cur.execute(
                    """UPDATE sessoes
                       SET transcricao_acumulada = %s,
                           ultima_analise = %s,
                           disc_identificado = %s,
                           num_analises = %s,
                           updated_at = NOW()
                       WHERE id = %s""",
                    (nova_transcricao, analise_json, disc, (num or 0) + 1, sessao_id),
                )
                logger.info("[Sessões] Sessão %s atualizada (análise #%s).", sessao_id, (num or 0) + 1)
            else:
                cur.execute(
                    """INSERT INTO sessoes
                       (meeting_id, transcricao_acumulada, ultima_analise, disc_identificado, num_analises)
                       VALUES (%s, %s, %s, %s, 1)""",
                    (meeting_id, transcricao_parcial, analise_json, disc),
                )
                logger.info("[Sessões] Nova sessão criada para meeting_id=%s.", meeting_id)

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("[Sessões] Erro ao salvar análise: %s", e)


def listar_sessoes(limite: int = 50) -> list:
    """Lista sessões mais recentes com preview da transcrição."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, meeting_id, disc_identificado, num_analises,
                          created_at, updated_at,
                          LEFT(transcricao_acumulada, 300) AS preview
                   FROM sessoes
                   ORDER BY created_at DESC
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


def salvar_transcricao_bruta(meeting_id: str, transcricao_parcial: str):
    """Salva/atualiza transcrição bruta ANTES do GPT, para garantir persistência."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, transcricao_acumulada FROM sessoes
                   WHERE meeting_id = %s AND created_at >= NOW() - INTERVAL 6 HOUR
                   ORDER BY created_at DESC LIMIT 1""",
                (meeting_id,),
            )
            row = cur.fetchone()
            if row:
                sessao_id, atual = row
                nova = ((atual or "") + "\n\n" + transcricao_parcial)[-60000:]
                cur.execute(
                    "UPDATE sessoes SET transcricao_acumulada = %s, updated_at = NOW() WHERE id = %s",
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
                   WHERE meeting_id = %s AND created_at >= NOW() - INTERVAL 6 HOUR
                   ORDER BY created_at DESC LIMIT 1""",
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
            cur.execute(
                """SELECT id FROM sessoes
                   WHERE meeting_id = %s AND created_at >= NOW() - INTERVAL 6 HOUR
                   LIMIT 1""",
                (meeting_id,),
            )
            row = cur.fetchone()
            if row:
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


def exportar_para_base_conhecimento(sessao_id: int, titulo: str = "", tipo: str = "reuniao") -> dict:
    """
    Exporta a transcrição acumulada de uma sessão para a base de conhecimento da IA.
    Gera embedding via text-embedding-3-small e insere na tabela base_conhecimento.
    """
    import json as _json
    import os
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

        # Gerar embedding via OpenAI
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        resp = client.embeddings.create(model="text-embedding-3-small", input=transcricao[:8000])
        embedding_json = _json.dumps(resp.data[0].embedding)

        # Inserir na base_conhecimento
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS base_conhecimento (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    titulo VARCHAR(255) NOT NULL,
                    tipo VARCHAR(50) DEFAULT 'reuniao',
                    texto MEDIUMTEXT NOT NULL,
                    embedding JSON,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_tipo (tipo),
                    INDEX idx_created (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute(
                """INSERT INTO base_conhecimento (titulo, tipo, texto, embedding)
                   VALUES (%s, %s, %s, %s)""",
                (titulo_final, tipo, transcricao, embedding_json),
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
        return {}
