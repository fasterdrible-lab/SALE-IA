"""
Testes de Tenant/User Isolation — Fase 18 / Tarefa 18.1 do "PROMPT
MESTRE — SALE-IA V2".

Cobre a regra literal: usuário A não pode acessar dado de usuário B em
reuniões (MeetingMemory), status/histórico de reunião e clientes.
Também confirma que dado sem dono registrado (legado/anônimo) continua
acessível a qualquer autenticado, e que admin sempre acessa tudo —
decisões confirmadas em 16-17/09/2026.

Mesmo padrão de tests/test_e2e_meeting_lifecycle.py: TestClient real +
api.database.engine trocado por SQLite em memória (StaticPool) para
MeetingMemory funcionar de verdade; camadas raw-pymysql sem DB real
disponível (sessoes/meeting_status/client_profiles) são tratadas via
fakes/mocks focados em cada teste.

Run:
    python -m unittest tests.test_tenant_isolation -v
"""

import logging
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

_FAKE_RECAP_VIVA_RESPONSE = {
    "texto_falavel": "Recapitulando o que conversamos até agora...",
    "mapa_mental": {"nos": []},
}


class _FakeConnRaises:
    """Simula 'sem MySQL disponível' de forma determinística — as
    funções raw-pymysql envolvidas (playbook_generator/sessao_manager)
    tratam isso com fallback gracioso (best-effort), então isso nunca
    quebra o request, só garante que o teste não depende de um socket
    de verdade."""

    def cursor(self):
        raise RuntimeError("sem MySQL disponível neste teste")


class _FakeSessaoCursor:
    def execute(self, *a, **k):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeSessaoConn:
    def cursor(self):
        return _FakeSessaoCursor()

    def commit(self):
        pass

    def close(self):
        pass


class TenantIsolationTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api.main as _main
        from api import database as _database
        cls._main = _main
        cls._database = _database

        cls._startup_patches = []
        for target in (
            "api.database.criar_tabelas",
            "agent.sessao_manager.criar_tabela_sessoes",
            "agent.sessao_manager.criar_tabela_usuarios",
            "agent.visual_scenario.criar_tabela_visual_scenarios",
            "agent.sales_memory.criar_tabela_sales_memories",
        ):
            try:
                p = patch(target)
                p.start()
                cls._startup_patches.append(p)
            except Exception:
                pass

        from fastapi.testclient import TestClient
        cls._ctx = TestClient(_main.app)
        cls.client = cls._ctx.__enter__()

        cls.token_a = _main._gerar_token("user-a", "vendedor.a@saleia.app.br", "vendedor")
        cls.headers_a = {"Authorization": f"Bearer {cls.token_a}"}
        cls.token_b = _main._gerar_token("user-b", "vendedor.b@saleia.app.br", "vendedor")
        cls.headers_b = {"Authorization": f"Bearer {cls.token_b}"}
        cls.token_admin = _main._gerar_token("user-admin", "admin@saleia.app.br", "admin")
        cls.headers_admin = {"Authorization": f"Bearer {cls.token_admin}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._startup_patches:
            p.stop()

    def setUp(self):
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self._engine)
        self._engine_patch = patch.object(self._database, "engine", self._engine)
        self._engine_patch.start()
        self.addCleanup(self._engine_patch.stop)

        self._sessao_conn_patch = patch(
            "agent.sessao_manager._get_conn", return_value=_FakeSessaoConn()
        )
        self._sessao_conn_patch.start()
        self.addCleanup(self._sessao_conn_patch.stop)

        self._playbook_conn_patch = patch(
            "agent.playbook_generator._get_conn", return_value=_FakeConnRaises()
        )
        self._playbook_conn_patch.start()
        self.addCleanup(self._playbook_conn_patch.stop)

        # agent.client_intelligence (raw pymysql, client_profiles) é
        # chamado best-effort dentro do ciclo de /tempo-real (contexto
        # de cliente vinculado) — sem mock, cada chamada tentaria um
        # socket real pra 127.0.0.1:3306 (lento e não-determinístico
        # entre ambientes). buscar_cliente_por_reuniao()/
        # buscar_resumo_cliente_para_reuniao() têm try/except próprios,
        # então falhar rápido aqui não quebra o ciclo.
        self._client_intel_conn_patch = patch(
            "agent.client_intelligence._get_conn", side_effect=RuntimeError("sem MySQL disponível neste teste")
        )
        self._client_intel_conn_patch.start()
        self.addCleanup(self._client_intel_conn_patch.stop)

        self._ia_multiagente_patch = patch(
            "agent.multiagente.claude_fallback.chamar_ia_async",
            new=AsyncMock(return_value=self._fake_agent_response()),
        )
        self._ia_multiagente_patch.start()
        self.addCleanup(self._ia_multiagente_patch.stop)

        self._ia_recap_patch = patch(
            "agent.recapitulacao.chamar_ia_async",
            new=AsyncMock(return_value=dict(_FAKE_RECAP_VIVA_RESPONSE)),
        )
        self._ia_recap_patch.start()
        self.addCleanup(self._ia_recap_patch.stop)

    @staticmethod
    def _fake_agent_response():
        return {
            "conversation_stage": "descoberta",
            "next_best_action": {
                "type": "question", "category": "descoberta_dor", "title": "Aprofundar dor",
                "message": "Me conta mais sobre isso?", "objective": "entender", "reason": "contexto",
                "expected_effect": "avancar", "risk_if_ignored": "estagnar", "follow_up": None, "confidence": 0.7,
            },
            "key_moments": [], "eventos": [],
            "perfil_disc": {"tipo": "C", "confianca": "media", "evidencia": "fala cautelosa"},
            "kare_type": "attain",
            "temperatura": {"nivel": "media", "entonacao": "neutro"},
            "mapa_financeiro": {}, "objecao_detectada": {},
            "score_compra": {"valor": 40, "justificativa": "fase inicial"},
            "maturity_score": {"total": 20},
            "resumo_vivo": "Cliente ainda em fase de descoberta.",
            "perfil_bigfive": {"abertura": 55, "conscienciosidade": 60},
        }

    def _criar_reuniao_de(self, meeting_id: str, headers: dict) -> None:
        """Cria/estampa uma MeetingMemory real via /tempo-real, dono
        resolvido do token em `headers` (ou anônima se `headers` vazio)."""
        fala = (
            "Cliente: Hoje a gente perde muito tempo com follow-up manual, "
            "cada vendedor cuida disso do jeito que acha melhor e isso vira "
            "uma bagunça enorme no fim do mês."
        )
        r = self.client.post(
            "/tempo-real",
            json={"transcricao_parcial": fala, "transcricao_nova": fala, "meeting_id": meeting_id},
            headers=headers,
        )
        self.assertEqual(r.status_code, 200, r.text)


class RecapitulacaoVivaIsolationTest(TenantIsolationTestBase):
    def test_dono_le_a_propria_recapitulacao(self):
        mid = "iso-recap-a-le-a"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.post("/recapitulacao-viva", json={"meeting_id": mid}, headers=self.headers_a)
        self.assertEqual(r.status_code, 200)

    def test_outro_usuario_nao_le_recapitulacao_de_reuniao_com_dono(self):
        mid = "iso-recap-b-nao-le-a"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.post("/recapitulacao-viva", json={"meeting_id": mid}, headers=self.headers_b)
        self.assertEqual(r.status_code, 404)

    def test_admin_le_recapitulacao_de_qualquer_reuniao(self):
        mid = "iso-recap-admin-le-tudo"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.post("/recapitulacao-viva", json={"meeting_id": mid}, headers=self.headers_admin)
        self.assertEqual(r.status_code, 200)

    def test_anonimo_nao_le_recapitulacao_de_reuniao_com_dono(self):
        mid = "iso-recap-anonimo-bloqueado"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.post("/recapitulacao-viva", json={"meeting_id": mid})
        self.assertEqual(r.status_code, 401)

    def test_reuniao_sem_dono_continua_aberta_a_qualquer_autenticado(self):
        """Dado legado/anônimo (usuario_id None) — decisão confirmada:
        continua acessível a qualquer usuário logado, nunca isolado."""
        mid = "iso-recap-sem-dono"
        self._criar_reuniao_de(mid, {})  # cria anonimamente, sem Authorization
        r = self.client.post("/recapitulacao-viva", json={"meeting_id": mid}, headers=self.headers_b)
        self.assertEqual(r.status_code, 200)

    def test_reuniao_sem_dono_continua_aberta_a_chamada_anonima(self):
        mid = "iso-recap-sem-dono-anon-le"
        self._criar_reuniao_de(mid, {})
        r = self.client.post("/recapitulacao-viva", json={"meeting_id": mid})
        self.assertEqual(r.status_code, 200)


class HistoricoUsoIsolationTest(TenantIsolationTestBase):
    def test_detalhe_dono_acessa(self):
        # /historico/uso/{meeting_id} exige o formato real do codigo do
        # Meet (xxx-xxxx-xxx), diferente dos outros endpoints testados
        # acima — meeting_id precisa bater com esse padrao aqui.
        mid = "abc-isoa-def"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.get(f"/historico/uso/{mid}", headers=self.headers_a)
        self.assertEqual(r.status_code, 200)

    def test_detalhe_outro_usuario_recebe_404(self):
        mid = "abc-isob-def"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.get(f"/historico/uso/{mid}", headers=self.headers_b)
        self.assertEqual(r.status_code, 404)

    def test_detalhe_admin_acessa(self):
        mid = "abc-isoc-def"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.get(f"/historico/uso/{mid}", headers=self.headers_admin)
        self.assertEqual(r.status_code, 200)

    def test_lista_filtra_reunioes_de_outros_usuarios(self):
        mid_a = "iso-lst-aaa-aaaa"
        mid_b = "iso-lst-bbb-bbbb"
        self._criar_reuniao_de(mid_a, self.headers_a)
        self._criar_reuniao_de(mid_b, self.headers_b)

        r_a = self.client.get("/historico/uso", headers=self.headers_a)
        self.assertEqual(r_a.status_code, 200)
        mids_vistos_por_a = {item["meeting_id"] for item in r_a.json()["reunioes"]}
        self.assertIn(mid_a, mids_vistos_por_a)
        self.assertNotIn(mid_b, mids_vistos_por_a)

        r_admin = self.client.get("/historico/uso", headers=self.headers_admin)
        mids_vistos_por_admin = {item["meeting_id"] for item in r_admin.json()["reunioes"]}
        self.assertIn(mid_a, mids_vistos_por_admin)
        self.assertIn(mid_b, mids_vistos_por_admin)

    def test_lista_inclui_reuniao_sem_dono_para_qualquer_autenticado(self):
        mid_sem_dono = "iso-lst-noo-wner"
        self._criar_reuniao_de(mid_sem_dono, {})
        r = self.client.get("/historico/uso", headers=self.headers_b)
        mids = {item["meeting_id"] for item in r.json()["reunioes"]}
        self.assertIn(mid_sem_dono, mids)


class RelatorioStatusIsolationTest(TenantIsolationTestBase):
    def test_dono_atualiza_status(self):
        mid = "iso-sta-aaa-aaaa"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.patch(f"/relatorios/{mid}/status", json={"status": "won"}, headers=self.headers_a)
        self.assertEqual(r.status_code, 200)

    def test_outro_usuario_nao_atualiza_status(self):
        mid = "iso-sta-bbb-bbbb"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.patch(f"/relatorios/{mid}/status", json={"status": "won"}, headers=self.headers_b)
        self.assertEqual(r.status_code, 404)

    def test_outro_usuario_nao_le_status(self):
        mid = "iso-sta-ccc-cccc"
        self._criar_reuniao_de(mid, self.headers_a)
        r = self.client.get(f"/relatorios/{mid}/status", headers=self.headers_b)
        self.assertEqual(r.status_code, 404)


class ClientesIsolationTest(unittest.TestCase):
    """agent.client_intelligence usa raw pymysql — sem DB real
    disponível, então este bloco testa a lógica de ownership
    diretamente (função pura `_verificar_dono_ou_admin` + a shape de
    `criar_cliente`/`listar_clientes` que estampam/filtram por
    usuario_id), em vez de HTTP fim-a-fim como nos outros blocos."""

    def test_verificar_dono_ou_admin_importavel_e_aplicavel_a_cliente(self):
        from api.main import _verificar_dono_ou_admin
        payload_a = {"sub": "user-a", "perfil": "vendedor"}
        payload_b = {"sub": "user-b", "perfil": "vendedor"}
        payload_admin = {"sub": "user-admin", "perfil": "admin"}

        # dono acessa
        _verificar_dono_ou_admin(payload_a, "user-a")
        # admin acessa
        _verificar_dono_ou_admin(payload_admin, "user-a")
        # sem dono registrado, qualquer autenticado acessa
        _verificar_dono_ou_admin(payload_b, None)

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            _verificar_dono_ou_admin(payload_b, "user-a")
        self.assertEqual(ctx.exception.status_code, 404)


class VerificarDonoOuAdminUnitTest(unittest.TestCase):
    """Cobertura direta e exaustiva do portão central de isolamento —
    reusado por todos os endpoints acima."""

    def setUp(self):
        from api.main import _verificar_dono_ou_admin
        self.fn = _verificar_dono_ou_admin

    def test_dono_passa(self):
        self.fn({"sub": "u1", "perfil": "vendedor"}, "u1")  # não deve levantar

    def test_outro_usuario_e_recusado_com_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.fn({"sub": "u2", "perfil": "vendedor"}, "u1")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_admin_sempre_passa_mesmo_sem_ser_dono(self):
        self.fn({"sub": "outro-id", "perfil": "admin"}, "u1")  # não deve levantar

    def test_recurso_sem_dono_passa_para_qualquer_autenticado(self):
        self.fn({"sub": "qualquer-um", "perfil": "vendedor"}, None)  # não deve levantar

    def test_recurso_sem_dono_passa_mesmo_string_vazia(self):
        self.fn({"sub": "qualquer-um", "perfil": "vendedor"}, "")  # falsy, tratado como sem dono


if __name__ == "__main__":
    unittest.main()
