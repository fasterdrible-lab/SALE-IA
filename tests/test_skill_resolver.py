"""
Testes unitários — agent/skill_resolver.py

Foco desta suíte: `resolver_melhor_skill`/`resolver_skill_context` (seleção
por triggers + prioridade) e a instrumentação de observabilidade adicionada
à Fase 1 (Langfuse) — TAREFA 1.7 do PROMPT MESTRE (skills consideradas,
skill selecionada, score, DISC, estágio, prioridade).

`listar_skills` é sempre mockado — sem isso, cada chamada bate em disco
(agent/skills/*.json) + tenta MySQL (falha graciosamente, mas com latência
real de conexão recusada). Mesmo padrão de tests/test_cost_router.py.

Run:
    python -m unittest tests.test_skill_resolver -v
"""
import logging
import unittest
from unittest.mock import MagicMock, patch

logging.disable(logging.CRITICAL)

from agent import skill_resolver


def _skill(name, priority=50, source="builtin", disc=None, min_score=0, max_score=100,
           stages=None, system_injection="[SKILL] texto"):
    return {
        "name": name,
        "priority": priority,
        "source": source,
        "triggers": {
            "disc_profiles": disc or [],
            "min_score": min_score,
            "max_score": max_score,
            "stages": stages or [],
        },
        "system_injection": system_injection,
    }


class ResolverMelhorSkillTest(unittest.TestCase):
    def test_nenhuma_skill_aplicavel_retorna_none(self):
        with patch.object(skill_resolver, "listar_skills", return_value=[_skill("A", min_score=90, max_score=100)]):
            self.assertIsNone(skill_resolver.resolver_melhor_skill(score=10.0))

    def test_maior_priority_vence(self):
        baixa = _skill("baixa", priority=40)
        alta = _skill("alta", priority=90)
        with patch.object(skill_resolver, "listar_skills", return_value=[baixa, alta]):
            vencedora = skill_resolver.resolver_melhor_skill()
        self.assertEqual(vencedora["name"], "alta")

    def test_empate_de_priority_prefere_builtin(self):
        gerada = _skill("gerada", priority=70, source="knowledge_compiler")
        builtin = _skill("builtin", priority=70, source="builtin")
        with patch.object(skill_resolver, "listar_skills", return_value=[gerada, builtin]):
            vencedora = skill_resolver.resolver_melhor_skill()
        self.assertEqual(vencedora["name"], "builtin")

    def test_filtra_por_disc_score_e_stage(self):
        fora_disc = _skill("fora_disc", disc=["C"])
        fora_score = _skill("fora_score", min_score=80, max_score=100)
        fora_stage = _skill("fora_stage", stages=["fechamento"])
        aplicavel = _skill("aplicavel", disc=["D"], min_score=0, max_score=100, stages=["descoberta"])
        with patch.object(skill_resolver, "listar_skills",
                           return_value=[fora_disc, fora_score, fora_stage, aplicavel]):
            vencedora = skill_resolver.resolver_melhor_skill(
                disc_profile="D", score=50.0, conversation_stage="descoberta",
            )
        self.assertEqual(vencedora["name"], "aplicavel")


class ResolverSkillContextTest(unittest.TestCase):
    def test_retorna_injecao_quando_ha_skill_aplicavel(self):
        skill = _skill("vencedora", system_injection="[SKILL] faça X")
        with patch.object(skill_resolver, "listar_skills", return_value=[skill]):
            texto = skill_resolver.resolver_skill_context()
        self.assertIn("[SKILL] faça X", texto)

    def test_retorna_vazio_sem_skill_aplicavel(self):
        with patch.object(skill_resolver, "listar_skills", return_value=[_skill("x", min_score=90, max_score=100)]):
            texto = skill_resolver.resolver_skill_context(score=10.0)
        self.assertEqual(texto, "")

    def test_retorna_vazio_quando_skill_sem_system_injection(self):
        skill = _skill("sem_texto", system_injection="")
        with patch.object(skill_resolver, "listar_skills", return_value=[skill]):
            texto = skill_resolver.resolver_skill_context()
        self.assertEqual(texto, "")

    def _obs_mock(self):
        obs = MagicMock()
        span = MagicMock()
        obs.start_span.return_value = span
        return obs, span

    def test_instrumenta_span_com_skill_selecionada_e_metadados(self):
        skill = _skill("vencedora", priority=77, source="builtin")
        obs, span = self._obs_mock()
        with patch.object(skill_resolver, "listar_skills", return_value=[skill]):
            with patch("services.observability.factory.get_observability_provider", return_value=obs):
                skill_resolver.resolver_skill_context(
                    disc_profile="D", score=60.0, conversation_stage="negociacao", meeting_id="m1",
                )

        obs.start_span.assert_called_once()
        _, kwargs = obs.start_span.call_args
        self.assertEqual(kwargs["name"], "skill_resolver")
        self.assertEqual(kwargs["meeting_id"], "m1")
        self.assertEqual(kwargs["input"], {"disc_profile": "D", "score": 60.0, "conversation_stage": "negociacao"})
        self.assertEqual(kwargs["metadata"]["candidatos_considerados"], 1)
        self.assertEqual(kwargs["metadata"]["skill_selecionada"], "vencedora")
        self.assertEqual(kwargs["metadata"]["skill_priority"], 77)
        self.assertEqual(kwargs["metadata"]["skill_source"], "builtin")
        obs.end_span.assert_called_once_with(span, output={"skill_selecionada": "vencedora"})

    def test_instrumenta_span_mesmo_sem_skill_aplicavel(self):
        obs, span = self._obs_mock()
        with patch.object(skill_resolver, "listar_skills", return_value=[_skill("fora", min_score=90, max_score=100)]):
            with patch("services.observability.factory.get_observability_provider", return_value=obs):
                skill_resolver.resolver_skill_context(score=10.0)

        _, kwargs = obs.start_span.call_args
        self.assertEqual(kwargs["metadata"]["candidatos_considerados"], 0)
        self.assertIsNone(kwargs["metadata"]["skill_selecionada"])
        obs.end_span.assert_called_once_with(span, output={"skill_selecionada": None})

    def test_falha_de_observabilidade_nunca_quebra_a_resolucao(self):
        skill = _skill("vencedora")
        with patch.object(skill_resolver, "listar_skills", return_value=[skill]):
            with patch("services.observability.factory.get_observability_provider",
                       side_effect=RuntimeError("langfuse fora do ar")):
                texto = skill_resolver.resolver_skill_context()
        self.assertIn("[SKILL]", texto)


class ResolverSkillsRelevantesTest(unittest.TestCase):
    """TAREFA 5.2/5.3 do PROMPT MESTRE (Skill Resolver V2)."""

    def test_primary_e_a_mesma_que_resolver_melhor_skill_escolheria(self):
        baixa = _skill("baixa", priority=40)
        alta = _skill("alta", priority=90)
        with patch.object(skill_resolver, "listar_skills", return_value=[baixa, alta]):
            resultado = skill_resolver.resolver_skills_relevantes()
        self.assertEqual(resultado["primary"]["name"], "alta")

    def test_sem_candidato_primary_e_none_e_listas_vazias(self):
        with patch.object(skill_resolver, "listar_skills", return_value=[_skill("fora", min_score=90, max_score=100)]):
            resultado = skill_resolver.resolver_skills_relevantes(score=10.0)
        self.assertIsNone(resultado["primary"])
        self.assertEqual(resultado["supporting"], [])
        self.assertEqual(resultado["cases"], [])

    def test_supporting_limitado_a_2_mesmo_com_mais_candidatos(self):
        skills = [_skill(f"s{i}", priority=100 - i) for i in range(5)]
        with patch.object(skill_resolver, "listar_skills", return_value=skills):
            resultado = skill_resolver.resolver_skills_relevantes()
        self.assertEqual(resultado["primary"]["name"], "s0")
        self.assertEqual([s["name"] for s in resultado["supporting"]], ["s1", "s2"])

    def test_case_reconhecido_pelo_prefixo_e_separado_de_primary_supporting(self):
        normal = _skill("normal", priority=90)
        caso = _skill("caso-real", priority=95, system_injection="[CASE] Cliente X fechou apos objecao de preco")
        with patch.object(skill_resolver, "listar_skills", return_value=[normal, caso]):
            resultado = skill_resolver.resolver_skills_relevantes()
        self.assertEqual(resultado["primary"]["name"], "normal")
        self.assertEqual([c["name"] for c in resultado["cases"]], ["caso-real"])

    def test_cases_limitado_a_1_mesmo_com_mais_de_um_case(self):
        caso1 = _skill("caso1", priority=95, system_injection="[CASE] A")
        caso2 = _skill("caso2", priority=90, system_injection="[CASE] B")
        with patch.object(skill_resolver, "listar_skills", return_value=[caso1, caso2]):
            resultado = skill_resolver.resolver_skills_relevantes()
        self.assertEqual(len(resultado["cases"]), 1)
        self.assertEqual(resultado["cases"][0]["name"], "caso1")

    def test_skills_existentes_sem_trigger_novo_continuam_batendo_igual(self):
        # Nenhuma das 5 skills builtin declara os triggers novos — precisa
        # continuar aplicavel independente do valor dos sinais novos.
        skill = _skill("sem-triggers-novos")
        with patch.object(skill_resolver, "listar_skills", return_value=[skill]):
            com_sinal = skill_resolver.resolver_skills_relevantes(buying_signal=True, urgency=True)
            sem_sinal = skill_resolver.resolver_skills_relevantes(buying_signal=False, urgency=False)
        self.assertEqual(com_sinal["primary"]["name"], "sem-triggers-novos")
        self.assertEqual(sem_sinal["primary"]["name"], "sem-triggers-novos")

    def test_trigger_novo_filtra_quando_declarado_na_skill(self):
        skill = dict(_skill("so-com-buying-signal"))
        skill["triggers"] = dict(skill["triggers"], requires_buying_signal=True)
        with patch.object(skill_resolver, "listar_skills", return_value=[skill]):
            sem_sinal = skill_resolver.resolver_skills_relevantes(buying_signal=False)
            com_sinal = skill_resolver.resolver_skills_relevantes(buying_signal=True)
        self.assertIsNone(sem_sinal["primary"])
        self.assertEqual(com_sinal["primary"]["name"], "so-com-buying-signal")

    def test_filtra_por_disc_score_e_stage_igual_ao_v1(self):
        fora_disc = _skill("fora_disc", disc=["C"])
        aplicavel = _skill("aplicavel", disc=["D"], stages=["descoberta"])
        with patch.object(skill_resolver, "listar_skills", return_value=[fora_disc, aplicavel]):
            resultado = skill_resolver.resolver_skills_relevantes(
                disc_profile="D", score=50.0, conversation_stage="descoberta",
            )
        self.assertEqual(resultado["primary"]["name"], "aplicavel")


if __name__ == "__main__":
    unittest.main(verbosity=2)
