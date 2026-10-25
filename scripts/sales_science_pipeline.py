"""
scripts/sales_science_pipeline.py — Tarefa B3: uma volta do pipeline
analítico (agent/sales_science_pipeline.py). Chamado de hora em hora por
`saleia-sales-science.timer`, em processo próprio e com prioridade baixa,
nunca dentro do uvicorn. Sem IA, só leitura do banco + 1 arquivo em data/.

Uso (na VPS, em /opt/saleia):
    venv/bin/python -m scripts.sales_science_pipeline
"""
from __future__ import annotations

import json

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    from agent.sales_science_pipeline import executar_pipeline

    print(json.dumps(executar_pipeline(), ensure_ascii=False))


if __name__ == "__main__":
    main()
