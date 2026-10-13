"""
Testes — Groq como 5º provedor de IA (13/10/2026) e o botão "Definir como
principal" das Configurações mudando a ordem real do roteador.

Nenhuma chamada de rede: o caller da Groq é substituído.

Run:
    python -m unittest tests.test_groq_provider -v
"""
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from api import ai_router
from api.pricing_catalog import obter_preco
from agent.data_classification_rules import redigir_segredos


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._state_original = ai_router.STATE_FILE
        ai_router.STATE_FILE = Path(self._tmp.name) / "ai_provider_order.json"
        self.addCleanup(setattr, ai_router, "STATE_FILE", self._state_original)
        ai_router.resetar_estado_ia_para_testes()
        # O .env local tem token real do Telegram: "IA fora do ar" não pode sair daqui.
        p = patch("agent.alertas.alertar", lambda *a, **k: None)
        p.start()
        self.addCleanup(p.stop)

    def salvar_ordem(self, ordem):
        ai_router.STATE_FILE.write_text(json.dumps({"order": ordem}), encoding="utf-8")


class TestGroqNoRoteador(_Base):
    def test_groq_registrada_com_modelo_padrao_e_no_fim_da_ordem_padrao(self):
        p = ai_router.PROVIDERS["groq"]
        self.assertEqual((p.env_keys, p.model_env, p.default_model),
                         (("GROQ_API_KEY",), "GROQ_MODEL", "openai/gpt-oss-120b"))
        self.assertEqual(ai_router.DEFAULT_PROVIDER_ORDER[-1], "groq")
        self.assertIn("groq", ai_router.snapshot_metricas()["por_provedor"])

    def test_ordem_salva_antiga_ganha_a_groq_no_fim(self):
        # data/ai_provider_order.json de produção tem só os 4 de antes
        self.salvar_ordem(["deepseek", "openai", "anthropic", "gemini"])
        self.assertEqual(ai_router.ordem_provedores(), ["deepseek", "openai", "anthropic", "gemini", "groq"])

    def test_ordem_salva_pelo_painel_depois_da_groq_fica_como_esta(self):
        ai_router.STATE_FILE.write_text(json.dumps({"order": ["openai", "deepseek"],
                                                    "conhecidos": sorted(ai_router.PROVIDERS)}), encoding="utf-8")
        self.assertEqual(ai_router.ordem_provedores(), ["openai", "deepseek"])

    def test_ao_salvar_registra_os_provedores_conhecidos(self):
        ai_router.definir_provedor_preferido("gemini")
        payload = json.loads(ai_router.STATE_FILE.read_text(encoding="utf-8"))
        self.assertIn("groq", payload["conhecidos"])
        self.assertEqual(payload["order"][0], "gemini")

    def test_ordem_explicita_do_env_e_respeitada(self):
        with patch.dict(os.environ, {"AI_PROVIDER_ORDER": "openai,deepseek"}):
            self.assertEqual(ai_router.ordem_provedores(), ["openai", "deepseek"])

    def test_groq_atende_quando_os_outros_falham(self):
        def falha(*a):
            raise RuntimeError("402 sem saldo")

        provs = {n: replace(ai_router.PROVIDERS[n], caller=falha) for n in ("deepseek", "openai", "anthropic", "gemini")}
        provs["groq"] = replace(ai_router.PROVIDERS["groq"], caller=lambda *a: ({"ok": True}, None))
        self.salvar_ordem(["deepseek", "openai", "anthropic", "gemini"])
        env = {"DEEPSEEK_API_KEY": "k" * 12, "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "",
               "GOOGLE_API_KEY": "", "GROQ_API_KEY": "gsk_" + "x" * 20, "GROQ_LLM_ATIVO": "true", "GROQ_MODEL": ""}
        with patch.dict(os.environ, env), patch.object(ai_router, "PROVIDERS", provs):
            os.environ.pop("GROQ_MODEL")
            r = ai_router.chamar_ia("sistema", "conteúdo")
        self.assertEqual((r["_provedor_ia"], r["_modelo_ia"]), ("groq", "openai/gpt-oss-120b"))

    def test_desligar_a_groq_como_ia_nao_apaga_a_chave_da_transcricao(self):
        chamadas = []
        provs = dict(ai_router.PROVIDERS)
        provs["groq"] = replace(ai_router.PROVIDERS["groq"], caller=lambda *a: chamadas.append(1) or ({"ok": True}, None))
        env = {"GROQ_API_KEY": "gsk_" + "x" * 20, "GROQ_LLM_ATIVO": "false", "AI_PROVIDER_ORDER": "groq"}
        with patch.dict(os.environ, env), patch.object(ai_router, "PROVIDERS", provs):
            self.assertEqual(ai_router.status_provedores()["groq"]["status"], "desligado")
            falhas_antes = ai_router.snapshot_metricas()["por_provedor"]["groq"]["falha"]
            with self.assertRaises(Exception):
                ai_router.chamar_ia("sistema", "conteúdo")
            self.assertEqual(chamadas, [])
            self.assertEqual(ai_router.snapshot_metricas()["por_provedor"]["groq"]["falha"], falhas_antes)  # não conta falha
            self.assertEqual(os.environ["GROQ_API_KEY"], "gsk_" + "x" * 20)

    def test_chave_groq_nunca_aparece_em_erro_nem_em_log(self):
        erro = ai_router._safe_error(RuntimeError("Invalid API Key gsk_abcDEF1234567890xyz"))
        self.assertNotIn("gsk_abcDEF", erro)
        self.assertNotIn("gsk_abcDEF", redigir_segredos("falhou com gsk_abcDEF1234567890xyz agora"))

    def test_preco_da_groq_no_catalogo(self):
        p = obter_preco("groq", "openai/gpt-oss-120b")
        self.assertEqual((p.input_per_million, p.output_per_million, p.cached_input_per_million), (0.15, 0.60, 0.075))
        self.assertEqual(obter_preco("groq", "qwen/qwen3.8-27b").input_per_million, 0.15)


class TestConfiguracoesAdmin(_Base):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        import api.main as main

        self.main = main
        self.client = TestClient(main.app)
        self.h = {"Authorization": "Bearer " + main._gerar_token("adm", "adm@saleia.app.br", "admin")}
        env_tmp = Path(self._tmp.name) / ".env"
        env_tmp.write_text('GROQ_API_KEY="gsk_' + "y" * 20 + '"\n', encoding="utf-8")
        p = patch.object(main, "_env_path", lambda: env_tmp)
        p.start()
        self.addCleanup(p.stop)

    def test_groq_aparece_na_configuracao_de_apis(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_" + "y" * 20, "GROQ_LLM_ATIVO": "true"}):
            provs = {p["id"]: p for p in self.client.get("/admin/api/provedores", headers=self.h).json()["provedores"]}
        self.assertEqual((provs["groq"]["nome"], provs["groq"]["tem_chave"], provs["groq"]["ativo"]), ("Groq", True, True))

    def test_inativar_groq_desliga_so_a_ia(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_" + "y" * 20, "GROQ_LLM_ATIVO": "true"}):
            r = self.client.patch("/admin/api/provedores/groq/status", headers=self.h, json={"ativo": False})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(os.environ["GROQ_LLM_ATIVO"], "false")
            self.assertEqual(os.environ["GROQ_API_KEY"], "gsk_" + "y" * 20)
            provs = {p["id"]: p for p in self.client.get("/admin/api/provedores", headers=self.h).json()["provedores"]}
            self.assertFalse(provs["groq"]["ativo"])
            self.client.patch("/admin/api/provedores/groq/status", headers=self.h, json={"ativo": True})
            self.assertEqual(os.environ["GROQ_LLM_ATIVO"], "true")

    def test_definir_como_principal_muda_a_ordem_real(self):
        self.salvar_ordem(["deepseek", "openai", "anthropic", "gemini"])
        with patch.dict(os.environ, {}):
            r = self.client.post("/admin/api/principal", headers=self.h, json={"provedor": "groq"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(ai_router.ordem_provedores()[0], "groq")
            provs = self.client.get("/admin/api/provedores", headers=self.h).json()["provedores"]
        self.assertEqual([p["id"] for p in provs if p["principal"]], ["groq"])


if __name__ == "__main__":
    unittest.main()
