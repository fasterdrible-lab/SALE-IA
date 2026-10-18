"""Inventário dos zips do Paulo (só contagens; não grava conteúdo)."""
import io, re, sys, zipfile, json
from collections import Counter
from xml.etree import ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FALA_RE = re.compile(r"^(\d{1,2}:\d{2}(:\d{2})?\s*)?[^:\n]{2,60}:\s+\S")
HORA_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
DATA_RE = re.compile(r"(\d{4})_(\d{2})_(\d{2})")
FECHOU_RE = re.compile(r"fech(amento|ou|ar) (do |o |de )?(contrato|neg[oó]cio|venda)|assinatura do contrato|contrato (foi )?assinado|pagamento (foi )?(realizado|efetuado|confirmado)", re.I)
NAO_RE = re.compile(r"n[aã]o (foi gerado|havia conversas)", re.I)
TIPO_RE = [("consultoria_gratuita", re.compile(r"consultoria gratuita", re.I)),
           ("diagnostico", re.compile(r"diagn[oó]stico", re.I)),
           ("reuniao_iniciada", re.compile(r"reuni[aã]o iniciada", re.I))]


def paragrafos(dados):
    with zipfile.ZipFile(io.BytesIO(dados)) as d:
        raiz = ET.fromstring(d.read("word/document.xml"))
    out = []
    for p in raiz.iter(W + "p"):
        t = "".join(x.text or "" for x in p.iter(W + "t")).strip()
        if t:
            out.append(t)
    return out


linhas = []
for caminho in sys.argv[1:]:
    z = zipfile.ZipFile(caminho)
    for info in z.infolist():
        if not info.filename.lower().endswith(".docx"):
            continue
        try:
            pars = paragrafos(z.read(info))
        except Exception as e:
            linhas.append({"arq": info.filename, "erro": type(e).__name__})
            continue
        i_t = next((i for i, p in enumerate(pars) if p.startswith("📖 Transcrição") or p.startswith("Transcrição") and i > 5), None)
        resumo = " ".join(pars[:i_t] if i_t else pars)
        trans = pars[i_t + 1:] if i_t is not None else []
        falas = sum(1 for p in trans if FALA_RE.match(p))
        horas = sum(1 for p in trans if HORA_RE.match(p))
        m = DATA_RE.search(info.filename)
        tipo = next((t for t, r in TIPO_RE if r.search(info.filename)), "outro")
        linhas.append({
            "arq": info.filename, "kb": info.file_size // 1000, "data": "-".join(m.groups()) if m else None,
            "tipo": tipo, "chars_resumo": len(resumo), "chars_trans": sum(len(p) for p in trans),
            "linhas_trans": len(trans), "falas_rotuladas": falas, "marcas_hora": horas,
            "resumo_vazio": bool(NAO_RE.search(resumo)), "fechou_no_resumo": bool(FECHOU_RE.search(resumo)),
            "paulo": "Paulo Henrique" in resumo,
        })

ok = [l for l in linhas if "erro" not in l]
com_trans = [l for l in ok if l["chars_trans"] > 2000]
print("docx lidos:", len(ok), "| com erro:", len(linhas) - len(ok))
print("nomes repetidos (mesmo arquivo em 2 zips):", sum(c - 1 for c in Counter(l["arq"] for l in ok).values() if c > 1))
print("resumo vazio (Gemini não gerou):", sum(l["resumo_vazio"] for l in ok))
print("com TRANSCRIÇÃO completa (>2.000 chars):", len(com_trans),
      "| mediana chars:", sorted(l["chars_trans"] for l in com_trans)[len(com_trans) // 2] if com_trans else 0)
print("   falas com rótulo 'Nome:' (mediana):", sorted(l["falas_rotuladas"] for l in com_trans)[len(com_trans) // 2] if com_trans else 0,
      "| marcas de hora (mediana):", sorted(l["marcas_hora"] for l in com_trans)[len(com_trans) // 2] if com_trans else 0)
print("só resumo útil (sem transcrição, resumo não vazio):", sum(1 for l in ok if l["chars_trans"] <= 2000 and not l["resumo_vazio"]))
print("Paulo citado no resumo:", sum(l["paulo"] for l in ok))
print("resumo indica fechamento:", sum(l["fechou_no_resumo"] for l in ok))
print("tipo pelo nome:", Counter(l["tipo"] for l in ok).most_common())
datas = sorted(l["data"] for l in ok if l["data"])
print("período:", datas[0] if datas else None, "→", datas[-1] if datas else None)
print("por mês:", sorted(Counter(d[:7] for d in datas).items()))
print("transcrição por mês:", sorted(Counter(l["data"][:7] for l in com_trans if l["data"]).items()))
json.dump(linhas, open(sys.argv[0].replace("inventario.py", "inventario.json"), "w", encoding="utf-8"), ensure_ascii=False)
