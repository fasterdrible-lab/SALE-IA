"""
api/metricas_historico.py — Histórico de métricas em SQLite (rolling 24h).

Armazena um snapshot por minuto com:
  - latência do banco
  - modo do banco (mysql / sqlite)
  - reuniões ativas (últimos 5 min)
  - reuniões criadas hoje

Deduplicação por DB-level: se já existe uma linha nos últimos 55s, a escrita é ignorada.
Isso garante apenas 1 snapshot/min mesmo com 2 workers uvicorn.
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "metricas.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def criar_tabela_metricas() -> None:
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS metricas_historico (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ts              REAL    NOT NULL,
                banco_latencia  REAL,
                banco_modo      TEXT,
                reunioes_ativas INTEGER,
                reunioes_hoje   INTEGER,
                chamadas_ia     INTEGER,
                falhas_ia       INTEGER
            )
        """)
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mh_ts ON metricas_historico(ts)"
        )


def registrar(
    banco: dict,
    reunioes_ativas: int,
    reunioes_hoje: int,
    chamadas_ia: int = 0,
    falhas_ia: int = 0,
) -> bool:
    """
    Insere snapshot e limpa linhas com mais de 25h.
    Retorna False se já existe uma linha nos últimos 55s (dedup multi-worker).
    """
    agora = time.time()
    with _conn() as db:
        recente = db.execute(
            "SELECT 1 FROM metricas_historico WHERE ts > ? LIMIT 1",
            (agora - 55,),
        ).fetchone()
        if recente:
            return False
        db.execute(
            """INSERT INTO metricas_historico
               (ts, banco_latencia, banco_modo, reunioes_ativas, reunioes_hoje, chamadas_ia, falhas_ia)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                agora,
                banco.get("latencia_ms"),
                banco.get("banco"),
                reunioes_ativas,
                reunioes_hoje,
                chamadas_ia,
                falhas_ia,
            ),
        )
        db.execute(
            "DELETE FROM metricas_historico WHERE ts < ?",
            (agora - 25 * 3600,),
        )
    return True


def obter(horas: int = 6) -> list[dict]:
    """Retorna snapshots das últimas N horas, ordem crescente."""
    horas = max(1, min(horas, 24))
    limite = time.time() - horas * 3600
    with _conn() as db:
        rows = db.execute(
            "SELECT * FROM metricas_historico WHERE ts >= ? ORDER BY ts ASC",
            (limite,),
        ).fetchall()
    return [dict(r) for r in rows]
