"""
Testes — pipeline automático-com-aprovação do Sales Brain (Fase 7.3):
memórias/playbooks/skills auto-gerados nascem 'pending' e só entram em uso
real (RAG/skill_resolver) após aprovação — mesma rede de segurança do
Knowledge Compiler (DRAFT/APPROVED), atrás do kill-switch
SALES_BRAIN_AUTOPILOT_ENABLED.

Não requer MySQL: `_get_conn()` de cada módulo é substituído por uma
conexão fake que só registra as chamadas (mesmo padrão de
tests/test_base_download.py).

Run:
    python -m unittest tests.test_sales_brain_approval -v
"""
import logging
import os
import unittest
from unittest.mock import patch

logging.disable(logging.CRITICAL)

import agent.playbook_generator as playbook_generator
import agent.sales_memory as sales_memory
import agent.skill_resolver as skill_resolver


class _RecordingCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecordingConn:
    def __init__(self):
        self.cursor_obj = _RecordingCursor()

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        pass

    def close(self):
        pass


class SalvarSkillStatusTest(unittest.TestCase):
    def test_status_pending_nasce_inativa(self):
        conn = _RecordingConn()
        with patch.object(skill_resolver, "_get_conn", return_value=conn):
            skill_resolver.salvar_skill({"name": "X", "status": "pending"})
        sql, params = conn.cursor_obj.calls[0]
        self.assertIn("status", sql)
        # is_active é o penúltimo-antepenúltimo campo antes de status na
        # tupla de VALUES — checa pelos valores, não pela posição exata.
        self.assertIn(0, params)  # is_active=0
        self.assertIn("pending", params)

    def test_status_default_aprovado_ativa_direto(self):
        conn = _RecordingConn()
        with patch.object(skill_resolver, "_get_conn", return_value=conn):
            skill_resolver.salvar_skill({"name": "X"})
        _, params = conn.cursor_obj.calls[0]
        self.assertIn(1, params)  # is_active=1
        self.assertIn("approved", params)


class SalvarPlaybookStatusTest(unittest.TestCase):
    def test_status_pending_nasce_inativo(self):
        conn = _RecordingConn()
        with patch.object(playbook_generator, "_get_conn", return_value=conn):
            playbook_generator.salvar_playbook({"name": "P", "status": "pending"})
        sql, params = conn.cursor_obj.calls[0]
        self.assertIn("status", sql)
        self.assertIn(0, params)
        self.assertIn("pending", params)

    def test_status_default_aprovado_ativa_direto(self):
        conn = _RecordingConn()
        with patch.object(playbook_generator, "_get_conn", return_value=conn):
            playbook_generator.salvar_playbook({"name": "P"})
        _, params = conn.cursor_obj.calls[0]
        self.assertIn(1, params)
        self.assertIn("approved", params)


class AutopilotFlagTest(unittest.TestCase):
    def test_default_ativo_sem_env(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SALES_BRAIN_AUTOPILOT_ENABLED", None)
            self.assertTrue(playbook_generator.autopilot_ativo())
            self.assertTrue(skill_resolver._autopilot_ativo())

    def test_false_desativa(self):
        with patch.dict(os.environ, {"SALES_BRAIN_AUTOPILOT_ENABLED": "false"}):
            self.assertFalse(playbook_generator.autopilot_ativo())
            self.assertFalse(skill_resolver._autopilot_ativo())

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"SALES_BRAIN_AUTOPILOT_ENABLED": "FALSE"}):
            self.assertFalse(playbook_generator.autopilot_ativo())


class GerarESalvarSkillStatusTest(unittest.TestCase):
    def test_skill_nasce_pending_com_autopilot_ativo(self):
        with patch.object(skill_resolver, "gerar_skill", return_value={"name": "S"}), \
             patch.object(skill_resolver, "salvar_skill", return_value="sid-1") as mock_salvar, \
             patch.dict(os.environ, {"SALES_BRAIN_AUTOPILOT_ENABLED": "true"}):
            skill_resolver.gerar_e_salvar_skill("contexto")
        skill_passado = mock_salvar.call_args[0][0]
        self.assertEqual(skill_passado["status"], "pending")

    def test_skill_nasce_aprovada_com_autopilot_desativado(self):
        with patch.object(skill_resolver, "gerar_skill", return_value={"name": "S"}), \
             patch.object(skill_resolver, "salvar_skill", return_value="sid-1") as mock_salvar, \
             patch.dict(os.environ, {"SALES_BRAIN_AUTOPILOT_ENABLED": "false"}):
            skill_resolver.gerar_e_salvar_skill("contexto")
        skill_passado = mock_salvar.call_args[0][0]
        self.assertEqual(skill_passado["status"], "approved")


class GerarESalvarPlaybookAutoSkillTest(unittest.TestCase):
    def test_autotrigger_skill_quando_autopilot_ativo(self):
        playbook_fake = {"name": "PB", "steps": ["passo 1"]}
        with patch.object(playbook_generator, "gerar_playbook", return_value=dict(playbook_fake)), \
             patch.object(playbook_generator, "salvar_playbook", return_value="pid-1"), \
             patch("agent.skill_resolver.gerar_e_salvar_skill") as mock_skill, \
             patch.dict(os.environ, {"SALES_BRAIN_AUTOPILOT_ENABLED": "true"}):
            pid = playbook_generator.gerar_e_salvar_playbook({}, "transcricao", "m1")
        self.assertEqual(pid, "pid-1")
        mock_skill.assert_called_once()
        self.assertEqual(mock_skill.call_args.kwargs.get("source_playbook_id"), "pid-1")

    def test_sem_autotrigger_quando_autopilot_desativado(self):
        with patch.object(playbook_generator, "gerar_playbook", return_value={"name": "PB"}), \
             patch.object(playbook_generator, "salvar_playbook", return_value="pid-2"), \
             patch("agent.skill_resolver.gerar_e_salvar_skill") as mock_skill, \
             patch.dict(os.environ, {"SALES_BRAIN_AUTOPILOT_ENABLED": "false"}):
            playbook_generator.gerar_e_salvar_playbook({}, "transcricao", "m1")
        mock_skill.assert_not_called()


class SalvarMemoriaStatusTest(unittest.TestCase):
    def test_salvar_memoria_default_e_approved(self):
        conn = _RecordingConn()
        with patch.object(sales_memory, "_get_conn", return_value=conn):
            sales_memory.salvar_memoria("objection", "T", "C")
        _, params = conn.cursor_obj.calls[0]
        self.assertIn("approved", params)

    def test_salvar_memorias_em_lote_default_e_pending(self):
        conn = _RecordingConn()
        memorias = [{"memory_type": "objection", "title": "T", "content": "C"}]
        with patch.object(sales_memory, "_get_conn", return_value=conn):
            ids = sales_memory.salvar_memorias_em_lote(memorias)
        self.assertEqual(len(ids), 1)
        _, params = conn.cursor_obj.calls[0]
        self.assertIn("pending", params)

    def test_lote_respeita_status_explicito_por_item(self):
        conn = _RecordingConn()
        memorias = [{"memory_type": "objection", "title": "T", "content": "C", "status": "approved"}]
        with patch.object(sales_memory, "_get_conn", return_value=conn):
            sales_memory.salvar_memorias_em_lote(memorias)
        _, params = conn.cursor_obj.calls[0]
        self.assertIn("approved", params)
        self.assertNotIn("pending", params)


class AtualizarStatusMemoriaTest(unittest.TestCase):
    def test_status_invalido_lanca(self):
        with self.assertRaises(ValueError):
            sales_memory.atualizar_status_memoria("id1", "pending")

    def test_aprovar_invalida_cache(self):
        conn = _RecordingConn()
        sales_memory._cache_memorias = {"vazio": False, "ids": ["x"]}
        self.addCleanup(setattr, sales_memory, "_cache_memorias", None)
        with patch.object(sales_memory, "_get_conn", return_value=conn):
            ok = sales_memory.atualizar_status_memoria("id1", "approved")
        self.assertTrue(ok)
        self.assertIsNone(sales_memory._cache_memorias)


class ListarMemoriasStatusFilterTest(unittest.TestCase):
    def test_filtro_default_aplica_approved(self):
        conn = _RecordingConn()
        with patch.object(sales_memory, "_get_conn", return_value=conn):
            sales_memory.listar_memorias()
        sql, params = conn.cursor_obj.calls[0]
        self.assertIn("status = %s", sql)
        self.assertIn("approved", params)

    def test_status_none_nao_filtra(self):
        conn = _RecordingConn()
        with patch.object(sales_memory, "_get_conn", return_value=conn):
            sales_memory.listar_memorias(status=None)
        sql, _ = conn.cursor_obj.calls[0]
        self.assertNotIn("status = %s", sql)


if __name__ == "__main__":
    unittest.main()
