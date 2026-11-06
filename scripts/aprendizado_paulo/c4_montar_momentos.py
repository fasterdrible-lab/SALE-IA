"""C4 — passo 1: monta os momentos de teste a partir das reuniões do Paulo.
Sem IA, sem custo.

Momento = objeção real do cliente, já extraída na Etapa 2, com a conversa
cortada logo depois da fala do cliente (antes da resposta do vendedor) e a
resposta real do Paulo como gabarito, com o desfecho (superada / parcial /
não superada, validado pela fala do cliente depois — v4).

Amostra estratificada e fixa (seed): 100 superadas, 50 parciais, 50 não
superadas; metade objeção de dinheiro (preco/capacidade_financeira),
metade os outros tipos (quando houver). A conversa vai no formato que a
produção manda para a IA (`Vendedor:` / `Cliente:`), com os mesmos cortes
de 6.000 caracteres de `api/processador_tempo_real.py::_limitar_contexto_ia`
para `transcricao_parcial` (o trecho mais recente) e `historico` (o anterior).

Uso: python -I c4_montar_momentos.py [pasta_dados] [rodada]
Saída (fora do git, conversa pseudonimizada): <pasta>/c4/momentos.json

Com `rodada` (ex.: rodada2), a saída vai para <pasta>/rodada2/c4/momentos.json:
200 superadas + 50 + 50, sem nenhuma reunião da amostra original, para medir
com casos que não serviram de diagnóstico e separar 40% de 50% (margem de ~7
pontos com 200 superadas; ~10 com 100).
"""
import json, random, re, sys, unicodedata
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PASTA = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\SALEIA_dados\paulo")
LOTE = PASTA / "completo"
EXTR = LOTE / "extracoes_deepseek-flash"
RODADA = sys.argv[2] if len(sys.argv) > 2 else None
ORIGINAL = PASTA / "c4" / "momentos.json"
SAIDA = PASTA / RODADA / "c4" if RODADA else PASTA / "c4"
DINHEIRO = ("preco", "capacidade_financeira")
COTA = {"superada": 200 if RODADA else 100, "parcial": 50, "nao_superada": 50}
MAX_CHARS = 6000  # _MAX_CONTEXT_CHARS de api/processador_tempo_real.py
MIN_FALAS_ANTES = 20  # objeção no começo da conversa não tem contexto para sugerir nada


def norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def rotulo(linha):
    return re.sub(r"^VENDEDOR: ", "Vendedor: ", re.sub(r"^PESSOA_\w+: ", "Cliente: ", linha))


def candidatos():
    for f in sorted(EXTR.glob("*.json")):
        rid = f.stem
        e = json.loads(f.read_text(encoding="utf-8"))["extracao"]
        linhas = (LOTE / "textos" / f"{rid}.txt").read_text(encoding="utf-8").splitlines()
        linhas_n = [norm(re.sub(r"^(VENDEDOR|PESSOA_\w+): ", "", l)) for l in linhas]
        for k, o in enumerate(e["objecoes"]):
            if o.get("desfecho") not in COTA or not o.get("resposta_vendedor"):
                continue
            alvo = norm(o.get("citacao_cliente"))
            i = next((j for j, l in enumerate(linhas_n) if alvo and alvo in l), None)
            if i is None or i < MIN_FALAS_ANTES or linhas[i].startswith("VENDEDOR: "):
                continue
            fim = i  # inclui as falas seguidas do cliente, até o vendedor responder
            while fim + 1 < len(linhas) and not linhas[fim + 1].startswith("VENDEDOR: "):
                fim += 1
            conversa = "\n".join(rotulo(l) for l in linhas[:fim + 1])
            yield {
                "id": f"{rid}-obj{k + 1:02d}", "reuniao": rid, "categoria": o.get("categoria"),
                "grupo_categoria": "dinheiro" if o.get("categoria") in DINHEIRO else "outras",
                "desfecho": o["desfecho"], "posicao_%": round(100 * i / len(linhas), 1),
                "transcricao_parcial": conversa[-MAX_CHARS:],
                "historico": conversa[:-MAX_CHARS][-MAX_CHARS:] or "Inicio da conversa",
                "gabarito": {
                    "citacao_cliente": o.get("citacao_cliente"), "contexto": o.get("contexto"),
                    "o_que_o_cliente_quis_dizer": o.get("o_que_o_cliente_quis_dizer"),
                    "resposta_vendedor": o.get("resposta_vendedor"), "tecnica": o.get("tecnica"),
                    "intencao_do_vendedor": o.get("intencao_do_vendedor"), "reacao_cliente": o.get("reacao_cliente"),
                    "evidencia_desfecho": o.get("evidencia_desfecho"),
                    "continuacao_real": "\n".join(rotulo(l) for l in linhas[fim + 1:fim + 5]),
                },
            }


def main():
    todos = list(candidatos())
    if RODADA:
        usadas = {m["reuniao"] for m in json.loads(ORIGINAL.read_text(encoding="utf-8"))}
        todos = [m for m in todos if m["reuniao"] not in usadas]
    random.seed(sum(map(ord, RODADA)) if RODADA else 4)
    escolhidos = []
    for desfecho, cota in COTA.items():
        for grupo in ("dinheiro", "outras"):
            pool = [m for m in todos if m["desfecho"] == desfecho and m["grupo_categoria"] == grupo]
            random.shuffle(pool)
            escolhidos += pool[:cota // 2]
        faltam = cota - sum(m["desfecho"] == desfecho for m in escolhidos)
        if faltam > 0:  # um grupo sem itens suficientes: completa com o outro
            usados = {m["id"] for m in escolhidos}
            resto = [m for m in todos if m["desfecho"] == desfecho and m["id"] not in usados]
            random.shuffle(resto)
            escolhidos += resto[:faltam]
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "momentos.json").write_text(json.dumps(escolhidos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"candidatos {len(todos)} | escolhidos {len(escolhidos)}")
    print("por desfecho:", dict(Counter(m["desfecho"] for m in escolhidos)))
    print("por categoria:", dict(Counter(m["categoria"] for m in escolhidos)))
    print("reuniões distintas:", len({m["reuniao"] for m in escolhidos}))


main()
