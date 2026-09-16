"""
Testes do Experiment Engine — Fase 14 (Tarefas 14.1 e 14.2) do
"PROMPT MESTRE — SALE-IA V2".

Função pura (agent/experiment_engine_rules.py), sem IA/banco. Reproduz
o exemplo literal do prompt mestre (Tarefa 14.1) e a guarda de
segurança fail-closed dos 5 itens obrigatórios (Tarefa 14.2).

Run:
    python -m unittest tests.test_experiment_engine_rules -v
"""

import unittest

from agent.experiment_engine_rules import (
    EXPERIMENT_SAFETY_CHECKS,
    montar_experiment_config,
    montar_experiment_hypothesis,
    validar_experiment_config,
    validar_experiment_hypothesis,
    validar_seguranca_experimento,
)


def _atestacao_completa():
    return {check: True for check in EXPERIMENT_SAFETY_CHECKS}


class ExperimentHypothesisTest(unittest.TestCase):
    def test_exemplo_literal_do_prompt_mestre(self):
        teste = montar_experiment_hypothesis(
            hypothesis="Quantificar impacto antes de preço melhora avanço.",
            control="fluxo atual",
            treatment="pergunta de impacto",
            metric="stage advancement",
        )
        self.assertEqual(teste["hypothesis"], "Quantificar impacto antes de preço melhora avanço.")
        self.assertEqual(teste["control"], "fluxo atual")
        self.assertEqual(teste["treatment"], "pergunta de impacto")
        self.assertEqual(teste["metric"], "stage advancement")

    def test_cada_campo_obrigatorio_individualmente(self):
        base = dict(hypothesis="h", control="c", treatment="t", metric="m")
        for campo in ("hypothesis", "control", "treatment", "metric"):
            kwargs = dict(base)
            kwargs[campo] = ""
            with self.assertRaises(ValueError):
                validar_experiment_hypothesis(**kwargs)

    def test_campo_so_com_espacos_e_tratado_como_vazio(self):
        with self.assertRaises(ValueError):
            validar_experiment_hypothesis("h", "c", "   ", "m")

    def test_campo_none_levanta(self):
        with self.assertRaises(ValueError):
            validar_experiment_hypothesis(None, "c", "t", "m")


class SegurancaExperimentoTest(unittest.TestCase):
    """Regra literal do prompt mestre: experimento não pode envolver
    informação falsa, discriminação, preço enganoso, escassez falsa ou
    ocultação de informação relevante — garantida via atestação
    explícita fail-closed."""

    def test_os_5_itens_literais_do_prompt_mestre(self):
        self.assertEqual(
            EXPERIMENT_SAFETY_CHECKS,
            (
                "no_false_information",
                "no_discrimination",
                "no_deceptive_pricing",
                "no_false_scarcity",
                "no_information_concealment",
            ),
        )

    def test_atestacao_completa_passa(self):
        validar_seguranca_experimento(_atestacao_completa())  # não deve levantar

    def test_atestacao_ausente_levanta(self):
        with self.assertRaises(ValueError):
            validar_seguranca_experimento({})

    def test_atestacao_none_levanta(self):
        with self.assertRaises(ValueError):
            validar_seguranca_experimento(None)

    def test_cada_item_faltando_individualmente_levanta(self):
        for check in EXPERIMENT_SAFETY_CHECKS:
            atestacao = _atestacao_completa()
            del atestacao[check]
            with self.assertRaises(ValueError):
                validar_seguranca_experimento(atestacao)

    def test_cada_item_explicitamente_false_levanta(self):
        for check in EXPERIMENT_SAFETY_CHECKS:
            atestacao = _atestacao_completa()
            atestacao[check] = False
            with self.assertRaises(ValueError):
                validar_seguranca_experimento(atestacao)

    def test_valor_truthy_nao_booleano_nao_e_aceito(self):
        """Fail-closed de verdade: string 'sim'/1 não substituem True
        explícito — evita atestação acidental por valor truthy solto."""
        atestacao = _atestacao_completa()
        atestacao["no_discrimination"] = "sim"
        with self.assertRaises(ValueError):
            validar_seguranca_experimento(atestacao)


class ExperimentConfigTest(unittest.TestCase):
    def test_exemplo_completo_valido(self):
        validar_experiment_config(
            pilot_group="grupo_piloto",
            control_group="grupo_controle",
            duration=14,
            minimum_sample=30,
            safety_attestation=_atestacao_completa(),
        )  # não deve levantar

    def test_pilot_group_vazio_levanta(self):
        with self.assertRaises(ValueError):
            validar_experiment_config("", "controle", 14, 30, _atestacao_completa())

    def test_control_group_vazio_levanta(self):
        with self.assertRaises(ValueError):
            validar_experiment_config("piloto", "", 14, 30, _atestacao_completa())

    def test_pilot_e_control_iguais_levanta(self):
        with self.assertRaises(ValueError):
            validar_experiment_config("mesmo_grupo", "mesmo_grupo", 14, 30, _atestacao_completa())

    def test_duration_zero_ou_negativa_levanta(self):
        with self.assertRaises(ValueError):
            validar_experiment_config("piloto", "controle", 0, 30, _atestacao_completa())
        with self.assertRaises(ValueError):
            validar_experiment_config("piloto", "controle", -1, 30, _atestacao_completa())

    def test_minimum_sample_zero_ou_negativo_levanta(self):
        with self.assertRaises(ValueError):
            validar_experiment_config("piloto", "controle", 14, 0, _atestacao_completa())

    def test_seguranca_invalida_propaga(self):
        with self.assertRaises(ValueError):
            validar_experiment_config("piloto", "controle", 14, 30, {})


class MontarExperimentConfigTest(unittest.TestCase):
    def test_monta_config_completa_a_partir_da_hypothesis(self):
        hipotese = montar_experiment_hypothesis(
            hypothesis="Quantificar impacto antes de preço melhora avanço.",
            control="fluxo atual",
            treatment="pergunta de impacto",
            metric="stage advancement",
        )
        config = montar_experiment_config(
            hypothesis_test=hipotese,
            pilot_group="grupo_a",
            control_group="grupo_b",
            duration=21,
            minimum_sample=50,
            safety_attestation=_atestacao_completa(),
        )
        self.assertEqual(config["hypothesis"], hipotese["hypothesis"])
        self.assertEqual(config["control"], "fluxo atual")
        self.assertEqual(config["treatment"], "pergunta de impacto")
        self.assertEqual(config["metric"], "stage advancement")
        self.assertEqual(config["pilot_group"], "grupo_a")
        self.assertEqual(config["control_group"], "grupo_b")
        self.assertEqual(config["duration"], 21)
        self.assertEqual(config["minimum_sample"], 50)
        self.assertEqual(config["safety_attestation"], _atestacao_completa())

    def test_hypothesis_test_invalido_levanta(self):
        with self.assertRaises(ValueError):
            montar_experiment_config(
                hypothesis_test={"hypothesis": "h"},  # faltam control/treatment/metric
                pilot_group="a",
                control_group="b",
                duration=14,
                minimum_sample=30,
                safety_attestation=_atestacao_completa(),
            )

    def test_hypothesis_test_nao_dict_levanta(self):
        with self.assertRaises(ValueError):
            montar_experiment_config(
                hypothesis_test="não é um dict",
                pilot_group="a",
                control_group="b",
                duration=14,
                minimum_sample=30,
                safety_attestation=_atestacao_completa(),
            )

    def test_seguranca_reprovada_bloqueia_mesmo_com_hypothesis_valida(self):
        hipotese = montar_experiment_hypothesis("h", "c", "t", "m")
        with self.assertRaises(ValueError):
            montar_experiment_config(
                hypothesis_test=hipotese,
                pilot_group="a",
                control_group="b",
                duration=14,
                minimum_sample=30,
                safety_attestation={},
            )


if __name__ == "__main__":
    unittest.main()
