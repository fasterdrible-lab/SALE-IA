"""
Testes — agent/multiagente/bigfive_agent.py

Cobre o agente Big Five (inferência comportamental de personalidade a
partir da transcrição, sem questionário) — mesmo padrão de mock de
tests/test_multiagente_claude_fallback.py, mas no nível de
chamar_ia_com_fallback_claude (ponto de entrada real do agente).

Run:
    python -m unittest tests.test_bigfive_agent -v
"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from agent.multiagente.bigfive_agent import analisar_bigfive
from api import ai_features


class AnalisarBigfiveTest(unittest.TestCase):
    def _run(self, **kwargs):
        defaults = dict(
            transcricao_parcial="Cliente: prefiro decidir sozinho e ver os numeros antes.",
            historico="",
            perfil_bigfive_atual={},
            diagnostico_atual={},
            usuario_id="u1",
            meeting_id="m1",
        )
        defaults.update(kwargs)
        return asyncio.run(analisar_bigfive(**defaults))

    def test_usa_feature_realtime_bigfive(self):
        with patch(
            "agent.multiagente.bigfive_agent.chamar_ia_com_fallback_claude",
            new=AsyncMock(return_value={"perfil_bigfive": {"abertura": 70}}),
        ) as mock_chamar:
            resultado = self._run()

        self.assertEqual(resultado, {"perfil_bigfive": {"abertura": 70}})
        _, kwargs = mock_chamar.call_args
        self.assertEqual(kwargs.get("feature"), ai_features.REALTIME_BIGFIVE)
        self.assertEqual(kwargs.get("meeting_id"), "m1")

    def test_placeholders_substituidos_no_prompt(self):
        with patch(
            "agent.multiagente.bigfive_agent.chamar_ia_com_fallback_claude",
            new=AsyncMock(return_value={}),
        ) as mock_chamar:
            self._run(
                transcricao_parcial="TRECHO_UNICO_XYZ",
                perfil_bigfive_atual={"abertura": 55},
            )

        args, _ = mock_chamar.call_args
        _system, prompt, *_ = args
        self.assertIn("TRECHO_UNICO_XYZ", prompt)
        self.assertIn(json.dumps({"abertura": 55}, ensure_ascii=False), prompt)
        self.assertNotIn("{transcricao_parcial}", prompt)
        self.assertNotIn("{perfil_bigfive_atual}", prompt)

    def test_prompt_nunca_recebe_signo_ou_astrologia(self):
        with patch(
            "agent.multiagente.bigfive_agent.chamar_ia_com_fallback_claude",
            new=AsyncMock(return_value={}),
        ) as mock_chamar:
            self._run()

        args, _ = mock_chamar.call_args
        _system, prompt, *_ = args
        # nenhum placeholder de astrologia foi substituido (nao existe no
        # template) — confirma que o agente nao tem canal de entrada para
        # dado astrologico nenhum.
        self.assertNotIn("perfil_astrologico", prompt.lower())


if __name__ == "__main__":
    unittest.main()
