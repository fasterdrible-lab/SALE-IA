"""
Testes — V.1.4.185: relatório pós-reunião automático.

Run:
    python -m unittest tests.test_relatorio_automatico -v
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from agent import relatorio_automatico_rules as r
from api import relatorio_automatico as svc

AGORA = datetime(2026, 10, 16, 18, 0, 0)
CONVERSA = "\n".join(
    f"{'Carlos' if i % 2 else 'Ana Souza'}: fala número {i} sobre o processo comercial, prazos e o orçamento do projeto."
    for i in range(30)
)


class RegrasTest(unittest.TestCase):
    def test_sessao_encerrada_espera_2_min(self):
        self.assertFalse(r.sessao_pronta(AGORA - timedelta(seconds=60), AGORA, AGORA))
        self.assertTrue(r.sessao_pronta(AGORA - timedelta(seconds=121), AGORA, AGORA))

    def test_extensao_antiga_vale_inatividade_de_30_min(self):
        self.assertFalse(r.sessao_pronta(None, AGORA - timedelta(minutes=20), AGORA))
        self.assertTrue(r.sessao_pronta(None, AGORA - timedelta(minutes=31), AGORA))
        self.assertFalse(r.sessao_pronta(None, None, AGORA))

    def test_reuniao_curta_ou_sem_falas_nao_gera(self):
        self.assertEqual(r.vale_gerar("")[0], False)
        self.assertEqual(r.vale_gerar("Vendedor: oi\nCliente: oi")[0], False)
        self.assertEqual(r.vale_gerar("x" * 5000)[0], False)  # muito texto, nenhuma fala
        self.assertEqual(r.vale_gerar(CONVERSA), (True, "ok"))

    def test_transcricao_longa_preserva_comeco_e_fim(self):
        texto = "INICIO " + "a" * 300_000 + " FIM"
        cortada = r.transcricao_para_relatorio(texto)
        self.assertLessEqual(len(cortada), r.LIMITE_CARACTERES + 100)
        self.assertTrue(cortada.startswith("INICIO"))
        self.assertTrue(cortada.endswith("FIM"))
        self.assertIn("omitido por tamanho", cortada)
        self.assertEqual(r.transcricao_para_relatorio("curta"), "curta")

    def test_kill_switch(self):
        self.assertTrue(r.habilitado({}))
        self.assertFalse(r.habilitado({"RELATORIO_AUTOMATICO_ENABLED": "false"}))


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.conn.sqls.append((sql, params))
        if sql.startswith("UPDATE sessoes SET relatorio_status = %s, relatorio_em = NOW()"):
            sid = params[1]
            st = self.conn.estado.get(sid)
            self.rowcount = 1 if st is None else 0
            if self.rowcount:
                self.conn.estado[sid] = "gerando"
        elif sql.startswith("UPDATE sessoes SET relatorio_status = %s, relatorio_detalhe"):
            self.conn.estado[params[2]] = params[0]
            self.conn.detalhe[params[2]] = params[1]

    def fetchall(self):
        return [s for s in self.conn.sessoes if self.conn.estado.get(s[0]) is None]


class _Conn:
    def __init__(self, sessoes):
        self.sessoes = sessoes
        self.estado = {}
        self.detalhe = {}
        self.sqls = []

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        pass

    def close(self):
        pass


class FilaTest(unittest.TestCase):
    def setUp(self):
        self.conn = _Conn([
            (1, "aaa-bbbb-ccc", AGORA, AGORA - timedelta(minutes=5)),       # encerrada há 5 min → gera
            (2, "ddd-eeee-fff", AGORA, None),                               # ao vivo → espera
            (3, "ggg-hhhh-iii", AGORA - timedelta(hours=1), None),          # extensão antiga parada → gera
            (4, "jjj-kkkk-lll", AGORA, AGORA - timedelta(minutes=10)),      # encerrada mas curta → pulada
        ])
        memorias = {
            "aaa-bbbb-ccc": {"transcript_full": CONVERSA, "usuario_id": "u1", "created_at": "2026-10-16T17:00:00"},
            "ggg-hhhh-iii": {"transcript_full": CONVERSA, "usuario_id": None, "created_at": "2026-10-16T16:00:00"},
            "jjj-kkkk-lll": {"transcript_full": "Vendedor: teste", "usuario_id": "u1", "created_at": None},
        }
        for p in (
            patch.object(svc, "_conn", lambda: self.conn),
            patch("api.database.obter_meeting_memory", side_effect=lambda m: memorias.get(m)),
            patch.dict("os.environ", {"RELATORIO_AUTOMATICO_ENABLED": "true"}),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.gerar = patch.object(svc, "gerar_relatorio", return_value={"_etapas_ok": ["cliente_oportunidade", "seller_dna"]}).start()
        self.addCleanup(patch.stopall)

    def test_gera_so_as_que_acabaram_e_pula_as_curtas(self):
        feitos = svc.processar_pendentes(max_por_vez=5, agora=AGORA)
        por_id = {f["sessao_id"]: f["status"] for f in feitos}
        self.assertEqual(por_id, {1: "ok", 3: "ok", 4: "pulado"})
        self.assertNotIn(2, self.conn.estado)  # reunião ao vivo nem foi reservada
        chamados = [c.args[2] for c in self.gerar.call_args_list]
        self.assertEqual(sorted(chamados), ["aaa-bbbb-ccc", "ggg-hhhh-iii"])
        self.assertEqual(self.gerar.call_args_list[0].args[3], "u1")  # dono vira vendedor da oportunidade
        self.assertIn("seller_dna", self.conn.detalhe[1])

    def test_uma_vez_por_sessao(self):
        svc.processar_pendentes(max_por_vez=5, agora=AGORA)
        n = self.gerar.call_count
        svc.processar_pendentes(max_por_vez=5, agora=AGORA + timedelta(hours=1))
        self.assertEqual(self.gerar.call_count, n)

    def test_limite_por_volta(self):
        feitos = svc.processar_pendentes(max_por_vez=1, agora=AGORA)
        self.assertEqual(len(feitos), 1)

    def test_erro_na_geracao_marca_erro_e_segue(self):
        self.gerar.side_effect = RuntimeError("IA fora")
        feitos = svc.processar_pendentes(max_por_vez=5, agora=AGORA)
        self.assertIn("erro", {f["status"] for f in feitos})
        self.assertEqual(self.conn.estado[1], "erro")

    def test_desligado_nao_faz_nada(self):
        with patch.dict("os.environ", {"RELATORIO_AUTOMATICO_ENABLED": "false"}):
            self.assertEqual(svc.processar_pendentes(agora=AGORA), [])
        self.gerar.assert_not_called()


class _ConnMigracao:
    """ALTER falha se a coluna já existe (como no MySQL)."""
    def __init__(self, colunas):
        self.colunas = set(colunas)
        self.sqls = []

    def cursor(self):
        conn = self

        class C:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def execute(s, sql, params=None):
                conn.sqls.append(sql)
                if sql.startswith("ALTER TABLE sessoes ADD COLUMN"):
                    col = sql.split("ADD COLUMN")[1].split()[0]
                    if col in conn.colunas:
                        raise RuntimeError("Duplicate column")
                    conn.colunas.add(col)
        return C()

    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


class MigracaoTest(unittest.TestCase):
    def test_sessoes_existentes_viram_anterior_so_quando_a_coluna_nasce(self):
        from agent import sessao_manager
        conn = _ConnMigracao(["encerrada_em"])
        with patch.object(sessao_manager, "_get_conn", return_value=conn):
            sessao_manager.migrar_colunas_sessoes()
        self.assertEqual(sum("relatorio_status = 'anterior'" in s for s in conn.sqls), 1)
        self.assertTrue({"relatorio_status", "relatorio_em", "relatorio_detalhe"} <= conn.colunas)
        conn.sqls.clear()
        with patch.object(sessao_manager, "_get_conn", return_value=conn):
            sessao_manager.migrar_colunas_sessoes()  # 2º restart: nada é remarcado
        self.assertFalse(any("'anterior'" in s for s in conn.sqls))

    def test_laco_proprio_no_startup(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent / "api" / "main.py").read_text(encoding="utf-8")
        self.assertIn("asyncio.create_task(_loop_relatorio_automatico())", src)
        self.assertIn("await asyncio.to_thread(processar_pendentes)", src)


if __name__ == "__main__":
    unittest.main()
