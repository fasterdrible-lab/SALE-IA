import csv, json, sys
from collections import Counter
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\SALEIA_dados\paulo\piloto")
sel = {r["id"]: r for r in csv.DictReader(open(P / "selecao.csv", encoding="utf-8-sig"), delimiter=";")}
M = ["deepseek-v4-pro", "deepseek-flash"]
ex = {m: {p.stem: json.loads(p.read_text(encoding="utf-8"))["extracao"] for p in (P / f"extracoes_{m}").glob("R*.json")} for m in M}
print(f"{'id':5} {'tipo':22} {'gemini':6} | {'pro: tipo/resultado':42} | flash: tipo/resultado")
for rid in sorted(ex[M[0]]):
    a, b = ex[M[0]][rid], ex[M[1]].get(rid, {})
    print(f"{rid:5} {sel[rid]['tipo']:22} {sel[rid]['fechou_provisorio'][:5]:6} | "
          f"{a['tipo_reuniao'] + '/' + a['resultado'].get('status', ''):42} | {b.get('tipo_reuniao')}/{(b.get('resultado') or {}).get('status')}")
for m in M:
    obj = [o for e in ex[m].values() for o in e["objecoes"]]
    perg = [q for e in ex[m].values() for q in e["perguntas_descoberta"]]
    print(f"\n{m}: objeções {len(obj)} {Counter(o['categoria'] for o in obj).most_common(5)}")
    print("   técnicas:", Counter(o["tecnica"] for o in obj).most_common(6))
    print("   desfecho:", Counter(o["desfecho"] for o in obj).most_common())
    print("   perguntas SPIN:", Counter(q["spin"] for q in perg).most_common())
rid = "R004"
for m in M:
    print(f"\n--- {m} {rid} objeções:")
    for o in ex[m][rid]["objecoes"][:3]:
        print(f"  [{o['categoria']}/{o['tecnica']}/{o['desfecho']}]")
        print(f"    CLIENTE: {o['citacao_cliente'][:150]}")
        print(f"    VENDEDOR: {o.get('resposta_vendedor', '')[:150]}")
