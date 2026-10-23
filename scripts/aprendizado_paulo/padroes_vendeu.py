"""Padrões que distinguem as vendas do Paulo — sobre as extrações da Etapa 2
(lote "completo", 1.049 reuniões). Sem IA, sem custo. PROVISÓRIO: os grupos
vêm de sinais_venda.py, não da lista oficial de compradores.

Duas leituras:
1. Por cliente (como comparar_vendeu.py): a 1ª reunião extraída (≥ 30 min)
   de cada cliente, grupos vendeu / adiou_recusou / sem_sinal. Compara
   como o Paulo monta a oferta (condições), objeções, perguntas e fechamento.
2. Objeções de dinheiro (preco + capacidade_financeira) em TODAS as
   reuniões: técnica de resposta do Paulo × desfecho dado pela IA (que só
   vale "superada"/"nao_superada" com fala do cliente depois — validador
   da v4). Independe dos grupos de sinais.

Associação, não causa (ver docs/APRENDIZADO_REUNIOES_PAULO.md).

Uso: python -I padroes_vendeu.py [pasta_dados]
Saídas (fora do git): <pasta>/padroes_vendeu.json (números, sem citação) e
<pasta>/padroes_vendeu_exemplos.csv (citações pseudonimizadas, para virar
itens da Biblioteca depois de revisadas).
"""
import csv, json, re, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PASTA = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\SALEIA_dados\paulo")
LOTE = PASTA / "completo"
EXTR = LOTE / "extracoes_deepseek-flash"
GRUPO = {"PAGOU": "vendeu", "FECHOU_VERBAL": "vendeu", "VAI_PENSAR": "adiou_recusou",
         "NAO_FECHOU": "adiou_recusou", "SEM_SINAL": "sem_sinal"}
GRUPOS = ("vendeu", "adiou_recusou", "sem_sinal")
DINHEIRO = ("preco", "capacidade_financeira")
MIN_CHARS_SEM_DURACAO = 27000  # ~30 min a 150 palavras/min (formato antigo vem sem duração)

# Condições da oferta: descrição + citação de preco.condicoes.
CONDICAO = {
    "parcelamento_12x": r"12 ?x|12 vezes|doze vezes|sem juros",
    "entrada": r"\bentrada\b",
    "sinal": r"\bsinal\b",
    "bonus": r"b[oô]nus",
    "desconto": r"desconto",
    "garantia": r"garantia|devolu[cç][aã]o",
    "cartao_recorrente": r"recorrente",
    "pix": r"\bpix\b",
    "pagar_depois_30_dias": r"30 dias|trinta dias",
    "condicao_so_hoje": r"\bhoje\b|nessa reuni[aã]o|nesta reuni[aã]o|condi[cç][aã]o especial|s[oó] agora",
}
C_RX = {k: re.compile(v, re.I) for k, v in CONDICAO.items()}


def carregar():
    nivel = {r["cliente"]: r["nivel"] for r in csv.DictReader(
        open(PASTA / "sinais_venda_clientes.csv", encoding="utf-8-sig"), delimiter=";")}
    reunioes = []
    for s in csv.DictReader(open(LOTE / "selecao.csv", encoding="utf-8-sig"), delimiter=";"):
        f = EXTR / f"{s['id']}.json"
        if not f.exists():
            continue
        s["extracao"] = json.loads(f.read_text(encoding="utf-8"))["extracao"]
        s["grupo"] = GRUPO.get(nivel.get(s["cliente"]))
        dur, chars = float(s["duracao_min"] or 0), int(s["chars"] or 0)
        s["longa"] = dur >= 30 or (dur == 0 and chars >= MIN_CHARS_SEM_DURACAO)
        reunioes.append(s)
    return reunioes


def pct(n, total):
    return round(100 * n / total, 1) if total else None


def mediana(xs):
    xs = list(xs)
    return round(statistics.median(xs), 1) if xs else None


def distribuicao(contador, total):
    return {k: pct(v, total) for k, v in contador.most_common()}


def condicoes(e):
    pr = e.get("preco") or {}
    texto = " ".join(f"{c.get('descricao', '')} {c.get('citacao', '')}" for c in pr.get("condicoes") or [])
    texto += " " + (pr.get("citacao") or "")
    return {k for k, rx in C_RX.items() if rx.search(texto)}


def por_cliente(reunioes):
    primeira = {}
    for r in reunioes:
        if r["grupo"] and r["longa"] and (r["cliente"] not in primeira or r["data"] < primeira[r["cliente"]]["data"]):
            primeira[r["cliente"]] = r
    grupos = defaultdict(list)
    for r in primeira.values():
        grupos[r["grupo"]].append(r["extracao"])

    out = {}
    for g in GRUPOS:
        es = grupos[g]
        n = len(es)
        oferta = [e for e in es if (e.get("preco") or {}).get("apresentado")]
        cond = Counter(c for e in oferta for c in condicoes(e))
        objs = [o for e in es for o in e["objecoes"]]
        din = [o for o in objs if o.get("categoria") in DINHEIRO]
        pergs = [q for e in es for q in e["perguntas_descoberta"]]
        fech = Counter(f.get("tecnica") for e in es for f in e["fechamento"])
        out[g] = {
            "n": n,
            "resultado_pela_ia": distribuicao(Counter(e["resultado"].get("status") for e in es), n),
            "tipo_reuniao": distribuicao(Counter(e.get("tipo_reuniao") for e in es), n),
            "%_apresentou_preco": pct(len(oferta), n),
            "condicoes_por_oferta_mediana": mediana(len(condicoes(e)) for e in oferta),
            "%_condicao_se_apresentou_preco": {k: pct(cond[k], len(oferta)) for k in CONDICAO},
            "dores_mediana": mediana(len(e["cliente"]["dores"]) for e in es),
            "objetivos_mediana": mediana(len(e["cliente"]["objetivos"]) for e in es),
            "objecoes_mediana": mediana(len(e["objecoes"]) for e in es),
            "%_reunioes_com_objecao_de_dinheiro": pct(sum(any(o.get("categoria") in DINHEIRO for o in e["objecoes"])
                                                          for e in es), n),
            "categoria_objecao_%": distribuicao(Counter(o.get("categoria") for o in objs), len(objs)),
            "dinheiro_tecnica_%": distribuicao(Counter(o.get("tecnica") for o in din), len(din)),
            "dinheiro_desfecho_%": distribuicao(Counter(o.get("desfecho") for o in din), len(din)),
            "perguntas_descoberta_mediana": mediana(len(e["perguntas_descoberta"]) for e in es),
            "spin_%": distribuicao(Counter(q.get("spin") for q in pergs), len(pergs)),
            "%_resposta_atende_sim": pct(sum(q.get("resposta_atende") == "sim" for q in pergs), len(pergs)),
            "%_com_tecnica_de_fechamento": {k: pct(sum(any(f.get("tecnica") == k for f in e["fechamento"]) for e in es), n)
                                            for k, _ in fech.most_common()},
            "%_proximo_passo_definido": pct(sum(bool((e.get("proximo_passo") or {}).get("definido")) for e in es), n),
        }
    return out


def objecoes_dinheiro(reunioes):
    """Técnica × desfecho em todas as reuniões + exemplos para a Biblioteca."""
    tab = defaultdict(Counter)
    exemplos = []
    for r in reunioes:
        for o in r["extracao"]["objecoes"]:
            if o.get("categoria") not in DINHEIRO:
                continue
            tab[o.get("tecnica")][o.get("desfecho")] += 1
            if o.get("desfecho") in ("superada", "parcial") and o.get("resposta_vendedor"):
                exemplos.append([r["id"], r["grupo"] or "", o.get("categoria"), o.get("tecnica"), o.get("desfecho"),
                                 o.get("contexto", ""), o.get("citacao_cliente", ""), o.get("o_que_o_cliente_quis_dizer", ""),
                                 o.get("resposta_vendedor", ""), o.get("intencao_do_vendedor", ""),
                                 o.get("reacao_cliente", ""), o.get("evidencia_desfecho", "")])
    resumo = {}
    for t, c in sorted(tab.items(), key=lambda x: -sum(x[1].values())):
        total = sum(c.values())
        com_reacao = c["superada"] + c["parcial"] + c["nao_superada"]  # "indefinido" = sem reação clara
        resumo[t] = {"n": total, "superada": c["superada"], "parcial": c["parcial"],
                     "nao_superada": c["nao_superada"], "indefinido": c["indefinido"],
                     "%_superada_entre_com_reacao": pct(c["superada"], com_reacao),
                     "%_superada_ou_parcial_entre_com_reacao": pct(c["superada"] + c["parcial"], com_reacao)}
    # Superadas primeiro; dentro, as de quem comprou.
    ordem = {"superada": 0, "parcial": 1}
    exemplos.sort(key=lambda x: (ordem[x[4]], x[1] != "vendeu", x[0]))
    return resumo, exemplos


def imprimir(cli, din):
    def linha(rotulo, f):
        print(f"{rotulo:44}" + "".join(f"{str(f(cli[g])):>14}" for g in GRUPOS))

    print(f"{'POR CLIENTE (1ª reunião extraída ≥ 30 min)':44}" + "".join(f"{g:>14}" for g in GRUPOS))
    linha("n", lambda d: d["n"])
    linha("% apresentou preço", lambda d: d["%_apresentou_preco"])
    linha("condições por oferta (mediana)", lambda d: d["condicoes_por_oferta_mediana"])
    for k in CONDICAO:
        linha(f"  se apresentou preço: {k}", lambda d, k=k: d["%_condicao_se_apresentou_preco"][k])
    linha("% com objeção de dinheiro", lambda d: d["%_reunioes_com_objecao_de_dinheiro"])
    for k in ("superada", "parcial", "nao_superada", "indefinido"):
        linha(f"  objeção de dinheiro: {k} %", lambda d, k=k: d["dinheiro_desfecho_%"].get(k))
    linha("dores (mediana)", lambda d: d["dores_mediana"])
    linha("objeções (mediana)", lambda d: d["objecoes_mediana"])
    linha("perguntas de descoberta (mediana)", lambda d: d["perguntas_descoberta_mediana"])
    linha("% resposta do cliente atende", lambda d: d["%_resposta_atende_sim"])
    for k in ("pedido_direto", "alternativa", "resumo_beneficios", "urgencia", "proximo_passo_concreto"):
        linha(f"  fechamento: {k} %", lambda d, k=k: d["%_com_tecnica_de_fechamento"].get(k))
    linha("% próximo passo definido", lambda d: d["%_proximo_passo_definido"])

    print("\nOBJEÇÕES DE DINHEIRO, TODAS AS REUNIÕES — técnica × desfecho")
    print(f"{'técnica':26}{'n':>6}{'super.':>8}{'parc.':>7}{'não':>6}{'indef.':>8}{'%sup*':>8}{'%sup+parc*':>12}")
    for t, d in din.items():
        print(f"{str(t):26}{d['n']:>6}{d['superada']:>8}{d['parcial']:>7}{d['nao_superada']:>6}{d['indefinido']:>8}"
              f"{str(d['%_superada_entre_com_reacao']):>8}{str(d['%_superada_ou_parcial_entre_com_reacao']):>12}")
    print("* entre as objeções com reação clara do cliente (sem 'indefinido')")


def main():
    reunioes = carregar()
    cli = por_cliente(reunioes)
    din, exemplos = objecoes_dinheiro(reunioes)
    json.dump({"reunioes_lidas": len(reunioes), "por_cliente": cli, "objecoes_dinheiro_tecnica_x_desfecho": din},
              open(PASTA / "padroes_vendeu.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(PASTA / "padroes_vendeu_exemplos.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["reuniao", "grupo_cliente", "categoria", "tecnica", "desfecho", "contexto", "citacao_cliente",
                    "o_que_quis_dizer", "resposta_vendedor", "intencao_do_vendedor", "reacao_cliente", "evidencia_desfecho"])
        w.writerows(exemplos)
    print(f"reuniões lidas: {len(reunioes)} | exemplos de objeção de dinheiro contornada: {len(exemplos)}\n")
    imprimir(cli, din)


main()
