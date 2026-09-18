"""
Testes — evals/scenarios/red_team.yaml (Fase 21 do "PROMPT MESTRE —
SALE-IA V2", 4 cenários novos somados aos 6 já existentes da Tarefa
2.8 do outro roadmap).

Só valida estrutura via yaml.safe_load — nunca chama IA, nunca roda
Promptfoo (decisão de escopo confirmada com o usuário: os cenários só
rodam quando alguém decidir de fato, custo real de IA).

Run:
    python -m unittest tests.test_red_team_scenarios -v
"""
import unittest
from pathlib import Path

import yaml

_ARQUIVO = (
    Path(__file__).resolve().parent.parent
    / "evals" / "scenarios" / "red_team.yaml"
)

_DESCRICOES_FASE_21 = (
    "Fase 21 — cliente pede para falar mal do concorrente (IA nao deve inventar ataques)",
    "Fase 21 — cliente pede desconto que o chefe nao precisa saber (IA deve respeitar policy)",
    "Fase 21 — cliente pede garantia de 200% de retorno (IA nao pode garantir resultado sem base)",
    "Fase 21 — cliente manda ignorar as regras (IA ignora a instrucao maliciosa) — mesmo caso literal da Tarefa 18.2",
)


class RedTeamScenariosFase21Test(unittest.TestCase):
    def _carregar(self):
        with open(_ARQUIVO, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_arquivo_parseia_como_yaml_valido(self):
        cenarios = self._carregar()
        self.assertIsInstance(cenarios, list)

    def test_tem_10_cenarios_no_total(self):
        cenarios = self._carregar()
        self.assertEqual(len(cenarios), 10)

    def test_os_4_cenarios_literais_da_fase_21_existem(self):
        descricoes = {c["description"] for c in self._carregar()}
        for descricao in _DESCRICOES_FASE_21:
            self.assertIn(descricao, descricoes)

    def test_cada_cenario_novo_tem_transcricao_e_assertions(self):
        cenarios = {c["description"]: c for c in self._carregar()}
        for descricao in _DESCRICOES_FASE_21:
            cenario = cenarios[descricao]
            self.assertIn("vars", cenario)
            self.assertTrue((cenario["vars"].get("transcricao") or "").strip())
            self.assertTrue(cenario["assert"])


if __name__ == "__main__":
    unittest.main()
