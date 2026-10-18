"""Etapa 1 — reuniões do Paulo: leitura, métricas da conversa, jornada por
cliente, resultado provisório e tabela de pseudônimos. Sem IA, tudo local.

Uso: python -I etapa1_paulo.py <saida> <zip1> [zip2 ...]
"""
import csv, io, json, re, statistics, sys, unicodedata, zipfile
from collections import Counter, defaultdict
from xml.etree import ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\phpos\OneDrive\SALE-IA\SALEIA")
from agent.turnos_rules import perguntas_do_texto  # noqa: E402
from agent.conversation_metrics_rules import PALAVRAS_ABERTURA_PADRAO, _tipo_pergunta  # noqa: E402

SAIDA = sys.argv[1]
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
VENDEDOR = "paulo henrique pagoti de oliveira silva"
HORA_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})$")
FALA_RE = re.compile(r"^([^:\n]{2,80}):\s+(.*)$")
FIM_RE = re.compile(r"encerrada após (\d{1,2}):(\d{2}):(\d{2})")
DATA_RE = re.compile(r"(\d{4})[_-](\d{2})[_-](\d{2})[ T](\d{2})[_:](\d{2})")
FECHOU_RE = re.compile(r"fech(amento|ou|ar|aram) (do |o |de |um |uma )?(contrato|neg[oó]cio|venda|parceria|mentoria|assessoria)"
                       r"|assinatura do contrato|contrato (foi )?assinado|pagamento (foi )?(realizado|efetuado|confirmado)"
                       r"|(realizou|efetuou|fez) o pagamento|confirmou a (contrata[cç][aã]o|compra|ades[aã]o)", re.I)
TIPOS = [("diagnostico", r"diagn[oó]stico"), ("consultoria_gratuita", r"consultoria gratuita"),
         ("performance", r"performance"), ("aceleracao", r"acelera"), ("reuniao_iniciada", r"reuni[aã]o iniciada")]
PALAVRAS_POR_SEGUNDO = 2.5  # ~150 palavras/min, para estimar monólogo (tempo por fala não existe aqui)


def norm(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    n = " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").lower().split())
    # "Apresentação de Paulo Henrique…" = o Paulo falando com a tela compartilhada.
    return VENDEDOR if VENDEDOR in n else n


# Confirmação no fim da frase ("…, né?", "concorda comigo?") não é pergunta
# de descoberta: o Gemini põe "?" em toda fala com entonação de pergunta.
TAGS = ("ne", "ta", "certo", "entendeu", "beleza", "ok", "sim", "concorda", "concorda comigo", "faz sentido",
        "tudo bem", "tudo bom", "tá bom", "ta bom", "combinado", "ta vendo", "pode ser", "e ai", "e voce", "por que",
        "por que nao", "sabe", "viu", "nao e", "fechou", "show", "perfeito", "isso", "e isso", "cade", "sera")


def pergunta_real(q):
    n = re.sub(r"[^\w\s,]", "", norm(q)).strip()
    if len(n.split()) < 3 or n in TAGS:
        return False
    ultima = n.rsplit(",", 1)
    return not (len(ultima) == 2 and ultima[1].strip() in TAGS)


def paragrafos(dados):
    with zipfile.ZipFile(io.BytesIO(dados)) as d:
        raiz = ET.fromstring(d.read("word/document.xml"))
    # Quebra de linha interna do Word (<w:br/>, <w:cr/>) separa falas dentro
    # do mesmo parágrafo em parte dos arquivos — vira linha própria.
    linhas = []
    for p in raiz.iter(W + "p"):
        partes = []
        for el in p.iter():
            if el.tag == W + "t":
                partes.append(el.text or "")
            elif el.tag in (W + "br", W + "cr"):
                partes.append("\n")
        linhas.extend(l.strip() for l in "".join(partes).split("\n"))
    return [l for l in linhas if l]


def secoes(pars):
    # "📖 Transcrição" (Anotações do Gemini) ou "Transcrição"/"Transcript" no topo (formato antigo "- Transcript.docx")
    i_t = next((i for i, p in enumerate(pars) if p.startswith("📖 Transcrição") or (i <= 10 and p in ("Transcrição", "Transcript"))), len(pars))
    cab = pars[:i_t]
    def bloco(nomes):
        i = next((k for k, p in enumerate(cab) if any(p.startswith(n) for n in nomes)), None)
        if i is None:
            return ""
        fim = next((k for k in range(i + 1, len(cab)) if cab[k] in ("Resumo", "Detalhes", "Próximas etapas", "Próximas etapas sugeridas")
                    or cab[k].startswith("Revise as anotações")), len(cab))
        return "\n".join(cab[i + 1:fim])
    return bloco(["Resumo"]), bloco(["Detalhes"]), bloco(["Próximas etapas"]), pars[i_t + 1:]


def ler(zips):
    vistos = {}
    for caminho in zips:
        z = zipfile.ZipFile(caminho)
        for info in z.infolist():
            if info.filename.lower().endswith(".docx") and info.filename not in vistos:
                vistos[info.filename] = paragrafos(z.read(info))
    return vistos


def analisar(arq, pars):
    resumo, detalhes, proximas, trans = secoes(pars)
    m = DATA_RE.search(arq)
    titulo = arq.split(" - 20")[0].strip()
    tipo = next((t for t, r in TIPOS if re.search(r, arq, re.I)), "outro")
    falas, hora = [], 0
    duracao = None
    for p in trans:
        h = HORA_RE.match(p)
        if h:
            hora = int(h[1]) * 3600 + int(h[2]) * 60 + int(h[3])
            continue
        f = FIM_RE.search(p)
        if f:
            duracao = int(f[1]) * 3600 + int(f[2]) * 60 + int(f[3])
            continue
        fm = FALA_RE.match(p)
        if fm and not p.startswith("Esta transcrição"):
            falas.append({"t": hora, "falante": fm[1].strip(), "texto": fm[2].strip()})
    vend = [f for f in falas if norm(f["falante"]) == VENDEDOR]
    outros = [f for f in falas if norm(f["falante"]) != VENDEDOR]
    pv = sum(len(f["texto"].split()) for f in vend)
    po = sum(len(f["texto"].split()) for f in outros)
    todas = [q for f in vend for q in perguntas_do_texto(f["texto"])]
    perguntas = [q for q in todas if pergunta_real(q)]
    abertas = sum(1 for q in perguntas if _tipo_pergunta(q, PALAVRAS_ABERTURA_PADRAO) == "aberta")
    cli_perg = sum(1 for f in outros for q in perguntas_do_texto(f["texto"]) if pergunta_real(q))
    # maior trecho seguido do Paulo (palavras) → monólogo estimado
    maior, atual = 0, 0
    for f in falas:
        atual = atual + len(f["texto"].split()) if norm(f["falante"]) == VENDEDOR else 0
        maior = max(maior, atual)
    texto_fim = " ".join([resumo, detalhes, proximas])
    return {
        "arquivo": arq, "titulo": titulo, "tipo": tipo,
        "data": f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}" if m else None,
        "duracao_s": duracao, "tem_transcricao": len(falas) >= 20,
        "falantes": Counter(f["falante"] for f in falas),
        "palavras_vendedor": pv, "palavras_cliente": po,
        "pct_fala_vendedor": round(100 * pv / (pv + po), 1) if pv + po else None,
        "perguntas_vendedor": len(perguntas), "perguntas_abertas": abertas,
        "confirmacoes_vendedor": len(todas) - len(perguntas), "perguntas_cliente": cli_perg,
        "maior_trecho_vendedor_palavras": maior,
        "monologo_estimado_s": round(maior / PALAVRAS_POR_SEGUNDO),
        "resumo_vazio": "não foi gerado" in resumo or "não havia conversas" in resumo,
        "fechou_pelo_resumo": bool(FECHOU_RE.search(texto_fim)),
        "resumo": resumo, "detalhes": detalhes, "proximas_etapas": proximas, "falas": falas,
    }



def deduplicar(reunioes):
    """A mesma reunião pode vir 2x (Anotações do Gemini + Transcript.docx):
    mesmo dia, mesmos participantes e falas iguais → fica a mais completa."""
    grupos = defaultdict(list)
    for r in reunioes:
        outros = frozenset(norm(n) for n in r["falantes"] if norm(n) != VENDEDOR)
        if r["tem_transcricao"] and r["data"] and outros:
            grupos[(r["data"][:10], outros)].append(r)
    fora = set()
    for rs in grupos.values():
        rs.sort(key=lambda r: -len(r["falas"]))
        for i, a in enumerate(rs):
            if a["arquivo"] in fora:
                continue
            ta = {norm(f["texto"]) for f in a["falas"][:60]}
            for b in rs[i + 1:]:
                tb = {norm(f["texto"]) for f in b["falas"][:60]}
                if len(ta & tb) >= 0.5 * min(len(ta), len(tb)):
                    fora.add(b["arquivo"])
                    a.setdefault("copias", []).append(b["arquivo"])
    print(f"duplicadas removidas: {len(fora)}", file=sys.stderr)
    return [r for r in reunioes if r["arquivo"] not in fora]

def main():
    docs = ler(sys.argv[2:])
    reunioes = [analisar(a, p) for a, p in docs.items()]
    reunioes = deduplicar(reunioes)
    reunioes.sort(key=lambda r: r["data"] or "")

    # Equipe = quem fala em muitas reuniões com clientes diferentes (não é cliente).
    presenca = Counter(norm(n) for r in reunioes for n in r["falantes"] if norm(n) != VENDEDOR)
    equipe = {n for n, c in presenca.items() if c >= 15}

    # Jornada: reuniões ligadas por um mesmo cliente (falante) — union-find.
    pai = list(range(len(reunioes)))
    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    dono = {}
    for i, r in enumerate(reunioes):
        nomes = [norm(n) for n in r["falantes"] if norm(n) != VENDEDOR and norm(n) not in equipe and len(norm(n).split()) >= 1]
        if not nomes and r["titulo"] and not r["titulo"].lower().startswith("reuni"):
            t = re.sub(r"(diagn[oó]stico|consultoria gratuita|⚡|_|-)", " ", r["titulo"], flags=re.I)
            nomes = [norm(t)] if norm(t) else []
        r["chaves_cliente"] = nomes
        for n in nomes:
            if n in dono:
                pai[raiz(i)] = raiz(dono[n])
            else:
                dono[n] = i
    grupos = defaultdict(list)
    for i in range(len(reunioes)):
        grupos[raiz(i)].append(i)

    # Pseudônimos: cada pessoa → código; Paulo → VENDEDOR_REF. Códigos já dados
    # são mantidos (os textos do piloto usam esses códigos); nomes novos entram no fim.
    pseud = {VENDEDOR: "VENDEDOR_REF"}
    try:
        for row in csv.DictReader(open(f"{SAIDA}/mapa_pseudonimos.csv", encoding="utf-8-sig"), delimiter=";"):
            pseud[row["nome_normalizado"]] = row["codigo"]
    except FileNotFoundError:
        pass
    proximo = 1 + max((int(c.split("_")[-1]) for c in pseud.values() if c[-4:].isdigit()), default=0)
    for n in sorted({norm(n) for r in reunioes for n in r["falantes"]}):
        if n not in pseud:
            pseud[n] = ("EQUIPE_" if n in equipe else "PESSOA_") + f"{proximo:04d}"
            proximo += 1

    jornadas = []
    for k, (g, idx) in enumerate(sorted(grupos.items(), key=lambda kv: reunioes[kv[1][0]]["data"] or "")):
        rs = [reunioes[i] for i in idx]
        cod = f"CLIENTE_{k + 1:04d}"
        for r in rs:
            r["cliente"] = cod
        fechou = any(r["fechou_pelo_resumo"] for r in rs)
        jornadas.append({"cliente": cod, "reunioes": len(rs), "com_transcricao": sum(r["tem_transcricao"] for r in rs),
                         "primeira": rs[0]["data"], "ultima": rs[-1]["data"],
                         "tipos": "→".join(r["tipo"] for r in rs), "fechou_provisorio": fechou,
                         "nomes_reais": " | ".join(sorted({n for r in rs for n in r["chaves_cliente"]}))[:200]})

    # Saídas
    with open(f"{SAIDA}/reunioes.jsonl", "w", encoding="utf-8") as f:
        for r in reunioes:
            d = dict(r, falantes=dict(r["falantes"]))
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    campos = ["cliente", "arquivo", "data", "tipo", "duracao_s", "tem_transcricao", "pct_fala_vendedor", "perguntas_vendedor",
              "perguntas_abertas", "confirmacoes_vendedor", "perguntas_cliente", "monologo_estimado_s", "resumo_vazio", "fechou_pelo_resumo"]
    with open(f"{SAIDA}/reunioes_metricas.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, campos, extrasaction="ignore", delimiter=";")
        w.writeheader()
        w.writerows(reunioes)
    with open(f"{SAIDA}/clientes_jornada.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(jornadas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(jornadas)
    with open(f"{SAIDA}/mapa_pseudonimos.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["nome_normalizado", "codigo"])
        w.writerows(sorted(pseud.items(), key=lambda kv: kv[1]))

    # Resumo para o relatório
    ct = [r for r in reunioes if r["tem_transcricao"] and r["pct_fala_vendedor"] is not None]
    def med(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.median(xs), 1) if xs else None
    def grupo(rs):
        return {"n": len(rs), "fala_vendedor_%": med(r["pct_fala_vendedor"] for r in rs),
                "perguntas": med(r["perguntas_vendedor"] for r in rs),
                "%_abertas": med(100 * r["perguntas_abertas"] / r["perguntas_vendedor"] for r in rs if r["perguntas_vendedor"]),
                "monologo_s": med(r["monologo_estimado_s"] for r in rs), "confirmacoes": med(r["confirmacoes_vendedor"] for r in rs), "perguntas_cliente": med(r["perguntas_cliente"] for r in rs),
                "duracao_min": med(r["duracao_s"] / 60 for r in rs if r["duracao_s"])}
    fechou_cli = {j["cliente"] for j in jornadas if j["fechou_provisorio"]}
    resumo = {
        "reunioes": len(reunioes), "com_transcricao": len(ct), "clientes": len(jornadas),
        "clientes_com_2+_reunioes": sum(1 for j in jornadas if j["reunioes"] >= 2),
        "clientes_fechou_provisorio": len(fechou_cli),
        "equipe_detectada": sorted(pseud[n] for n in equipe),
        "pessoas_pseudonimizadas": len(pseud),
        "geral": grupo(ct),
        "por_tipo": {t: grupo([r for r in ct if r["tipo"] == t]) for t in sorted({r["tipo"] for r in ct})},
        "clientes_que_fecharam": grupo([r for r in ct if r["cliente"] in fechou_cli]),
        "clientes_sem_fechamento": grupo([r for r in ct if r["cliente"] not in fechou_cli]),
    }
    json.dump(resumo, open(f"{SAIDA}/resumo_etapa1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


main()
