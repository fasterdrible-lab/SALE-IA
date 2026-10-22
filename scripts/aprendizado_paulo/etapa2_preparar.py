"""Etapa 2 — prepara o piloto: escolhe 50 reuniões (metade de clientes que
fecharam pelo resumo do Gemini, metade não; vários tipos) e troca nomes,
e-mails, telefones e documentos por códigos antes de qualquer envio à IA.

Saída: piloto/selecao.csv, piloto/textos/<id>.txt (pseudonimizado), piloto/estimativa.json

Com "todas" (21/10/2026): todas as reuniões com transcrição, sem sorteio,
em completo/ (ids C0001…), sem tocar no piloto.
"""
import csv, json, random, re, sys, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
D = Path(r"C:\SALEIA_dados\paulo")
TODAS = len(sys.argv) > 1 and sys.argv[1] == "todas"
P = D / ("completo" if TODAS else "piloto")
(P / "textos").mkdir(parents=True, exist_ok=True)
VENDEDOR = "paulo henrique pagoti de oliveira silva"
N = 0 if TODAS else int(sys.argv[1]) if len(sys.argv) > 1 else 50


def norm(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    n = " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").lower().split())
    return VENDEDOR if VENDEDOR in n else n


mapa = {r["nome_normalizado"]: r["codigo"] for r in csv.DictReader(open(D / "mapa_pseudonimos.csv", encoding="utf-8-sig"), delimiter=";")}
# Palavras comuns que também são nomes/sobrenomes — não trocar soltas no meio da fala.
COMUNS = {"bom", "boa", "sim", "nao", "rosa", "flor", "luz", "santos", "jesus", "deus", "cruz", "paz", "guerra", "mar",
          "neves", "campos", "costa", "silva", "souza", "lima", "alves", "rocha", "ramos", "reis", "dias", "nunes",
          "pereira", "oliveira", "ferreira", "rodrigues", "gomes", "martins", "araujo", "ribeiro", "carvalho", "barbosa",
          "vieira", "pinto", "moura", "mendes", "freitas", "cardoso", "teixeira", "correia", "monteiro", "batista",
          "brasil", "paulo", "henrique", "pagoti", "presentation", "apresentacao", "de", "da", "do", "dos", "das", "e"}
primeiros = {}
for nome, cod in mapa.items():
    if nome == VENDEDOR:
        continue
    partes = nome.split()
    if partes and len(partes[0]) >= 3 and partes[0] not in COMUNS:
        primeiros.setdefault(partes[0], cod)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
FONE = re.compile(r"(?<!\d)(\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\d)")
CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def pseudonimizar(texto, nomes_reuniao):
    """nomes_reuniao: {nome original do falante: código}. Troca nome completo,
    cada parte do nome desses falantes e primeiros nomes conhecidos de
    outros clientes (só com inicial maiúscula)."""
    t = EMAIL.sub("[EMAIL]", texto)
    t = CNPJ.sub("[CNPJ]", t)
    t = CPF.sub("[CPF]", t)
    t = FONE.sub("[TELEFONE]", t)
    for original, cod in sorted(nomes_reuniao.items(), key=lambda kv: -len(kv[0])):
        t = re.sub(re.escape(original), cod, t, flags=re.I)
        for parte in original.split():
            if len(parte) >= 3 and norm(parte) not in COMUNS:
                for v in {parte, sem_acento(parte)}:
                    t = re.sub(rf"\b{re.escape(v)}\b", cod, t, flags=re.I)

    def troca(m):
        return primeiros.get(norm(m.group(0)), m.group(0))
    return re.sub(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,}\b", troca, t)


reunioes = [json.loads(l) for l in open(D / "reunioes.jsonl", encoding="utf-8")]
jornada = {r["cliente"]: r for r in csv.DictReader(open(D / "clientes_jornada.csv", encoding="utf-8-sig"), delimiter=";")}
if TODAS:
    escolha = [r for r in reunioes if r["tem_transcricao"]]
else:
    cand = [r for r in reunioes if r["tem_transcricao"] and r["duracao_s"] and 1800 <= r["duracao_s"] <= 7200
            and jornada.get(r["cliente"], {}).get("reunioes") in ("1", "2", "3", "4", "5")]
    random.seed(20261017)
    fechou = [r for r in cand if jornada[r["cliente"]]["fechou_provisorio"] == "True"]
    nao = [r for r in cand if jornada[r["cliente"]]["fechou_provisorio"] != "True"]
    escolha = random.sample(fechou, min(N // 2, len(fechou))) + random.sample(nao, min(N - N // 2, len(nao)))
escolha.sort(key=lambda r: r["data"])

linhas, chars = [], 0
for i, r in enumerate(escolha, 1):
    rid = f"C{i:04d}" if TODAS else f"R{i:03d}"
    nomes = {f: ("VENDEDOR" if norm(f) == VENDEDOR else mapa.get(norm(f), "PESSOA_X")) for f in r["falantes"]}
    corpo = "\n".join(f"{nomes.get(f['falante'], 'PESSOA_X')}: {f['texto']}" for f in r["falas"] if not f["texto"].rstrip().endswith("- Transcrição"))
    corpo = pseudonimizar(corpo, {k: v for k, v in nomes.items() if v != "VENDEDOR"})
    corpo = re.sub(r"Paulo Henrique Pagoti de Oliveira Silva", "VENDEDOR", corpo, flags=re.I)
    (P / "textos" / f"{rid}.txt").write_text(corpo, encoding="utf-8")
    chars += len(corpo)
    linhas.append({"id": rid, "cliente": r["cliente"], "arquivo": r["arquivo"], "data": r["data"], "tipo": r["tipo"],
                   "duracao_min": round((r["duracao_s"] or 0) / 60),
                   "fechou_provisorio": jornada.get(r["cliente"], {}).get("fechou_provisorio", ""),
                   "chars": len(corpo)})
with open(P / "selecao.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, list(linhas[0].keys()), delimiter=";")
    w.writeheader()
    w.writerows(linhas)
tokens_in = chars / 3.2 + len(linhas) * 2500  # ~3,2 chars/token em pt + prompt
est = {"reunioes": len(linhas), "chars": chars, "tokens_entrada_estimados": round(tokens_in),
       "custo_pro_fora_pico_usd": round(tokens_in / 1e6 * 0.66 + len(linhas) * 5000 / 1e6 * 1.98, 2),
       "custo_flash_fora_pico_usd": round(tokens_in / 1e6 * 0.15 + len(linhas) * 5000 / 1e6 * 0.6, 2)}
json.dump(est, open(P / "estimativa.json", "w"), indent=1)
print(json.dumps(est, indent=1))
print("fechou/não:", sum(l["fechou_provisorio"] == "True" for l in linhas), "/", sum(l["fechou_provisorio"] != "True" for l in linhas))
print("tipos:", {t: sum(l["tipo"] == t for l in linhas) for t in {l["tipo"] for l in linhas}})
