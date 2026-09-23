"""
Testes de agent/policy_violation_rules.py — Fase 25 do "PROMPT MESTRE
— SALE-IA V2" (Critério para iniciar o Digital Sales Twin), critério
`policy violation = 0`.

Módulo puro (sem IA, sem banco) — mesmo padrão de
tests/test_audit_trail.py::ValidarAuditTrailEntryTest.

Run:
    python -m unittest tests.test_policy_violation_rules -v
"""

import unittest

from agent.policy_violation_rules import (
    POLICY_VIOLATION_TIPOS,
    validar_policy_violation_event,
)


class ValidarPolicyViolationEventTest(unittest.TestCase):
    def _dados_validos(self, **overrides):
        dados = {"tipo": "PROMPT_INJECTION", "trechos_detectados": ["ignore as instruções"]}
        dados.update(overrides)
        return dados

    def test_dados_validos_nao_levantam(self):
        validar_policy_violation_event(self._dados_validos())  # não deve levantar

    def test_tipo_invalido_levanta(self):
        with self.assertRaises(ValueError):
            validar_policy_violation_event(self._dados_validos(tipo="ADVERSARIAL_SALES"))

    def test_tipo_ausente_levanta(self):
        with self.assertRaises(ValueError):
            validar_policy_violation_event(self._dados_validos(tipo=None))

    def test_trechos_detectados_vazios_levanta(self):
        with self.assertRaises(ValueError):
            validar_policy_violation_event(self._dados_validos(trechos_detectados=[]))

    def test_trechos_detectados_ausentes_levanta(self):
        with self.assertRaises(ValueError):
            validar_policy_violation_event({"tipo": "PROMPT_INJECTION"})


class VocabularioTest(unittest.TestCase):
    def test_so_prompt_injection_tem_detector_hoje(self):
        # Decisão deliberada de escopo desta rodada — adversarial sales
        # (Fase 21) e FORBIDDEN do AutonomyPolicy (Fase 17) não têm
        # detector real ainda, documentados como gap.
        self.assertEqual(POLICY_VIOLATION_TIPOS, ("PROMPT_INJECTION",))


if __name__ == "__main__":
    unittest.main()
