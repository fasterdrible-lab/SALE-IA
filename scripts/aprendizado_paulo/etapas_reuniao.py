"""Liga as extrações da Etapa 2 às 3 etapas do método de venda — sem IA.

Etapas (definição do usuário, 23/10/2026):
  diagnostico      entender o cenário e "fechar as portas" antes da solução
  apresentacao     conectar o projeto ao que o cliente trouxe no diagnóstico
  fechamento_pre   perguntas de amarração antes do investimento
  fechamento_pos   investimento apresentado + quebra de objeção ("vou pensar"…)

Cortes por marcador na fala do VENDEDOR (aproximados, conferir na amostra):
  fim do diagnóstico   1ª recapitulação / "deixa eu te mostrar" depois de 15%
  investimento         1ª oferta com valor ou condição (12x, sem juros, "entrada de R$…")
                       depois do diagnóstico
  início do fechamento última pergunta de amarração antes do investimento, já na reta
                       final (≥ 60% do trecho apresentação→investimento)
Amostra conferida em 23/10: a 1ª amarração depois da recapitulação costuma ser
o COMBINADO do "sincero sim ou não" no começo da apresentação ("no final quero
contar com o sincero sim ou não") — medido à parte (`contrato_sim_ou_nao`),
não é fechamento. "Investimento" sem valor ("o investimento é baseado no
retorno") é conversa, não oferta.
Reunião sem recapitulação fica fora das análises por etapa.

Uso: python -I etapas_reuniao.py [pasta_dados]
Saídas (fora do git): <pasta>/etapas_reunioes.csv (cortes por reunião),
<pasta>/etapas_amostra.txt (falas em volta dos cortes, para conferir),
<pasta>/etapas_analise.json, <pasta>/etapas_exemplos_fechamento.csv.
"""
import csv, json, random, re, statistics, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PASTA = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\SALEIA_dados\paulo")
LOTE = PASTA / "completo"
EXTR = LOTE / "extracoes_deepseek-flash"
GRUPO = {"PAGOU": "vendeu", "FECHOU_VERBAL": "vendeu", "VAI_PENSAR": "adiou_recusou",
         "NAO_FECHOU": "adiou_recusou", "SEM_SINAL": "sem_sinal"}
GRUPOS = ("vendeu", "adiou_recusou", "sem_sinal")
ETAPAS = ("diagnostico", "apresentacao", "fechamento_pre", "fechamento_pos")
MIN_CHARS_SEM_DURACAO = 27000

RECAP_RX = re.compile(r"recapitul|deixa eu (te |s[oó] )?(mostrar|apresentar)|vou (te )?(mostrar|apresentar)|"
                      r"compartilhar (a |minha )?tela|consegue ver (a )?minha tela", re.I)
AMARRA_RX = re.compile(r"sincero,? sim ou n[aã]o|posso contar com|se fizer sentido|"
                       r"voc[eê] (come[cç]a|starta|inicia|fecha) (com a gente )?(hoje|agora)|"
                       r"se eu (conseguir|te entregar|encaixar).{0,80}(voc[eê]|a gente) (come[cç]a|starta|avan[cç]a|fecha)|"
                       r"o que (ainda )?(pode|poderia) te (travar|impedir|segurar)", re.I)
# Só a OFERTA com valor ou condição ("R$ 50 mil" sozinho costuma ser faturamento;
# "investimento" sem número costuma ser conversa).
PRECO_RX = re.compile(r"(investimento|entrada|parcela)s? (de|é|e|seria|fica|ficaria|ficaria em) (de )?(r\$ ?)?\d|"
                      r"\b(em|de) (at[eé] )?1[0-2] ?(vezes|x)\b|\b1[0-2] ?(vezes|x) (de|no|sem)\b|\b12 ?x\b|"
                      r"doze vezes|sem juros|100 juros", re.I)  # "10 vezes a mais" não é parcela
FECHAMENTO_RETA_FINAL = 0.6

# "Portas" que o diagnóstico pode fechar, e a objeção que cada uma deveria evitar no fim.
PORTAS = {
    "decisor": (r"quem (mais )?(decide|participa|toma a decis)|decide sozinh|decis[aã]o (é|e) (s[oó] )?sua|"
                r"(esposa|marido|s[oó]ci[oa]|fam[ií]lia).{0,60}(decid|decis[aã]o|particip|junto|apoi)", ("decisor_terceiros",)),
    "investimento": (r"quanto (voc[eê] )?(tem|teria|consegue|pode|pretende|est[aá] disposto).{0,30}(investir|dispon|separar|reservad)|"
                     r"or[cç]amento|tem (um )?valor (separado|reservado|em mente)|capital (dispon[ií]vel|para investir)",
                     ("capacidade_financeira", "preco")),
    "urgencia": (r"(por que|porque) (agora|esse momento|neste momento)|quando (voc[eê] )?(quer|precisa|pretende) (come[cç]ar|resolver|ter)|"
                 r"quanto tempo (voc[eê] )?(vai|pretende|quer|aguenta)|se (nada|n[aã]o) (mudar|fizer nada)|o que acontece se",
                 ("prazo_momento",)),
}
PORTAS_RX = {k: re.compile(v[0], re.I) for k, v in PORTAS.items()}
STOP = set("""quando porque porqu entao assim aquele aquela isso essa esse esta este estou estava ainda muito mais
menos sobre tambem depois antes agora hoje gente voces voce minha minhas meus nosso nossa nossos coisa coisas tudo todo
todos toda todas fazer feito ficar ficou outra outro outras outros mesmo mesma pouco porque sempre nunca dentro fora
tenho tinha temos teria seria preciso precisa estar sendo tendo dessa desse disso nessa nesse nisso pessoa pessoas
porem talvez entendeu certo exatamente realmente""".split())


def norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def palavras(t):
    return {w for w in norm(t).split() if len(w) >= 5 and w not in STOP and not w.isdigit() and not w.startswith("pessoa")}


def cortes(linhas):
    """(fim_diagnostico, inicio_fechamento, investimento, contrato_sim_ou_nao) como índice de fala, ou None."""
    n = len(linhas)
    vend = [(i, l[10:]) for i, l in enumerate(linhas) if l.startswith("VENDEDOR: ")]
    d = next((i for i, t in vend if i >= 0.15 * n and RECAP_RX.search(t)), None)
    p = next((i for i, t in vend if i > (d or 0) and PRECO_RX.search(t)), None)
    f = contrato = None
    if d is not None and p is not None:
        amarras = [i for i, t in vend if d < i < p and AMARRA_RX.search(t)]
        reta_final = d + FECHAMENTO_RETA_FINAL * (p - d)
        f = next((i for i in reversed(amarras) if i >= reta_final), None)
        contrato = next((i for i in amarras if i < reta_final), None)
    return d, f, p, contrato


def etapa_de(i, d, f, p):
    if i is None or d is None:
        return None
    if i < d:
        return "diagnostico"
    if p is not None and i >= p:
        return "fechamento_pos"
    if f is not None and i >= f:
        return "fechamento_pre"
    return "apresentacao"


def carregar():
    nivel = {r["cliente"]: r["nivel"] for r in csv.DictReader(
        open(PASTA / "sinais_venda_clientes.csv", encoding="utf-8-sig"), delimiter=";")}
    reunioes = []
    for s in csv.DictReader(open(LOTE / "selecao.csv", encoding="utf-8-sig"), delimiter=";"):
        f = EXTR / f"{s['id']}.json"
        if not f.exists():
            continue
        linhas = (LOTE / "textos" / f"{s['id']}.txt").read_text(encoding="utf-8").splitlines()
        linhas_n = [norm(re.sub(r"^(VENDEDOR|PESSOA_\w+): ", "", l)) for l in linhas]
        d, fe, p, contrato = cortes(linhas)
        dur, chars = float(s["duracao_min"] or 0), int(s["chars"] or 0)
        s.update(extracao=json.loads(f.read_text(encoding="utf-8"))["extracao"], linhas=linhas, linhas_n=linhas_n,
                 d=d, f=fe, p=p, contrato=contrato, grupo=GRUPO.get(nivel.get(s["cliente"])),
                 longa=dur >= 30 or (dur == 0 and chars >= MIN_CHARS_SEM_DURACAO))
        reunioes.append(s)
    return reunioes


def posicao(r, citacao):
    alvo = norm(citacao)
    if not alvo:
        return None
    i = next((k for k, l in enumerate(r["linhas_n"]) if alvo in l), None)
    if i is None:  # citação que atravessa 2 falas: procura pelo começo
        inicio = " ".join(alvo.split()[:6])
        i = next((k for k, l in enumerate(r["linhas_n"]) if inicio in l), None)
    return i


def etapa_item(r, citacao):
    return etapa_de(posicao(r, citacao), r["d"], r["f"], r["p"])


def texto_vendedor(r, ini, fim):
    return " ".join(r["linhas"][i][10:] for i in range(ini, fim) if r["linhas"][i].startswith("VENDEDOR: "))


def pct(n, total):
    return round(100 * n / total, 1) if total else None


def amostra(reunioes, qtd=10):
    random.seed(23)
    com = [r for r in reunioes if r["d"] is not None]
    linhas = []
    for r in random.sample(com, qtd):
        n = len(r["linhas"])
        linhas.append(f"\n===== {r['id']} ({n} falas) diagnóstico até {r['d']} ({pct(r['d'], n)}%) | contrato {r['contrato']} | "
                      f"fechamento_pre {r['f']} | investimento {r['p']} ({pct(r['p'], n) if r['p'] else '-'}%)")
        for nome, i in (("FIM DO DIAGNÓSTICO", r["d"]), ("CONTRATO SIM OU NÃO", r["contrato"]),
                        ("INÍCIO DO FECHAMENTO", r["f"]), ("INVESTIMENTO", r["p"])):
            if i is None:
                continue
            linhas.append(f"--- {nome}")
            for k in range(max(0, i - 2), min(n, i + 3)):
                linhas.append(("▶ " if k == i else "  ") + r["linhas"][k][:300])
    (PASTA / "etapas_amostra.txt").write_text("\n".join(linhas), encoding="utf-8")


def analise_portas(reunioes):
    """Pergunta de 'porta' no diagnóstico × a objeção que ela deveria evitar depois do diagnóstico.
    Todas as reuniões com diagnóstico e investimento marcados — não depende dos grupos de venda."""
    base = [r for r in reunioes if r["d"] is not None and r["p"] is not None]
    out = {"reunioes": len(base)}
    for porta, (_, categorias) in PORTAS.items():
        cont = {True: Counter(), False: Counter()}
        for r in base:
            perguntou = bool(PORTAS_RX[porta].search(texto_vendedor(r, 0, r["d"])))
            objs = [o for o in r["extracao"]["objecoes"] if o.get("categoria") in categorias
                    and etapa_item(r, o.get("citacao_cliente")) in ("apresentacao", "fechamento_pre", "fechamento_pos")]
            cont[perguntou]["n"] += 1
            cont[perguntou]["com_objecao"] += bool(objs)
            cont[perguntou]["objecoes"] += len(objs)
            cont[perguntou]["superadas"] += sum(o.get("desfecho") == "superada" for o in objs)
            cont[perguntou]["linhas"] += len(r["linhas"])
        out[porta] = {
            ("perguntou_no_diagnostico" if k else "nao_perguntou"): {
                "reunioes": c["n"], "%_com_essa_objecao_depois": pct(c["com_objecao"], c["n"]),
                "%_superadas": pct(c["superadas"], c["objecoes"]), "falas_por_reuniao": round(c["linhas"] / c["n"]) if c["n"] else None}
            for k, c in cont.items()}
    return out


def analise_conexao(reunioes):
    """Quanto das dores/objetivos ditos pelo cliente no diagnóstico o vendedor retoma depois.
    Placebo: as dores de OUTRA reunião contra a mesma apresentação — a diferença é a personalização."""
    random.seed(7)
    base = [r for r in reunioes if r["d"] is not None]
    dores_diag = {}
    for r in base:
        itens = [it for k in ("dores", "objetivos") for it in r["extracao"]["cliente"][k]
                 if etapa_item(r, it.get("citacao")) == "diagnostico"]
        dores_diag[r["id"]] = [ws for it in itens if len(ws := palavras(it.get("citacao"))) >= 2]

    def retomadas(conjuntos, texto_ws):
        if not conjuntos:
            return None
        return 100 * sum(len(ws & texto_ws) >= max(2, len(ws) // 2) for ws in conjuntos) / len(conjuntos)

    ids = [r["id"] for r in base if dores_diag[r["id"]]]
    por_grupo = defaultdict(lambda: {"propria": [], "placebo": []})
    primeira = {}
    for r in base:
        if r["grupo"] and r["longa"] and (r["cliente"] not in primeira or r["data"] < primeira[r["cliente"]]["data"]):
            primeira[r["cliente"]] = r
    primeiras = {r["id"] for r in primeira.values()}
    for r in base:
        if not dores_diag[r["id"]]:
            continue
        depois = palavras(texto_vendedor(r, r["d"], len(r["linhas"])))
        outro = random.choice([i for i in ids if i != r["id"]])
        prop, plac = retomadas(dores_diag[r["id"]], depois), retomadas(dores_diag[outro], depois)
        for chave in ["todas"] + ([r["grupo"]] if r["id"] in primeiras else []):
            por_grupo[chave]["propria"].append(prop)
            por_grupo[chave]["placebo"].append(plac)
    return {g: {"reunioes": len(v["propria"]),
                "%_dores_retomadas_mediana": round(statistics.median(v["propria"]), 1),
                "%_placebo_mediana": round(statistics.median(v["placebo"]), 1),
                "%_dores_retomadas_media": round(statistics.mean(v["propria"]), 1),
                "%_placebo_media": round(statistics.mean(v["placebo"]), 1)}
            for g, v in por_grupo.items() if v["propria"]}


def analise_fechamento(reunioes):
    """Amarração antes do preço (por cliente) + objeções depois do diagnóstico, por etapa."""
    primeira = {}
    for r in reunioes:
        if r["d"] is not None and r["grupo"] and r["longa"] and (
                r["cliente"] not in primeira or r["data"] < primeira[r["cliente"]]["data"]):
            primeira[r["cliente"]] = r
    amarra = {}
    for g in GRUPOS:
        rs = [r for r in primeira.values() if r["grupo"] == g]
        com_preco = [r for r in rs if r["p"] is not None]
        amarra[g] = {"n": len(rs), "%_chegou_no_investimento": pct(len(com_preco), len(rs)),
                     "%_contrato_sim_ou_nao_no_inicio_da_apresentacao_se_chegou":
                         pct(sum(r["contrato"] is not None for r in com_preco), len(com_preco)),
                     "%_amarracao_antes_do_investimento_se_chegou": pct(sum(r["f"] is not None for r in com_preco), len(com_preco))}

    tab = defaultdict(lambda: defaultdict(Counter))
    exemplos = []
    cat_etapa = defaultdict(Counter)
    for r in reunioes:
        for o in r["extracao"]["objecoes"]:
            et = etapa_item(r, o.get("citacao_cliente"))
            if not et:
                continue
            cat_etapa[et][o.get("categoria")] += 1
            if et != "fechamento_pos" or o.get("categoria") in ("preco", "capacidade_financeira"):
                continue  # dinheiro já está em padroes_vendeu.py
            tab[o.get("categoria")][o.get("tecnica")][o.get("desfecho")] += 1
            if o.get("desfecho") in ("superada", "parcial") and o.get("resposta_vendedor"):
                exemplos.append([r["id"], r["grupo"] or "", et, o.get("categoria"), o.get("tecnica"), o.get("desfecho"),
                                 o.get("contexto", ""), o.get("citacao_cliente", ""), o.get("o_que_o_cliente_quis_dizer", ""),
                                 o.get("resposta_vendedor", ""), o.get("intencao_do_vendedor", ""),
                                 o.get("reacao_cliente", ""), o.get("evidencia_desfecho", "")])
    tecnicas = {}
    for cat, por_tec in tab.items():
        tecnicas[cat] = {}
        for tec, c in sorted(por_tec.items(), key=lambda x: -sum(x[1].values())):
            com_reacao = c["superada"] + c["parcial"] + c["nao_superada"]
            tecnicas[cat][tec] = {"n": sum(c.values()), "superada": c["superada"], "parcial": c["parcial"],
                                  "nao_superada": c["nao_superada"], "%_superada_entre_com_reacao": pct(c["superada"], com_reacao)}
    ordem = {"superada": 0, "parcial": 1}
    exemplos.sort(key=lambda x: (x[3], ordem[x[5]], x[1] != "vendeu", x[0]))
    with open(PASTA / "etapas_exemplos_fechamento.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["reuniao", "grupo_cliente", "etapa", "categoria", "tecnica", "desfecho", "contexto", "citacao_cliente",
                    "o_que_quis_dizer", "resposta_vendedor", "intencao_do_vendedor", "reacao_cliente", "evidencia_desfecho"])
        w.writerows(exemplos)
    return {"amarracao_por_cliente": amarra,
            "objecoes_por_etapa": {e: dict(cat_etapa[e].most_common()) for e in ETAPAS},
            "fechamento_pos_tecnica_x_desfecho": tecnicas, "exemplos": len(exemplos)}


def analise_perguntas(reunioes):
    por_etapa = defaultdict(Counter)
    for r in reunioes:
        for q in r["extracao"]["perguntas_descoberta"]:
            et = etapa_item(r, q.get("citacao"))
            if et:
                por_etapa[et][q.get("spin")] += 1
    return {e: {k: pct(v, sum(por_etapa[e].values())) for k, v in por_etapa[e].most_common()} | {"n": sum(por_etapa[e].values())}
            for e in ETAPAS}


def main():
    reunioes = carregar()
    with open(PASTA / "etapas_reunioes.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["reuniao", "falas", "fim_diagnostico", "contrato_sim_ou_nao", "inicio_fechamento", "investimento"])
        w.writerows([r["id"], len(r["linhas"]), r["d"], r["contrato"], r["f"], r["p"]] for r in reunioes)
    amostra(reunioes)
    n = len(reunioes)
    com_d = [r for r in reunioes if r["d"] is not None]
    cobertura = {"reunioes": n, "com_fim_do_diagnostico": len(com_d),
                 "com_amarracao_antes_do_investimento": sum(r["f"] is not None for r in com_d),
                 "com_investimento": sum(r["p"] is not None for r in com_d),
                 "fim_diagnostico_%_mediana": round(statistics.median(100 * r["d"] / len(r["linhas"]) for r in com_d), 1),
                 "investimento_%_mediana": round(statistics.median(100 * r["p"] / len(r["linhas"]) for r in com_d if r["p"]), 1)}
    resultado = {"cobertura": cobertura, "perguntas_spin_por_etapa": analise_perguntas(reunioes),
                 "portas_do_diagnostico": analise_portas(reunioes), "conexao_apresentacao": analise_conexao(reunioes),
                 "fechamento": analise_fechamento(reunioes)}
    json.dump(resultado, open(PASTA / "etapas_analise.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(resultado, ensure_ascii=False, indent=1))


main()
