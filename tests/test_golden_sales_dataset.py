"""
Testes — Golden Sales Dataset (Fase 20 do "PROMPT MESTRE — SALE-IA V2").

Valida a estrutura do dataset em evals/datasets/golden_sales_dataset/
(10 categorias × 4 cenários, schema literal do prompt mestre) — nunca
roda nada contra IA real (decisão de escopo confirmada com o usuário:
só o dataset, sem runner), só confirma que o YAML parseia e que cada
cenário respeita o schema/taxonomias fechadas.

Run:
    python -m unittest tests.test_golden_sales_dataset -v
"""
import unittest
from pathlib import Path

import yaml

from agent.objection_rules import OBJECTION_TIPOS
from agent.sales_event_rules import SALES_EVENT_TYPES
from agent.sales_reasoning_engine import SALES_REASONING_FRAMEWORKS

_DATASET_DIR = (
    Path(__file__).resolve().parent.parent
    / "evals" / "datasets" / "golden_sales_dataset"
)

_CATEGORIAS = (
    "discovery",
    "qualification",
    "pricing",
    "objections",
    "negotiation",
    "closing",
    "lost_deal",
    "won_deal",
    "bad_seller_behavior",
    "good_seller_behavior",
)

_CAMPOS_OBRIGATORIOS = (
    "id",
    "description",
    "input",
    "expected_facts",
    "expected_events",
    "expected_framework",
    "acceptable_actions",
    "forbidden_actions",
)


def _carregar_categoria(nome: str) -> list:
    caminho = _DATASET_DIR / f"{nome}.yaml"
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)


class GoldenSalesDatasetEstruturaTest(unittest.TestCase):
    def test_as_10_categorias_literais_existem_como_arquivo(self):
        for categoria in _CATEGORIAS:
            caminho = _DATASET_DIR / f"{categoria}.yaml"
            self.assertTrue(caminho.exists(), f"faltando {caminho}")

    def test_readme_existe_com_versionamento(self):
        readme = _DATASET_DIR / "README.md"
        self.assertTrue(readme.exists())
        conteudo = readme.read_text(encoding="utf-8")
        self.assertIn("v1.0.0", conteudo)

    def test_cada_categoria_tem_exatamente_4_cenarios(self):
        for categoria in _CATEGORIAS:
            cenarios = _carregar_categoria(categoria)
            self.assertEqual(
                len(cenarios), 4, f"{categoria} deveria ter 4 cenários, tem {len(cenarios)}"
            )

    def test_total_de_40_cenarios(self):
        total = sum(len(_carregar_categoria(c)) for c in _CATEGORIAS)
        self.assertEqual(total, 40)

    def test_cada_cenario_tem_todos_os_campos_obrigatorios(self):
        for categoria in _CATEGORIAS:
            for cenario in _carregar_categoria(categoria):
                for campo in _CAMPOS_OBRIGATORIOS:
                    self.assertIn(
                        campo, cenario,
                        f"{categoria}/{cenario.get('id')} sem campo '{campo}'",
                    )

    def test_ids_sao_unicos_dentro_do_dataset_inteiro(self):
        todos_ids = []
        for categoria in _CATEGORIAS:
            todos_ids.extend(c["id"] for c in _carregar_categoria(categoria))
        self.assertEqual(len(todos_ids), len(set(todos_ids)), "IDs duplicados no dataset")

    def test_expected_events_usa_so_vocabulario_fechado_de_sales_event_types(self):
        for categoria in _CATEGORIAS:
            for cenario in _carregar_categoria(categoria):
                for evento in cenario["expected_events"]:
                    self.assertIn(
                        evento, SALES_EVENT_TYPES,
                        f"{categoria}/{cenario['id']}: evento '{evento}' fora de SALES_EVENT_TYPES",
                    )

    def test_expected_framework_usa_so_vocabulario_fechado_ou_null(self):
        for categoria in _CATEGORIAS:
            for cenario in _carregar_categoria(categoria):
                framework = cenario["expected_framework"]
                if framework is not None:
                    self.assertIn(
                        framework, SALES_REASONING_FRAMEWORKS,
                        f"{categoria}/{cenario['id']}: framework '{framework}' fora de SALES_REASONING_FRAMEWORKS",
                    )

    def test_acceptable_e_forbidden_actions_nunca_vazias(self):
        for categoria in _CATEGORIAS:
            for cenario in _carregar_categoria(categoria):
                self.assertTrue(
                    cenario["acceptable_actions"],
                    f"{categoria}/{cenario['id']}: acceptable_actions vazia",
                )
                self.assertTrue(
                    cenario["forbidden_actions"],
                    f"{categoria}/{cenario['id']}: forbidden_actions vazia",
                )

    def test_input_nunca_vazio(self):
        for categoria in _CATEGORIAS:
            for cenario in _carregar_categoria(categoria):
                self.assertTrue(
                    (cenario["input"] or "").strip(),
                    f"{categoria}/{cenario['id']}: input vazio",
                )

    def test_ids_seguem_o_prefixo_da_propria_categoria(self):
        prefixo_por_categoria = {
            "lost_deal": "lost-deal",
            "won_deal": "won-deal",
            "bad_seller_behavior": "bad-seller",
            "good_seller_behavior": "good-seller",
        }
        for categoria in _CATEGORIAS:
            prefixo_esperado = prefixo_por_categoria.get(categoria, categoria)
            for cenario in _carregar_categoria(categoria):
                self.assertTrue(
                    cenario["id"].startswith(prefixo_esperado),
                    f"{categoria}: id '{cenario['id']}' não começa com '{prefixo_esperado}'",
                )


class GoldenSalesDatasetObjectionsTest(unittest.TestCase):
    """objections.yaml referencia OBJECTION_TIPOS (Fase 6.1) — checagem
    leve, já que a categoria fica descrita dentro de expected_facts
    (texto livre), não um campo estruturado à parte."""

    def test_objections_menciona_categorias_conhecidas_de_objection_tipos(self):
        cenarios = _carregar_categoria("objections")
        texto_completo = " ".join(
            str(fato.get("valor", "")) for c in cenarios for fato in c["expected_facts"]
        )
        mencionadas = {tipo for tipo in OBJECTION_TIPOS if tipo in texto_completo}
        self.assertTrue(mencionadas, "nenhuma categoria de OBJECTION_TIPOS mencionada em objections.yaml")


if __name__ == "__main__":
    unittest.main()
