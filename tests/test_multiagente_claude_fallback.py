"""
Testes — agent/multiagente/claude_fallback.py

Cobre o fallback do tempo real para a conta Claude do vendedor quando os
4 provedores centrais se esgotam (HTTPException 503 de api/ai_router.py).

Run:
    python -m unittest tests.test_multiagente_claude_fallback -v
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude


class ChamarIaComFallbackClaudeTest(unittest.TestCase):
    def _run(self, usuario_id=None, feature="teste"):
        return asyncio.run(
            chamar_ia_com_fallback_claude("system", "user", usuario_id, feature=feature)
        )

    def test_sucesso_normal_nao_toca_em_claude_account(self):
        with patch(
            "agent.multiagente.claude_fallback.chamar_ia_async",
            new=AsyncMock(return_value={"ok": True, "_provedor_ia": "deepseek"}),
        ):
            with patch("agent.claude_account.claude_pilot_habilitado") as mock_flag:
                resultado = self._run(usuario_id="user-a")

        mock_flag.assert_not_called()
        self.assertEqual(resultado, {"ok": True, "_provedor_ia": "deepseek"})

    def test_503_sem_usuario_id_relanca(self):
        with patch(
            "agent.multiagente.claude_fallback.chamar_ia_async",
            new=AsyncMock(side_effect=HTTPException(status_code=503, detail="fora do ar")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                self._run(usuario_id=None)

        self.assertEqual(ctx.exception.status_code, 503)

    def test_erro_nao_503_relanca_sem_tentar_fallback(self):
        with patch(
            "agent.multiagente.claude_fallback.chamar_ia_async",
            new=AsyncMock(side_effect=HTTPException(status_code=400, detail="bad request")),
        ):
            with patch("agent.claude_account.claude_pilot_habilitado") as mock_flag:
                with self.assertRaises(HTTPException) as ctx:
                    self._run(usuario_id="user-a")

        mock_flag.assert_not_called()
        self.assertEqual(ctx.exception.status_code, 400)

    def test_429_de_loop_caro_bloqueado_relanca_sem_tentar_fallback(self):
        """Decisao de design da Fase 5 (Cost Intelligence, api/otimizacao.py::
        verificar_loop_caro): o bloqueio de loop caro por reuniao usa 429,
        nao 503, exatamente para NAO acionar o fallback pra Conta Claude
        pessoal do vendedor — um loop caro bloqueado no orcamento central
        nao pode virar gasto na assinatura pessoal, isso derrotaria o
        proposito do bloqueio."""
        with patch(
            "agent.multiagente.claude_fallback.chamar_ia_async",
            new=AsyncMock(side_effect=HTTPException(
                status_code=429,
                detail={"erro": "Limite de custo de IA desta reuniao foi atingido."},
            )),
        ):
            with patch("agent.claude_account.claude_pilot_habilitado") as mock_flag:
                with self.assertRaises(HTTPException) as ctx:
                    self._run(usuario_id="user-a")

        mock_flag.assert_not_called()
        self.assertEqual(ctx.exception.status_code, 429)

    def test_503_com_usuario_id_mas_flag_desligada_relanca(self):
        with patch(
            "agent.multiagente.claude_fallback.chamar_ia_async",
            new=AsyncMock(side_effect=HTTPException(status_code=503, detail="fora do ar")),
        ):
            with patch("agent.claude_account.claude_pilot_habilitado", return_value=False):
                with self.assertRaises(HTTPException) as ctx:
                    self._run(usuario_id="user-a")

        self.assertEqual(ctx.exception.status_code, 503)

    def test_503_com_flag_ligada_mas_sem_conexao_ativa_relanca(self):
        with patch(
            "agent.multiagente.claude_fallback.chamar_ia_async",
            new=AsyncMock(side_effect=HTTPException(status_code=503, detail="fora do ar")),
        ):
            with patch("agent.claude_account.claude_pilot_habilitado", return_value=True):
                with patch("api.database.obter_claude_connection", return_value=None):
                    with self.assertRaises(HTTPException) as ctx:
                        self._run(usuario_id="user-a")

        self.assertEqual(ctx.exception.status_code, 503)

    def test_503_com_conexao_ativa_cai_no_fallback_claude(self):
        conexao = {"status": "ativo", "oauth_token_encrypted": "cripto"}
        with patch(
            "agent.multiagente.claude_fallback.chamar_ia_async",
            new=AsyncMock(side_effect=HTTPException(status_code=503, detail="fora do ar")),
        ):
            with patch("agent.claude_account.claude_pilot_habilitado", return_value=True):
                with patch("api.database.obter_claude_connection", return_value=conexao):
                    with patch(
                        "agent.claude_account.claude_account_executor.execute",
                        new=AsyncMock(return_value={"dores": ["dor-x"], "_custo_real_usd": 0.05}),
                    ) as mock_execute:
                        with patch("api.database.registrar_evento_uso_ia") as mock_registrar:
                            resultado = self._run(usuario_id="user-a", feature="realtime.coach")

        mock_execute.assert_awaited_once()
        _, kwargs = mock_execute.call_args
        self.assertEqual(kwargs["usuario_id"], "user-a")
        self.assertIn("system", kwargs["prompt"])
        self.assertIn("user", kwargs["prompt"])
        self.assertEqual(resultado["dores"], ["dor-x"])
        self.assertEqual(resultado["_provedor_ia"], "claude_account")

        mock_registrar.assert_called_once()
        reg_kwargs = mock_registrar.call_args.kwargs
        self.assertEqual(reg_kwargs["provider"], "claude_account")
        self.assertEqual(reg_kwargs["feature"], "realtime.coach")
        self.assertTrue(reg_kwargs["fallback_used"])
        self.assertEqual(reg_kwargs["cost_usd"], 0.05)

    def test_fallback_tambem_falhando_relanca_excecao_original(self):
        conexao = {"status": "ativo", "oauth_token_encrypted": "cripto"}
        with patch(
            "agent.multiagente.claude_fallback.chamar_ia_async",
            new=AsyncMock(side_effect=HTTPException(status_code=503, detail="fora do ar")),
        ):
            with patch("agent.claude_account.claude_pilot_habilitado", return_value=True):
                with patch("api.database.obter_claude_connection", return_value=conexao):
                    with patch(
                        "agent.claude_account.claude_account_executor.execute",
                        new=AsyncMock(side_effect=RuntimeError("claude tambem falhou")),
                    ):
                        with self.assertRaises(HTTPException) as ctx:
                            self._run(usuario_id="user-a")

        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
