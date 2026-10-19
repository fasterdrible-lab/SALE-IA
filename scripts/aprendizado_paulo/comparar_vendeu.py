"""O que o Paulo faz quando vende × quando não vende — comparação PROVISÓRIA
(usa os níveis de sinais_venda.py, não a lista oficial). Sem IA.

Unidade: a 1ª reunião com transcrição (≥ 30 min) de cada cliente — a de
venda, não a de acompanhamento. Grupos pelo nível do cliente:
  vendeu      PAGOU ou FECHOU_VERBAL
  adiou_recusou  VAI_PENSAR ou NAO_FECHOU (não fechou de forma explícita)
  sem_sinal   SEM_SINAL (mistura: pode ter pago depois, fora da reunião)
COMPROMISSO fica de fora (meio do caminho).

Associação, não causa. As palavras do ritual de fechamento (usadas para
classificar) não entram como comportamento comparado.

Uso: python -I comparar_vendeu.py <pasta_dados>
Saída: <pasta>/comparar_vendeu.json
"""
import csv, json, re, statistics, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
PASTA = sys.argv[1]
VENDEDOR = "paulo henrique"
# Nomes dos casos de sucesso do Paulo: arquivo local, fora do git (ver sinais_venda.py).
try:
    CASOS = [l.strip().lower() for l in open(f"{PASTA}/casos_de_sucesso.txt", encoding="utf-8-sig") if l.strip()]
except FileNotFoundError:
    CASOS = []
CASOS_RX = "|".join(re.escape(n) for n in CASOS) or r"(?!x)x"
GRUPO = {"PAGOU": "vendeu", "FECHOU_VERBAL": "vendeu", "VAI_PENSAR": "adiou_recusou",
         "NAO_FECHOU": "adiou_recusou", "SEM_SINAL": "sem_sinal"}

# Comportamentos do Paulo (presença na reunião).
PAULO = {
    "pede_sim_ou_nao_sincero": r"sincero,? sim ou n[aã]o|posso contar com o sincero",
    "oferece_bonus": r"b[oô]nus",
    "fala_de_garantia": r"garantia|devolu[cç][aã]o do (seu )?dinheiro",
    "conta_caso_de_cliente": rf"\b({CASOS_RX})\b|depoimento|resultado(s)? (dos|de) (nossos )?clientes|esse (aqui )?(é|e) o",
    "condicao_so_hoje": r"(s[oó]|somente|apenas) (hoje|nessa reuni[aã]o|nesta reuni[aã]o|agora)|condi[cç][aã]o especial|decis[aã]o r[aá]pida",
    "pede_sinal": r"\bsinal\b",
    "parcela_12x": r"12 vezes|doze vezes|sem juros",
    "pergunta_nota_0_10": r"de 0 a 10|de zero a dez|de 1 a 10|de um a dez",
    "quantifica_dor": r"quanto (voc[eê]s?|a empresa) (fatura|vende|lucra|perde|ganha)|quanto (isso|que isso) (te )?(custa|representa)",
    "chama_decisor": r"(esposa|marido|s[oó]cio|s[oó]cia).{0,40}(participar|entrar|estar) (na|da|nessa) (reuni[aã]o|conversa)",
}
# Comportamentos do cliente.
CLIENTE = {
    "cliente_pergunta_preco": r"quanto (custa|fica|é o investimento|seria)|qual (é )?(o )?(valor|pre[cç]o|investimento)",
    "cliente_cita_esposa_socio": r"\b(minha esposa|meu marido|meu s[oó]cio|minha s[oó]cia|meus s[oó]cios)\b",
    "cliente_fala_de_dinheiro_curto": r"(t[aá]|est[aá]) (apertado|dif[ií]cil)|n[aã]o tenho (esse )?(dinheiro|valor)|sem (dinheiro|caixa)",
}
P_RX = {k: re.compile(v, re.I) for k, v in PAULO.items()}
C_RX = {k: re.compile(v, re.I) for k, v in CLIENTE.items()}
# Só a OFERTA — "R$ 50 mil" sozinho costuma ser o faturamento do cliente.
PRECO_RX = re.compile(r"(investimento|entrada|parcela)s? (de|é|e|seria|fica|ficaria)\b|12 vezes|doze vezes|sem juros", re.I)
NUMERICAS = ["duracao_min", "pct_fala_vendedor", "perguntas_vendedor_por_hora", "pct_perguntas_abertas",
             "perguntas_cliente_por_hora", "monologo_estimado_s", "preco_em_%_da_reuniao"]


def main():
    nivel_cli = {r["cliente"]: r["nivel"] for r in csv.DictReader(
        open(f"{PASTA}/sinais_venda_clientes.csv", encoding="utf-8-sig"), delimiter=";")}
    primeira = {}
    for l in open(f"{PASTA}/reunioes.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if not r["tem_transcricao"] or not r["duracao_s"] or r["duracao_s"] < 1800:
            continue
        if r["cliente"] not in primeira or (r["data"] or "") < (primeira[r["cliente"]]["data"] or ""):
            primeira[r["cliente"]] = r

    linhas = defaultdict(list)
    for cli, r in primeira.items():
        g = GRUPO.get(nivel_cli.get(cli))
        if not g:
            continue
        falas = r["falas"]
        paulo = " ".join(f["texto"] for f in falas if VENDEDOR in f["falante"].lower())
        cliente = " ".join(f["texto"] for f in falas if VENDEDOR not in f["falante"].lower())
        i_preco = next((i for i, f in enumerate(falas) if VENDEDOR in f["falante"].lower() and PRECO_RX.search(f["texto"])), None)
        horas = r["duracao_s"] / 3600
        d = {
            "duracao_min": r["duracao_s"] / 60, "pct_fala_vendedor": r["pct_fala_vendedor"],
            "perguntas_vendedor_por_hora": r["perguntas_vendedor"] / horas,
            "pct_perguntas_abertas": 100 * r["perguntas_abertas"] / r["perguntas_vendedor"] if r["perguntas_vendedor"] else None,
            "perguntas_cliente_por_hora": r["perguntas_cliente"] / horas, "monologo_estimado_s": r["monologo_estimado_s"],
            "preco_em_%_da_reuniao": 100 * i_preco / len(falas) if i_preco is not None else None,
            "chegou_na_oferta": i_preco is not None,
        }
        d.update({k: bool(rx.search(paulo)) for k, rx in P_RX.items()})
        d.update({k: bool(rx.search(cliente)) for k, rx in C_RX.items()})
        linhas[g].append(d)

    def mediana(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.median(xs), 1) if xs else None

    resultado = {}
    for g in ("vendeu", "adiou_recusou", "sem_sinal"):
        ls = linhas[g]
        resultado[g] = {"n": len(ls)}
        resultado[g].update({k: mediana(l[k] for l in ls) for k in NUMERICAS})
        resultado[g].update({f"%_{k}": round(100 * sum(l[k] for l in ls) / len(ls), 1) if ls else None
                             for k in ["chegou_na_oferta"] + list(PAULO) + list(CLIENTE)})
        # Mesmos comportamentos só entre as reuniões que chegaram à oferta
        # (bônus, sinal e 12x só aparecem depois do preço).
        com_oferta = [l for l in ls if l["chegou_na_oferta"]]
        resultado[g].update({f"%_{k}_se_chegou_na_oferta": round(100 * sum(l[k] for l in com_oferta) / len(com_oferta), 1)
                             if com_oferta else None for k in ("oferece_bonus", "pede_sinal", "parcela_12x", "pede_sim_ou_nao_sincero")})
    json.dump(resultado, open(f"{PASTA}/comparar_vendeu.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    chaves = list(resultado["vendeu"])
    print(f"{'':34}{'vendeu':>10}{'adiou/rec':>11}{'sem_sinal':>11}")
    for k in chaves:
        print(f"{k:34}" + "".join(f"{str(resultado[g][k]):>11}" for g in ("vendeu", "adiou_recusou", "sem_sinal")))


main()
