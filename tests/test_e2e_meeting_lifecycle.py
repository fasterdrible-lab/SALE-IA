"""
Testes E2E — Fase 0 do "SALE-IA V2" (Tarefa 0.2): simula uma reunião
completa via TestClient (início -> transcrição -> MeetingMemory ->
análise -> next best action -> objeção -> recapitulação viva) e testes de
degradação controlada quando os provedores de IA falham.

Mocka só a camada de IA (agent.multiagente.claude_fallback.
chamar_ia_async, usado pelos 5 agentes do orquestrador, e
agent.recapitulacao.chamar_ia_async, usado pela recapitulação viva) —
nunca a lógica de persistência/orquestração real. `api.database.engine`
é trocado por SQLite em memória (mesmo padrão de
tests/test_admin_costs_endpoints.py) para que MeetingMemory funcione de
verdade dentro do teste.

Run:
    python -m unittest tests.test_e2e_meeting_lifecycle -v
"""

import json
import logging
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

logging.disable(logging.CRITICAL)

# Resposta mínima válida pros 5 agentes do orquestrador (Coach/DISC/
# Finance/Closer/BigFive) — mesmo dict pra qualquer um dos 5, já que o
# teste não valida conteúdo semântico, só que o ciclo persiste corretamente.
_FAKE_AGENT_RESPONSE = {
    "conversation_stage": "descoberta",
    "next_best_action": {
        "type": "question", "category": "descoberta_dor", "title": "Aprofundar dor",
        "message": "Me conta mais sobre isso?", "objective": "entender", "reason": "contexto",
        "expected_effect": "avancar", "risk_if_ignored": "estagnar", "follow_up": None, "confidence": 0.7,
    },
    "key_moments": [],
    "eventos": [],
    "perfil_disc": {"tipo": "C", "confianca": "media", "evidencia": "fala cautelosa"},
    "kare_type": "attain",
    "temperatura": {"nivel": "media", "entonacao": "neutro"},
    "mapa_financeiro": {},
    "objecao_detectada": {},
    "score_compra": {"valor": 40, "justificativa": "fase inicial"},
    "maturity_score": {"total": 20},
    "resumo_vivo": "Cliente ainda em fase de descoberta.",
    "perfil_bigfive": {"abertura": 55, "conscienciosidade": 60},
}

_FAKE_RECAP_VIVA_RESPONSE = {
    "texto_falavel": "Recapitulando o que conversamos até agora...",
    "mapa_mental": {"nos": []},
}


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


class MeetingLifecycleE2ETest(unittest.TestCase):
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
        cls.token = _main._gerar_token("u1", "vendedor@saleia.app.br", "vendedor")
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)
        for p in cls._startup_patches:
            p.stop()

    def setUp(self):
        # MeetingMemory (SQLModel) precisa de um engine de verdade — SQLite
        # em memória, StaticPool porque o TestClient roda numa thread
        # diferente desta.
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self._engine)
        self._engine_patch = patch.object(self._database, "engine", self._engine)
        self._engine_patch.start()
        self.addCleanup(self._engine_patch.stop)

        # agent.sessao_manager (raw pymysql, tabela sessoes legada) — sem
        # DB real disponível; fake connection não-destrutiva, sempre "sem
        # linha", pra manter o caminho best-effort rápido e determinístico.
        self._sessao_conn_patch = patch(
            "agent.sessao_manager._get_conn", return_value=_FakeSessaoConn()
        )
        self._sessao_conn_patch.start()
        self.addCleanup(self._sessao_conn_patch.stop)

        # Único ponto de entrada de IA dos 5 agentes do orquestrador.
        self._ia_multiagente = AsyncMock(return_value=dict(_FAKE_AGENT_RESPONSE))
        self._ia_multiagente_patch = patch(
            "agent.multiagente.claude_fallback.chamar_ia_async", new=self._ia_multiagente
        )
        self._ia_multiagente_patch.start()
        self.addCleanup(self._ia_multiagente_patch.stop)

        # Recapitulação viva usa chamar_ia_async importado direto em
        # agent/recapitulacao.py (caminho separado do multiagente).
        self._ia_recap_patch = patch(
            "agent.recapitulacao.chamar_ia_async",
            new=AsyncMock(return_value=dict(_FAKE_RECAP_VIVA_RESPONSE)),
        )
        self._ia_recap_patch.start()
        self.addCleanup(self._ia_recap_patch.stop)

    # ─────────────────────────────────────────────────────────
    # Fluxo feliz: reunião completa de ponta a ponta
    # ─────────────────────────────────────────────────────────

    def test_reuniao_completa_ponta_a_ponta(self):
        meeting_id = "e2e-reuniao-completa-1"

        r_inicio = self.client.post("/iniciar-sessao", json={"meeting_id": meeting_id})
        self.assertEqual(r_inicio.status_code, 200)

        # MeetingMemory ainda não existe antes do primeiro ciclo.
        from api.database import obter_meeting_memory
        self.assertIsNone(obter_meeting_memory(meeting_id))

        # Cada fragmento precisa passar do gate de "texto novo minimo"
        # (api/processador_tempo_real.py: 120 chars OU 18 palavras) pra IA
        # ser chamada de verdade nesse ciclo, mesmo padrao de uma fala real
        # de reuniao (nao uma frase curta isolada).
        fragmentos = [
            "Cliente: Hoje a gente perde muito tempo com follow-up manual, "
            "cada vendedor cuida disso do jeito que acha melhor e isso vira "
            "uma bagunça enorme no fim do mês.",
            "Cliente: Isso deve custar uns R$15 mil por mês em produtividade "
            "perdida, sem contar os negócios que a gente simplesmente esquece "
            "de retomar e acaba perdendo pro concorrente.",
            "Cliente: Achei caro o valor que vocês cobram pela licença, "
            "principalmente porque a gente ainda não tem certeza se o time "
            "inteiro vai usar a ferramenta direito.",  # objeção
        ]
        historico = ""
        for i, fala in enumerate(fragmentos):
            r = self.client.post(
                "/tempo-real",
                json={
                    "transcricao_parcial": fala,
                    "transcricao_nova": fala,
                    "historico": historico,
                    "meeting_id": meeting_id,
                },
                headers=self.headers,
            )
            self.assertEqual(r.status_code, 200, r.text)
            data = r.json()
            self.assertEqual(data.get("analysis_status"), "updated", f"ciclo {i}: {data.get('analysis_reason')}")
            historico += f"\n{fala}"

        # MeetingMemory acumulou os 3 ciclos, não sobrescreveu.
        memoria = obter_meeting_memory(meeting_id)
        self.assertIsNotNone(memoria)
        self.assertGreaterEqual(len(memoria["score_history"]), 3, "score_history deveria acumular 1 entrada por ciclo")
        self.assertGreater(memoria["provider_cost_estimate"], -1)  # aceita 0.0 (fake não simula custo real) sem quebrar

        # Transcrição acumulada sem duplicar cada fala.
        for fala in fragmentos:
            self.assertEqual(
                memoria["transcript_full"].count(fala), 1,
                f"fala duplicada ou ausente na transcrição acumulada: {fala!r}",
            )

        # Recapitulação viva lê a MeetingMemory de verdade (não é uma
        # chamada desconectada) — precisa existir ANTES de poder chamar.
        r_recap = self.client.post("/recapitulacao-viva", json={"meeting_id": meeting_id})
        self.assertEqual(r_recap.status_code, 200, r_recap.text)
        recap_data = r_recap.json()
        self.assertEqual(recap_data["meeting_id"], meeting_id)
        self.assertIn("recapitulacao_viva", recap_data)

    def test_recapitulacao_viva_404_sem_meeting_memory(self):
        r = self.client.post("/recapitulacao-viva", json={"meeting_id": "meeting-que-nunca-existiu"})
        self.assertEqual(r.status_code, 404)

    def test_duas_reunioes_nao_se_misturam(self):
        m1, m2 = "e2e-isolamento-1", "e2e-isolamento-2"
        self.client.post(
            "/tempo-real",
            json={"transcricao_parcial": "Cliente: fala da reuniao 1", "meeting_id": m1},
            headers=self.headers,
        )
        from api.database import obter_meeting_memory
        # m2 nunca recebeu um ciclo — não pode ter memória nenhuma, nem
        # "herdar" nada do que aconteceu em m1.
        self.assertIsNone(obter_meeting_memory(m2))
        mem1 = obter_meeting_memory(m1)
        self.assertIsNotNone(mem1)
        self.assertIn("fala da reuniao 1", mem1["transcript_full"])

    def test_ACHADO_recapitulacao_viva_sem_auth_nem_ownership(self):
        """Achado de segurança documentado na Fase 0 (não corrigido nesta
        rodada, ver docs/BASELINE_REPORT_FASE0.md): /recapitulacao-viva
        não exige autenticação e MeetingMemory não tem coluna usuario_id
        — qualquer pessoa que souber um meeting_id de outro vendedor
        consegue ler a recapitulação viva daquela reunião. Este teste
        documenta o comportamento ATUAL (200 sem token), não afirma que
        isso é correto — serve pra detectar quando alguém corrigir isso
        de propósito (aí este teste passa a falhar e deve ser atualizado
        junto da correção, não silenciado)."""
        meeting_id = "e2e-achado-sem-auth"
        self.client.post(
            "/tempo-real",
            json={"transcricao_parcial": "Cliente: dado sensivel do negocio dele.", "meeting_id": meeting_id},
            headers=self.headers,
        )
        r_sem_token = self.client.post("/recapitulacao-viva", json={"meeting_id": meeting_id})
        self.assertEqual(
            r_sem_token.status_code, 200,
            "Se isso passou a exigir auth, ótimo — atualize este teste e o BASELINE_REPORT_FASE0.md.",
        )

    # ─────────────────────────────────────────────────────────
    # Degradação controlada quando a IA falha
    # ─────────────────────────────────────────────────────────

    def test_ACHADO_todos_provedores_indisponiveis_degrada_silenciosamente(self):
        self._ia_multiagente.side_effect = HTTPException(status_code=503, detail="todos os provedores fora do ar")
        fala = (
            "Cliente: Alô, vocês estão me ouvindo? Queria entender melhor "
            "como funciona a implantação da ferramenta no nosso time inteiro."
        )
        r = self.client.post(
            "/tempo-real",
            json={"transcricao_parcial": fala, "meeting_id": "e2e-falha-total"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        # Achado real (diferente do que a investigação inicial supunha):
        # cada um dos 5 agentes falha isoladamente DENTRO de
        # analisar_fragmento_multi (agent/multiagente/orquestrador.py),
        # capturado por _safe()/asyncio.gather(return_exceptions=True) —
        # a exceção NUNCA propaga até processador_tempo_real.py, então o
        # try/except de lá nunca dispara "analysis_status: error".
        # _mesclar() monta um resultado normal com fallbacks genéricos
        # (_FALLBACK_NBA etc.) e devolve analysis_status="updated" como se
        # tivesse funcionado — com os 4 provedores centrais fora do ar, o
        # vendedor recebe 200 com conteúdo genérico e NENHUM sinal visível
        # de que a IA falhou. Documentado no BASELINE_REPORT_FASE0.md como
        # achado de observabilidade (não corrigido nesta rodada — é
        # decisão de produto se merece um flag de degradação visível).
        data = r.json()
        self.assertEqual(data.get("analysis_status"), "updated")
        self.assertEqual(data.get("next_best_action", {}).get("title"), "Descoberta Inicial")  # fallback genérico

    def test_json_invalido_de_um_provedor_nao_quebra_o_ciclo(self):
        # Simula: 1a tentativa retorna algo não-dict (json malformado já
        # foi tratado como erro por api/ai_router.py antes de chegar aqui;
        # no nível do agente, uma resposta inesperada também não pode
        # derrubar o ciclo) — 2a chamada em diante volta ao normal.
        self._ia_multiagente.side_effect = [
            "isto nao e um dict valido",
            dict(_FAKE_AGENT_RESPONSE),
            dict(_FAKE_AGENT_RESPONSE),
            dict(_FAKE_AGENT_RESPONSE),
            dict(_FAKE_AGENT_RESPONSE),
        ]
        fala = (
            "Cliente: Ok, entendi a proposta. Só preciso alinhar com o time "
            "financeiro antes de fechar qualquer coisa por aqui."
        )
        r = self.client.post(
            "/tempo-real",
            json={"transcricao_parcial": fala, "meeting_id": "e2e-json-invalido"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        # Nunca pode vazar a string crua nem quebrar em 500 — resultado
        # sempre precisa ser um dict serializável.
        self.assertIsInstance(r.json(), dict)


if __name__ == "__main__":
    unittest.main()
