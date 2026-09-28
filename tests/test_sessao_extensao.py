"""
Testes — Tarefa B8: sessão da extensão em /tempo-real
(api/main.py::_avaliar_sessao_extensao + auth_status/token_renovado).

Run:
    python -m unittest tests.test_sessao_extensao -v
"""
import logging
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt

logging.disable(logging.CRITICAL)

import api.main as _main  # noqa: E402


def _token(horas_restantes: float, sub="u1") -> str:
    payload = {"sub": sub, "email": "v@saleia.app.br", "perfil": "vendedor",
               "exp": datetime.now(timezone.utc) + timedelta(hours=horas_restantes)}
    return jwt.encode(payload, _main._JWT_SECRET, algorithm=_main._JWT_ALGO)


class AvaliarSessaoTest(unittest.TestCase):
    def test_sem_header_e_anonimo(self):
        self.assertEqual(_main._avaliar_sessao_extensao(None),
                         {"usuario_id": None, "auth_status": "anonimo", "token_renovado": None})
        self.assertEqual(_main._avaliar_sessao_extensao("Basic abc")["auth_status"], "anonimo")

    def test_expirado(self):
        s = _main._avaliar_sessao_extensao("Bearer " + _token(-1))
        self.assertEqual((s["auth_status"], s["usuario_id"], s["token_renovado"]), ("expirado", None, None))

    def test_invalido(self):
        s = _main._avaliar_sessao_extensao("Bearer nao-e-um-jwt")
        self.assertEqual((s["auth_status"], s["usuario_id"]), ("invalido", None))

    def test_valido_longe_de_expirar_nao_renova(self):
        with patch("agent.sessao_manager.usuario_esta_ativo") as ativo:
            s = _main._avaliar_sessao_extensao("Bearer " + _token(60))
        self.assertEqual((s["auth_status"], s["usuario_id"], s["token_renovado"]), ("ok", "u1", None))
        ativo.assert_not_called()

    def test_perto_de_expirar_usuario_ativo_renova_por_72h(self):
        with patch("agent.sessao_manager.usuario_esta_ativo", return_value=True):
            s = _main._avaliar_sessao_extensao("Bearer " + _token(5))
        self.assertIsNotNone(s["token_renovado"])
        novo = jwt.decode(s["token_renovado"], _main._JWT_SECRET, algorithms=[_main._JWT_ALGO])
        self.assertEqual((novo["sub"], novo["perfil"]), ("u1", "vendedor"))
        restante = datetime.fromtimestamp(novo["exp"], tz=timezone.utc) - datetime.now(timezone.utc)
        self.assertGreater(restante, timedelta(hours=71))

    def test_perto_de_expirar_usuario_inativo_nao_renova(self):
        with patch("agent.sessao_manager.usuario_esta_ativo", return_value=False):
            s = _main._avaliar_sessao_extensao("Bearer " + _token(5))
        self.assertEqual((s["auth_status"], s["token_renovado"]), ("ok", None))

    def test_falha_ao_checar_usuario_nunca_lanca(self):
        with patch("agent.sessao_manager.usuario_esta_ativo", side_effect=RuntimeError("mysql fora")):
            s = _main._avaliar_sessao_extensao("Bearer " + _token(5))
        self.assertEqual((s["auth_status"], s["usuario_id"], s["token_renovado"]), ("ok", "u1", None))


class TempoRealAuthStatusTest(unittest.TestCase):
    def _chamar(self, authorization):
        req = _main.TempoRealRequest(transcricao_parcial="Cliente: fala qualquer", meeting_id="m1")
        with patch("api.processador_tempo_real.processar_fragmento_tempo_real",
                   new=AsyncMock(return_value={"next_best_action": {}})) as proc, \
             patch("agent.sessao_manager.salvar_transcricao_bruta"), \
             patch("agent.sessao_manager.salvar_analise"), \
             patch("agent.sessao_manager.usuario_esta_ativo", return_value=True):
            import asyncio
            resultado = asyncio.run(_main.analisar_tempo_real(req, authorization=authorization))
        return resultado, proc.call_args.kwargs["usuario_id"]

    def test_anonimo(self):
        r, uid = self._chamar(None)
        self.assertEqual((r["auth_status"], uid), ("anonimo", None))
        self.assertNotIn("token_renovado", r)

    def test_expirado_segue_analisando_como_anonimo(self):
        r, uid = self._chamar("Bearer " + _token(-1))
        self.assertEqual((r["auth_status"], uid), ("expirado", None))
        self.assertIn("next_best_action", r)

    def test_ok_com_renovacao(self):
        r, uid = self._chamar("Bearer " + _token(3))
        self.assertEqual((r["auth_status"], uid), ("ok", "u1"))
        self.assertIn("token_renovado", r)


if __name__ == "__main__":
    unittest.main()
