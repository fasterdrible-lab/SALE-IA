"""T6 da auditoria (SALEIA_Relatorio_Detalhado_Auditoria_67_Registros.docx,
17/10/2026): casos fixos que toda versão do extrator precisa passar.

Uso: python -I regressao_auditoria.py [pasta_de_extracoes]
Cada caso acha o item extraído pela citação (sobreposição de palavras) e
confere a regra. Item que a versão nova não extraiu = "não extraído" (não
conta como falha, mas aparece no relatório).
"""
import json, re, sys, unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PASTA = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\SALEIA_dados\paulo\piloto\extracoes_deepseek-flash")

# Casos fora do git (têm citações de clientes): C:\SALEIA_dados\paulo\casos_auditoria.json
CASOS_JSON = r"C:\SALEIA_dados\paulo\casos_auditoria.json"
CASOS = [tuple(c) for c in json.load(open(CASOS_JSON, encoding="utf-8"))]


def norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return " ".join(re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).split())


def sobrepoe(a, b):
    pa, pb = set(norm(a).split()), set(norm(b).split())
    return len(pa & pb) / max(1, min(len(pa), len(pb))) >= 0.6 if pa and pb else False


def checar(caso, e):
    cid, rid, tipo, trecho, regra = caso
    if tipo == "resultado":
        r = e["resultado"]
        st = {"reuniao_seguinte_marcada": "reuniao_confirmada", "fechou": "pagamento_confirmado"}.get(r.get("status"), r.get("status"))
        ok = st not in ("reuniao_confirmada", "pagamento_confirmado") or bool(r.get("evidencia_aceite_cliente"))
        return ok, f"{st} | aceite: {r.get('evidencia_aceite_cliente', '')[:60]}"
    if tipo == "objecao":
        it = next((o for o in e["objecoes"] if sobrepoe(o.get("citacao_cliente"), trecho)), None)
        if not it:
            return None, "não extraído"
        if it.get("desfecho") != "superada":
            return True, it.get("desfecho")
        # "superada" só vale com fala do CLIENTE, depois da objeção, provando o aceite
        linhas = (PASTA.parent / "textos" / f"{rid}.txt").read_text(encoding="utf-8").splitlines()
        def pos(c):
            a = norm(c)
            return next((k for k, l in enumerate(linhas) if a and a in norm(l)), None)
        po, pe = pos(it["citacao_cliente"]), pos(it.get("evidencia_desfecho"))
        ok = po is not None and pe is not None and pe > po and not linhas[pe].startswith("VENDEDOR:")
        return ok, f"superada | prova (fala {pe}, objeção {po}): {it.get('evidencia_desfecho', '')[:60]}"
    it = next((q for q in e["perguntas_descoberta"] if sobrepoe(q.get("citacao"), trecho)), None)
    if not it:
        return None, "não extraído"
    ra = it.get("resposta_atende")
    ok = ra in ("nao", "parcial", "sem_resposta") if "in (nao" in regra else ra == "sim"
    return ok, f"{ra} | resposta: {it.get('resposta_do_cliente', '')[:60]}"


ex = {p.stem: json.loads(p.read_text(encoding="utf-8"))["extracao"] for p in PASTA.glob("R*.json")}
passou = falhou = ausente = 0
for caso in CASOS:
    ok, det = checar(caso, ex[caso[1]])
    marca = "PASSOU" if ok else ("—" if ok is None else "FALHOU")
    passou += ok is True
    falhou += ok is False
    ausente += ok is None
    print(f"{caso[0]} {caso[1]} {caso[2]:9} {marca:7} {caso[4][:45]:45} → {det}")
print(f"\n{passou} passaram, {falhou} falharam, {ausente} não extraídos (de {len(CASOS)})")
