"""
Testes de api/otimizacao.py (Cost Intelligence Fase 5 — ATIVA em
producao desde V.1.4.60, nao mais shadow mode).

Run:
    python -m unittest tests.test_otimizacao -v
"""

import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api import otimizacao as ot


class FlagsAtivoTest(unittest.TestCase):
    def test_default_e_ativo(self):
        with patch.dict(os.environ, {}, clear=False):
            for chave in ("OTIMIZACAO_CACHE_ATIVO", "OTIMIZACAO_CONTEXTO_ATIVO", "OTIMIZACAO_LOOP_ATIVO"):
                os.environ.pop(chave, None)
            self.assertTrue(ot.cache_ativo())
            self.assertTrue(ot.contexto_ativo())
            self.assertTrue(ot.loop_ativo())

    def test_false_desativa(self):
        with patch.dict(os.environ, {"OTIMIZACAO_CACHE_ATIVO": "false"}):
            self.assertFalse(ot.cache_ativo())
        with patch.dict(os.environ, {"OTIMIZACAO_CONTEXTO_ATIVO": "0"}):
            self.assertFalse(ot.contexto_ativo())
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_ATIVO": "False"}):
            self.assertFalse(ot.loop_ativo())


class CacheTest(unittest.TestCase):
    def setUp(self):
        ot._cache_respostas.clear()

    def test_sem_hit_devolve_none(self):
        self.assertIsNone(ot.buscar_no_cache("feat.x", "s", "u"))

    def test_guardar_e_buscar_devolve_copia_do_resultado(self):
        resultado = {"ok": True, "_custo_estimado_ia": 0.05}
        ot.guardar_no_cache("feat.x", "s", "u", resultado)
        achado = ot.buscar_no_cache("feat.x", "s", "u")
        self.assertEqual(achado, resultado)
        self.assertIsNot(achado, resultado)  # copia, nao a mesma referencia

    def test_conteudo_diferente_nao_bate(self):
        ot.guardar_no_cache("feat.x", "s", "u-A", {"ok": True})
        self.assertIsNone(ot.buscar_no_cache("feat.x", "s", "u-B"))

    def test_expira_fora_do_ttl(self):
        ot.guardar_no_cache("feat.x", "s", "u", {"ok": True})
        chave = ot._chave_cache("feat.x", "s", "u")
        ot._cache_respostas[chave]["ts"] -= (ot._CACHE_TTL_S + 1)
        self.assertIsNone(ot.buscar_no_cache("feat.x", "s", "u"))

    def test_desativado_nunca_guarda_nem_busca(self):
        with patch.dict(os.environ, {"OTIMIZACAO_CACHE_ATIVO": "false"}):
            ot.guardar_no_cache("feat.x", "s", "u", {"ok": True})
            self.assertIsNone(ot.buscar_no_cache("feat.x", "s", "u"))
        self.assertEqual(len(ot._cache_respostas), 0)

    def test_respeita_tamanho_maximo_lru(self):
        for i in range(ot._CACHE_MAX_ENTRIES + 10):
            ot.guardar_no_cache(f"feat.{i}", "s", f"u{i}", {"ok": True})
        self.assertLessEqual(len(ot._cache_respostas), ot._CACHE_MAX_ENTRIES)

    def test_registrar_cache_hit_nunca_lanca(self):
        with patch("api.database.registrar_decisao_otimizacao", side_effect=RuntimeError("boom")):
            try:
                ot.registrar_cache_hit(feature="f", meeting_id=None, system_prompt="s", custo_evitado_usd=0.01)
            except Exception as exc:  # pragma: no cover
                self.fail(f"registrar_cache_hit propagou excecao: {exc}")


class CorteContextoTest(unittest.TestCase):
    def test_abaixo_do_limite_nao_corta(self):
        with patch.dict(os.environ, {"OTIMIZACAO_CONTEXTO_MAX_CHARS": "1000"}):
            sp, uc, cortado = ot.aplicar_corte_contexto("s" * 100, "u" * 100)
        self.assertFalse(cortado)
        self.assertEqual(uc, "u" * 100)

    def test_acima_do_limite_corta_so_o_user_content(self):
        with patch.dict(os.environ, {"OTIMIZACAO_CONTEXTO_MAX_CHARS": "150"}):
            sp, uc, cortado = ot.aplicar_corte_contexto("S" * 100, "U" * 900)
        self.assertTrue(cortado)
        self.assertEqual(sp, "S" * 100)  # system_prompt NUNCA e cortado
        self.assertEqual(len(uc), 50)    # 150 - 100 = 50 chars sobram pro user_content
        self.assertTrue(all(c == "U" for c in uc))

    def test_corte_mantem_o_fim_do_conteudo_tail_slice(self):
        with patch.dict(os.environ, {"OTIMIZACAO_CONTEXTO_MAX_CHARS": "10"}):
            sp, uc, cortado = ot.aplicar_corte_contexto("", "0123456789ABCDEFGHIJ")
        self.assertTrue(cortado)
        self.assertEqual(uc, "ABCDEFGHIJ")  # mantem os ULTIMOS 10 chars, nao os primeiros

    def test_desativado_nunca_corta(self):
        with patch.dict(os.environ, {"OTIMIZACAO_CONTEXTO_ATIVO": "false", "OTIMIZACAO_CONTEXTO_MAX_CHARS": "10"}):
            sp, uc, cortado = ot.aplicar_corte_contexto("s", "u" * 1000)
        self.assertFalse(cortado)
        self.assertEqual(len(uc), 1000)

    def test_registrar_corte_contexto_nunca_lanca(self):
        with patch("api.database.registrar_decisao_otimizacao", side_effect=RuntimeError("boom")):
            try:
                ot.registrar_corte_contexto(
                    feature="f", meeting_id=None, provider="openai", model="gpt-4o",
                    system_prompt="s", custo_usd=0.01, chars_cortados=500,
                )
            except Exception as exc:  # pragma: no cover
                self.fail(f"registrar_corte_contexto propagou excecao: {exc}")


class LoopCaroTest(unittest.TestCase):
    def setUp(self):
        ot._custo_reuniao_cache.clear()

    def test_sem_limite_configurado_nunca_bloqueia(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTIMIZACAO_LOOP_MAX_CUSTO_USD", None)
            with patch("api.database.custo_por_reuniao", return_value={"total_usd": 999.0}):
                ot.verificar_loop_caro("m1", "realtime.coach", "s")  # nao deve lancar

    def test_sem_meeting_id_nunca_bloqueia(self):
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_MAX_CUSTO_USD": "1.0"}):
            ot.verificar_loop_caro(None, "realtime.coach", "s")  # nao deve lancar

    def test_abaixo_do_limite_nao_bloqueia(self):
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_MAX_CUSTO_USD": "10.0"}):
            with patch("api.database.custo_por_reuniao", return_value={"total_usd": 1.0}):
                ot.verificar_loop_caro("m1", "realtime.coach", "s")  # nao deve lancar

    def test_acima_do_limite_lanca_429_com_detalhe(self):
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_MAX_CUSTO_USD": "1.0"}):
            with patch("api.database.custo_por_reuniao", return_value={"total_usd": 5.0}):
                with patch("api.database.registrar_decisao_otimizacao"):
                    with self.assertRaises(HTTPException) as ctx:
                        ot.verificar_loop_caro("m1", "realtime.coach", "s")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("custo_acumulado_usd", ctx.exception.detail)
        self.assertEqual(ctx.exception.detail["limite_usd"], 1.0)

    def test_desativado_nunca_bloqueia_mesmo_acima_do_limite(self):
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_MAX_CUSTO_USD": "1.0", "OTIMIZACAO_LOOP_ATIVO": "false"}):
            with patch("api.database.custo_por_reuniao", return_value={"total_usd": 999.0}):
                ot.verificar_loop_caro("m1", "realtime.coach", "s")  # nao deve lancar

    def test_custo_por_reuniao_e_cacheado_60s(self):
        with patch.dict(os.environ, {"OTIMIZACAO_LOOP_MAX_CUSTO_USD": "100.0"}):
            with patch("api.database.custo_por_reuniao", return_value={"total_usd": 1.0}) as mock_custo:
                ot.verificar_loop_caro("m1", "f", "s")
                ot.verificar_loop_caro("m1", "f", "s")
                ot.verificar_loop_caro("m1", "f", "s")
        mock_custo.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
