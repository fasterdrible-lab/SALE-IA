"""
Testes — integração do agente Big Five em agent/multiagente/orquestrador.py

Cobre: _mesclar() inclui perfil_bigfive; o kill-switch
BIGFIVE_AGENT_ENABLED=false faz o agente nunca ser chamado (5º agente
skip completo, zero custo).

Mocka os 5 agentes + as 3 buscas de RAG (nunca toca MySQL/rede real).

Run:
    python -m unittest tests.test_orquestrador_bigfive -v
"""

import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, patch

logging.disable(logging.CRITICAL)

import agent.multiagente.orquestrador as orquestrador
from agent.multiagente.orquestrador import _mesclar, analisar_fragmento_multi, bigfive_agent_ativo


def _mock_rag():
    """Contexto para patchar as 3 buscas de RAG feitas no início de
    analisar_fragmento_multi — evita qualquer tentativa de conexão real
    com MySQL nos testes."""
    return (
        patch.object(orquestrador, "buscar_contexto_similar", new=AsyncMock(return_value=None)),
        patch("agent.sales_memory.buscar_contexto_para_reuniao", return_value=None),
        patch("api.database.buscar_conhecimento_compilado_similar", return_value=None),
    )


class MesclarIncluiBigFiveTest(unittest.TestCase):
    def test_mesclar_inclui_perfil_bigfive(self):
        resultado = _mesclar(
            coach={}, disc={}, finance={}, closer={},
            bigfive={"perfil_bigfive": {"abertura": 80, "confianca": "alta"}},
        )
        self.assertEqual(resultado["perfil_bigfive"], {"abertura": 80, "confianca": "alta"})

    def test_mesclar_bigfive_vazio_vira_dict_vazio(self):
        resultado = _mesclar(coach={}, disc={}, finance={}, closer={}, bigfive={})
        self.assertEqual(resultado["perfil_bigfive"], {})


class AnalisarFragmentoMultiBigFiveTest(unittest.TestCase):
    def _patches_agentes(self, bigfive_mock=None):
        return [
            patch.object(orquestrador, "analisar_coach", new=AsyncMock(return_value={})),
            patch.object(orquestrador, "analisar_disc", new=AsyncMock(return_value={})),
            patch.object(orquestrador, "analisar_finance", new=AsyncMock(return_value={})),
            patch.object(orquestrador, "analisar_closer", new=AsyncMock(return_value={})),
            patch.object(orquestrador, "analisar_bigfive", new=(bigfive_mock or AsyncMock(return_value={}))),
        ]

    def test_bigfive_ativo_por_padrao_e_resultado_inclui_perfil(self):
        bigfive_mock = AsyncMock(return_value={"perfil_bigfive": {"abertura": 65}})
        rag_patches = _mock_rag()
        agente_patches = self._patches_agentes(bigfive_mock)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BIGFIVE_AGENT_ENABLED", None)
            for p in (*rag_patches, *agente_patches):
                p.start()
            try:
                resultado = asyncio.run(analisar_fragmento_multi("transcricao", meeting_id="m1"))
            finally:
                for p in (*rag_patches, *agente_patches):
                    p.stop()

        bigfive_mock.assert_awaited()
        self.assertEqual(resultado["perfil_bigfive"], {"abertura": 65})

    def test_kill_switch_desativa_agente_bigfive_completamente(self):
        bigfive_mock = AsyncMock(return_value={"perfil_bigfive": {"abertura": 99}})
        rag_patches = _mock_rag()
        agente_patches = self._patches_agentes(bigfive_mock)
        with patch.dict(os.environ, {"BIGFIVE_AGENT_ENABLED": "false"}):
            self.assertFalse(bigfive_agent_ativo())
            for p in (*rag_patches, *agente_patches):
                p.start()
            try:
                resultado = asyncio.run(analisar_fragmento_multi("transcricao", meeting_id="m1"))
            finally:
                for p in (*rag_patches, *agente_patches):
                    p.stop()

        bigfive_mock.assert_not_awaited()
        self.assertEqual(resultado["perfil_bigfive"], {})


if __name__ == "__main__":
    unittest.main()
