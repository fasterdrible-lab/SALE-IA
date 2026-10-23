"""C4 — passo 3: IA juíza compara a sugestão da SALEIA com o que o Paulo fez
no mesmo momento real, e calcula a qualidade da recomendação.

Entradas (fora do git): <pasta>/c4/momentos.json (passo 1) e
<pasta>/c4/sugestoes.jsonl (passo 2, gerado na VPS por
scripts/c4_paulo_sugestoes.py). Para cada momento e cada sistema
(coach = sidebar de hoje, motor = Piloto) a juíza (DeepSeek Flash) diz:
endereçou a objeção? técnica sugerida (mesmo vocabulário da Etapa 2), mesma
estratégia do Paulo? melhor / equivalente / pior que a resposta dele? risco?

Métrica principal (definida na C4, 23/10/2026): **"mesma estratégia ou
melhor" nas objeções que o Paulo superou** — a sugestão aponta o mesmo
caminho que funcionou (sim/parcial) ou um caminho melhor. Contraprova: nas
não superadas, quanto a sugestão repete a estratégia que falhou. Técnica
igual à do Paulo é medida também sem IA (comparação do rótulo).

Travas iguais às da Etapa 2 (a conta do DeepSeek é a da produção): para no
pico e com saldo abaixo de SALDO_MINIMO_USD (padrão 5). Rodar de novo
retoma.

Uso: python -I c4_julgar.py [pasta_dados]
Saídas: <pasta>/c4/julgamentos.jsonl e <pasta>/c4/c4_resultado.json
"""
import json, sys, threading, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from os import environ
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from deepseek_util import chat_json, saldo  # noqa: E402

PASTA = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\SALEIA_dados\paulo") / "c4"
MODELO = "deepseek-flash"
SALDO_MINIMO_USD = float(environ.get("SALDO_MINIMO_USD", "5"))
SISTEMAS = ("coach", "motor")
TECNICAS = ("reformular_valor", "comparacao_custo", "prova_social_caso", "pergunta_aprofundamento",
            "condicao_pagamento", "garantia", "urgencia_escassez", "empatia_validacao", "envolver_decisor",
            "isolar_objecao", "outra", "nao_trata_objecao")
_trava = threading.Lock()
_estado = {"parado": None, "saldo": None, "em": 0.0}

SISTEMA = f"""Você avalia sugestões de um assistente de vendas consultivas em português.
Recebe: o fim de uma conversa real de vendas, a objeção do cliente, o que o VENDEDOR DE REFERÊNCIA
(o melhor vendedor da empresa) respondeu de verdade, como o cliente reagiu (desfecho) e a SUGESTÃO que o
assistente deu ao vendedor para aquele momento.

Responda só com JSON:
{{
 "enderecou_a_objecao": "sim|parcial|nao",
 "tecnica_sugerida": "{'|'.join(TECNICAS)}",
 "mesma_estrategia_do_vendedor": "sim|parcial|nao",
 "comparacao": "melhor|equivalente|pior",
 "risco": "nenhum|promessa_ou_dado_inventado|pressao_inadequada|fora_de_contexto",
 "motivo": "1 ou 2 frases"
}}

Regras:
- "enderecou_a_objecao": a sugestão trata a preocupação que o cliente acabou de levantar? Pergunta
  genérica de descoberta que ignora a objeção = "nao".
- "mesma_estrategia_do_vendedor": o CAMINHO é o mesmo (ex.: os dois ajustam a forma de pagamento; os dois
  envolvem o decisor), não as mesmas palavras.
- "comparacao": pensando no que tem mais chance de avançar a venda NAQUELE momento, com o que se sabe
  da conversa. Se o desfecho do vendedor foi "nao_superada", a resposta dele não funcionou: uma sugestão
  com o mesmo caminho não é "melhor". Não premie sugestão longa ou bonita; premie a que resolve.
- "risco": prometer resultado, inventar preço/condição/dado que não aparece na conversa = "promessa_ou_dado_inventado";
  forçar a decisão de forma agressiva = "pressao_inadequada"; sugestão que não combina com o momento = "fora_de_contexto".
"""


def em_pico(agora=None):
    agora = agora or datetime.now(timezone.utc)
    return agora.weekday() < 5 and (1 <= agora.hour < 4 or 6 <= agora.hour < 10)


def pode_enviar():
    with _trava:
        if _estado["parado"]:
            return False
        if em_pico():
            _estado["parado"] = "horário de pico do DeepSeek"
            return False
        if time.time() - _estado["em"] > 30:
            _estado.update(saldo=float(saldo()["balance_infos"][0]["total_balance"]), em=time.time())
        if _estado["saldo"] < SALDO_MINIMO_USD:
            _estado["parado"] = f"saldo US$ {_estado['saldo']:.2f} abaixo de US$ {SALDO_MINIMO_USD:.2f}"
            return False
        return True


def texto_sugestao(sistema, s):
    if not s:
        return None
    if sistema == "coach":
        partes = [("Próxima ação", s.get("next_best_action")), ("O que dizer agora", s.get("texto_falavel")),
                  ("Dica", s.get("dica_vendedor")), ("Alerta", s.get("alerta_urgente"))]
    else:
        partes = [("Framework", s.get("recommended_framework")), ("Próxima ação", s.get("next_best_action")),
                  ("Próxima pergunta", s.get("next_best_question")),
                  ("Evitar", "; ".join(s.get("avoid") or []) if isinstance(s.get("avoid"), list) else s.get("avoid")),
                  ("Por quê", s.get("reason"))]
    partes = [f"{k}: {v}" for k, v in partes if v]
    return "\n".join(partes) or None


def julgar(m, sistema, s):
    g = m["gabarito"]
    usuario = (f"FIM DA CONVERSA (até a objeção):\n{m['transcricao_parcial'][-3000:]}\n\n"
               f"OBJEÇÃO DO CLIENTE: {g['citacao_cliente']}\n"
               f"O QUE O CLIENTE QUIS DIZER (leitura prévia): {g.get('o_que_o_cliente_quis_dizer')}\n\n"
               f"O QUE O VENDEDOR DE REFERÊNCIA RESPONDEU: {g['resposta_vendedor']}\n"
               f"Continuação real:\n{g.get('continuacao_real')}\n"
               f"Reação do cliente: {g.get('reacao_cliente') or '(não registrada)'}\n"
               f"DESFECHO: {m['desfecho']}\n\n"
               f"SUGESTÃO DO ASSISTENTE:\n{texto_sugestao(sistema, s)}")
    # 800 tokens deixava 46% das respostas vazias (23/10): o Flash gasta parte "pensando".
    r, uso = chat_json(SISTEMA, usuario, modelo=MODELO, max_tokens=8000)
    return r, uso


def main():
    momentos = {m["id"]: m for m in json.loads((PASTA / "momentos.json").read_text(encoding="utf-8"))}
    sugestoes = {}
    for l in (PASTA / "sugestoes.jsonl").read_text(encoding="utf-8").splitlines():
        if l.strip():
            s = json.loads(l)
            sugestoes[s["id"]] = s
    saida = PASTA / "julgamentos.jsonl"
    feitos = set()
    if saida.exists():
        feitos = {(j["id"], j["sistema"]) for j in map(json.loads, saida.read_text(encoding="utf-8").splitlines()) if j}
    tarefas = [(mid, sis) for mid in sugestoes for sis in SISTEMAS
               if (mid, sis) not in feitos and texto_sugestao(sis, sugestoes[mid].get(sis))]
    print(f"{len(feitos)} já julgados, {len(tarefas)} pendentes")
    trava_arq = threading.Lock()

    def uma(t):
        mid, sis = t
        if not pode_enviar():
            return
        try:
            r, uso = julgar(momentos[mid], sis, sugestoes[mid][sis])
        except Exception as e:
            print("FALHA", mid, sis, e)
            return
        with trava_arq, saida.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": mid, "sistema": sis, "julgamento": r, "uso": uso}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(uma, tarefas))
    if _estado["parado"]:
        print("PARADO:", _estado["parado"], "— rodar de novo retoma")
    relatorio(momentos, sugestoes, saida)


def pct(n, d):
    return round(100 * n / d, 1) if d else None


def relatorio(momentos, sugestoes, saida):
    julg = [json.loads(l) for l in saida.read_text(encoding="utf-8").splitlines() if l.strip()]
    res = {"momentos": len(momentos), "sugestoes_geradas": {s: sum(bool(x.get(s)) for x in sugestoes.values()) for s in SISTEMAS},
           "erros_na_geracao": sum(bool(x.get("erros")) for x in sugestoes.values()),
           "coach_usou_biblioteca": sum(bool((x.get("coach") or {}).get("usou_biblioteca")) for x in sugestoes.values())}
    for sis in SISTEMAS:
        js = [(momentos[j["id"]], j["julgamento"]) for j in julg if j["sistema"] == sis]
        sup = [(m, j) for m, j in js if m["desfecho"] == "superada"]
        nao = [(m, j) for m, j in js if m["desfecho"] == "nao_superada"]
        bom = lambda j: j.get("mesma_estrategia_do_vendedor") in ("sim", "parcial") or j.get("comparacao") == "melhor"
        res[sis] = {
            "julgados": len(js),
            "QUALIDADE_mesma_estrategia_ou_melhor_nas_superadas_%": pct(sum(bom(j) for _, j in sup), len(sup)),
            "n_superadas": len(sup),
            "mesma_estrategia_ou_melhor_por_grupo_%": {
                g: pct(sum(bom(j) for m, j in sup if m["grupo_categoria"] == g), sum(m["grupo_categoria"] == g for m, _ in sup))
                for g in ("dinheiro", "outras")},
            "repete_estrategia_que_falhou_nas_nao_superadas_%": pct(
                sum(j.get("mesma_estrategia_do_vendedor") == "sim" for _, j in nao), len(nao)),
            "melhor_que_o_vendedor_nas_nao_superadas_%": pct(sum(j.get("comparacao") == "melhor" for _, j in nao), len(nao)),
            "enderecou_a_objecao_%": {k: pct(v, len(js)) for k, v in Counter(j.get("enderecou_a_objecao") for _, j in js).items()},
            "comparacao_%": {k: pct(v, len(js)) for k, v in Counter(j.get("comparacao") for _, j in js).items()},
            "risco_%": {k: pct(v, len(js)) for k, v in Counter(j.get("risco") for _, j in js).items()},
            "tecnica_igual_ao_vendedor_nas_superadas_%": pct(
                sum(j.get("tecnica_sugerida") == m["gabarito"]["tecnica"] for m, j in sup), len(sup)),
            "tecnica_sugerida_%": {k: pct(v, len(js)) for k, v in Counter(j.get("tecnica_sugerida") for _, j in js).most_common()},
        }
    (PASTA / "c4_resultado.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


main()
