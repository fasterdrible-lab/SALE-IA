"""Etapa 2 — extração com IA (DeepSeek) das reuniões do piloto.

Toda informação extraída precisa de citação literal do texto; o validador
descarta o item cuja citação não for encontrada (mesma disciplina do
SALEIA: nunca fabricar evidência). Saídas em piloto/extracoes/<id>.json e
piloto/revisao.csv (uma linha por item, para revisão humana).

Uso: python -I etapa2_extrair.py <qtd, "todas" ou ids separados por vírgula> [modelo] [lote]
lote: pasta em C:\\SALEIA_dados\\paulo (padrão "piloto"; "completo" = todas
as reuniões, ver etapa2_preparar.py todas).

Travas (21/10/2026 — a conta do DeepSeek é a mesma da produção): para de
enviar se o saldo cair abaixo de SALDO_MINIMO_USD ou no horário de pico do
DeepSeek (preço dobrado). Rodar de novo retoma: reunião já extraída é pulada.
"""
import csv, json, re, sys, threading, time, unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from deepseek_util import chat_json, saldo  # noqa: E402

LOTE = sys.argv[3] if len(sys.argv) > 3 else "piloto"
P = Path(r"C:\SALEIA_dados\paulo") / LOTE
MODELO = sys.argv[2] if len(sys.argv) > 2 else "deepseek-v4-pro"
EXTR = P / f"extracoes_{MODELO}"
EXTR.mkdir(exist_ok=True)

SALDO_MINIMO_USD = 8.0
_trava = threading.Lock()
_saldo_cache = {"valor": None, "em": 0.0}
_parado = {"motivo": None}


def em_pico(agora=None):
    """Pico do DeepSeek: 01-04 e 06-10 UTC em dias úteis (preço dobrado)."""
    agora = agora or datetime.now(timezone.utc)
    return agora.weekday() < 5 and (1 <= agora.hour < 4 or 6 <= agora.hour < 10)


def pode_enviar():
    with _trava:
        if _parado["motivo"]:
            return False
        if em_pico():
            _parado["motivo"] = "horário de pico do DeepSeek"
            return False
        if time.time() - _saldo_cache["em"] > 30:
            info = saldo()["balance_infos"][0]
            _saldo_cache.update(valor=float(info["total_balance"]), em=time.time())
        if _saldo_cache["valor"] < SALDO_MINIMO_USD:
            _parado["motivo"] = f"saldo US$ {_saldo_cache['valor']:.2f} abaixo de US$ {SALDO_MINIMO_USD:.2f}"
            return False
        return True

SISTEMA = """Você analisa a transcrição de uma reunião de vendas consultivas em português.
VENDEDOR é o vendedor de referência da empresa. PESSOA_xxxx são clientes (nomes trocados por código).
A transcrição foi gerada por computador e tem erros de reconhecimento de fala.

REGRAS ABSOLUTAS
1. Use SOMENTE o que está na transcrição. Nunca invente, nunca complete com conhecimento geral.
2. Todo campo "citacao" deve ser uma cópia EXATA e contígua de um trecho da transcrição (de 4 a 40 palavras), sem o rótulo do falante, sem reticências, sem corrigir erros. Se não houver trecho que sustente o item, NÃO inclua o item.
3. Use apenas os valores permitidos nos campos de categoria. Se nenhum servir, use "outro"/"outra".
4. Prefira poucos itens bem sustentados a muitos fracos.
5. Os campos "contexto", "o_que_o_cliente_quis_dizer", "intencao_do_vendedor", "por_que_perguntou" e "explicacao" são a SUA leitura da conversa — escreva em 1 a 3 frases claras, baseadas no que vem antes e depois do trecho, sem inventar fatos que não estão na transcrição. Se não der para saber, escreva "não dá para saber pela transcrição".
6. DESFECHO DE OBJEÇÃO — seja conservador:
   - "superada": SÓ se o cliente diz explicitamente que a dúvida foi resolvida ou aceita a condição proposta ("pode ser assim", "fechado", "agora ficou claro, vamos"). Coloque essa fala em "evidencia_desfecho".
   - "nao_superada": o cliente mantém a objeção ("não concordo", "continua caro", "não consigo"). Coloque essa fala em "evidencia_desfecho".
   - "parcial": o cliente reage de forma genérica ("acredito que sim", "entendi", "achei bacana") ou a negociação continua aberta.
   - "indefinido": não há reação clara do cliente.
   Interesse, concordância genérica ou avanço da conversa NÃO são "superada".
7. RESULTADO DA REUNIÃO — escolha UM, o mais conservador que o texto sustenta:
   - "pagamento_confirmado": o pagamento foi feito/confirmado nesta reunião.
   - "contrato_pendente": combinaram contratar, falta enviar/assinar/analisar contrato ou concluir pagamento já iniciado.
   - "reuniao_confirmada": nova reunião com dia/horário PROPOSTO E ACEITO pelo cliente — coloque a fala de aceite do cliente em "evidencia_aceite_cliente".
   - "reuniao_proposta": alguém propôs data/horário, mas o aceite explícito do cliente não aparece.
   - "promete_retorno": o cliente promete dar resposta/retorno (com ou sem prazo), sem decisão.
   - "vai_pensar": o cliente diz que vai pensar/conversar com alguém, sem prometer retorno concreto.
   - "nao_fechou": o cliente recusa. "indefinido": não dá para saber.
   Em "motivo", diga em 1 frase por que escolheu esse e não o próximo mais forte.
8. CITAÇÕES: a citação de objeção deve ter pelo menos 6 palavras ditas pelo cliente. "resposta_do_cliente" de uma pergunta deve ser a fala do cliente logo em seguida à pergunta e que de fato responde a ela; se o cliente não respondeu, deixe vazio. Trechos com reconhecimento de fala incompreensível não devem ser usados.
9. Responda só com um JSON válido no formato abaixo.

FORMATO
{
 "tipo_reuniao": "diagnostico|apresentacao_proposta|negociacao|fechamento|acompanhamento|outro",
 "resultado": {"status": "pagamento_confirmado|contrato_pendente|reuniao_confirmada|reuniao_proposta|promete_retorno|vai_pensar|nao_fechou|indefinido", "citacao": "...", "evidencia_aceite_cliente": "...(fala exata do cliente aceitando dia/horário, ou vazio)", "explicacao": "como a reunião terminou", "motivo": "por que este status"},
 "cliente": {
   "situacao_atual": [{"fato": "frase curta", "citacao": "...", "explicacao": "o que isso diz sobre o cliente"}],
   "dores": [{"dor": "frase curta", "citacao": "...", "explicacao": "por que isso é um problema para ele"}],
   "objetivos": [{"objetivo": "frase curta", "citacao": "...", "explicacao": "o que ele quer alcançar e por quê"}]
 },
 "objecoes": [{
   "categoria": "preco|capacidade_financeira|prazo_momento|confianca_credibilidade|decisor_terceiros|necessidade_prioridade|risco_resultado|concorrencia|outro",
   "contexto": "o que estava sendo discutido logo antes da objeção",
   "citacao_cliente": "...",
   "o_que_o_cliente_quis_dizer": "a preocupação real por trás da frase",
   "resposta_vendedor": "...(citação exata da resposta do VENDEDOR)",
   "intencao_do_vendedor": "o que o vendedor buscou com essa resposta e como conduziu",
   "tecnica": "reformular_valor|comparacao_custo|prova_social_caso|pergunta_aprofundamento|condicao_pagamento|garantia|urgencia_escassez|empatia_validacao|envolver_decisor|isolar_objecao|outra",
   "reacao_cliente": "...(citação exata do que o cliente disse depois, ou vazio)",
   "desfecho": "superada|parcial|nao_superada|indefinido",
   "evidencia_desfecho": "...(citação exata do cliente que prova superada/nao_superada, ou vazio)",
   "motivo": "por que este desfecho, em 1 frase"
 }],
 "perguntas_descoberta": [{"citacao": "...(pergunta do VENDEDOR)", "spin": "situacao|problema|implicacao|necessidade_solucao",
   "dimensao": "fato_atual|meta_futura|historico_tempo|sentimento_opiniao|decisao|outro",
   "por_que_perguntou": "o que o vendedor queria descobrir", "resposta_do_cliente": "...(citação exata, ou vazio)",
   "resposta_atende": "sim|parcial|nao|sem_resposta",
   "motivo": "a resposta trata da mesma dimensão da pergunta? (ex.: perguntou rendimento atual e o cliente falou de meta futura = nao)"}],
 "preco": {"apresentado": true, "citacao": "...", "explicacao": "como e em que momento o preço foi apresentado", "condicoes": [{"descricao": "frase curta", "citacao": "..."}]},
 "fechamento": [{"tecnica": "pedido_direto|alternativa|resumo_beneficios|urgencia|proximo_passo_concreto|outra", "citacao": "...", "explicacao": "como o vendedor conduziu para a decisão"}],
 "proximo_passo": {"definido": true, "citacao": "..."}
}
Limites: até 6 itens por lista de cliente, até 8 objeções, até 12 perguntas de descoberta (só perguntas reais de investigação, não confirmações como "né?", "faz sentido?"), até 5 técnicas de fechamento."""


def norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def validar(extr, texto):
    """Remove itens com citação que não está no texto. Retorna (extração limpa, contagens)."""
    base = norm(re.sub(r"^(VENDEDOR|PESSOA_\w+): ", "", texto, flags=re.M))
    cont = {"ok": 0, "descartado": 0}

    def ok(c):
        if not c or not str(c).strip():
            return None
        achou = norm(c) in base and len(norm(c).split()) >= 3
        cont["ok" if achou else "descartado"] += 1
        return achou

    def filtra(lista, campos):
        out = []
        for it in lista or []:
            if not isinstance(it, dict):
                continue
            resultados = [ok(it.get(c)) for c in campos]
            if resultados[0]:  # a citação principal precisa existir
                for c, r in zip(campos[1:], resultados[1:]):
                    if r is False:
                        it[c] = ""  # citação secundária inventada vira vazio
                out.append(it)
        return out

    # Posição de cada citação (índice da fala) — para checar "logo depois".
    linhas_n = [norm(re.sub(r"^(VENDEDOR|PESSOA_\w+): ", "", l)) for l in texto.splitlines()]

    def pos(c):
        a = norm(c)
        return next((k for k, l in enumerate(linhas_n) if a and a in l), None)

    regras = cont.setdefault("rebaixados", Counter())
    e = dict(extr)
    cli = e.get("cliente") or {}
    e["cliente"] = {k: filtra(cli.get(k), ["citacao"]) for k in ("situacao_atual", "dores", "objetivos")}
    objs = []
    for o in filtra(e.get("objecoes"), ["citacao_cliente", "resposta_vendedor", "reacao_cliente", "evidencia_desfecho"]):
        if len(norm(o.get("citacao_cliente")).split()) < 6:  # auditoria: "E não tem nita."
            regras["objecao_citacao_curta"] += 1
            continue
        if o.get("desfecho") in ("superada", "nao_superada") and not o.get("evidencia_desfecho"):
            regras[f"{o['desfecho']}_sem_prova→indefinido"] += 1
            o["desfecho"] = "indefinido"
        elif o.get("desfecho") in ("superada", "nao_superada"):
            # A prova precisa ser fala do CLIENTE e vir DEPOIS da objeção.
            po, pe = pos(o["citacao_cliente"]), pos(o["evidencia_desfecho"])
            do_cliente = pe is not None and not texto.splitlines()[pe].startswith("VENDEDOR:")
            if po is None or pe is None or pe < po or not do_cliente:
                regras[f"{o['desfecho']}_prova_fora_de_ordem_ou_do_vendedor→indefinido"] += 1
                o["desfecho"] = "indefinido"
        objs.append(o)
    e["objecoes"] = objs
    pergs = filtra(e.get("perguntas_descoberta"), ["citacao", "resposta_do_cliente"])
    for q in pergs:
        if q.get("resposta_do_cliente"):
            pq, pr = pos(q["citacao"]), pos(q["resposta_do_cliente"])
            if pq is None or pr is None or not (0 < pr - pq <= 4):  # auditoria: respostas não responsivas
                regras["resposta_fora_de_sequencia"] += 1
                q["resposta_do_cliente"] = ""
    e["perguntas_descoberta"] = pergs
    e["fechamento"] = filtra(e.get("fechamento"), ["citacao"])
    for chave in ("resultado", "proximo_passo"):
        it = e.get(chave) or {}
        if it.get("citacao") and not ok(it["citacao"]):
            it["citacao"] = ""
            it["sem_evidencia"] = True
        e[chave] = it
    res = e["resultado"]
    aceite = res.get("evidencia_aceite_cliente")
    if aceite and not ok(aceite):
        res["evidencia_aceite_cliente"] = aceite = ""
    if aceite:
        pa = pos(aceite)
        if pa is None or texto.splitlines()[pa].startswith("VENDEDOR:"):  # aceite tem de ser do cliente
            regras["aceite_do_vendedor_descartado"] += 1
            res["evidencia_aceite_cliente"] = aceite = ""
    if res.get("status") == "reuniao_confirmada" and not aceite:  # T4 da auditoria
        regras["reuniao_confirmada_sem_aceite→reuniao_proposta"] += 1
        res["status"] = "reuniao_proposta"
    if res.get("status") in ("pagamento_confirmado", "contrato_pendente", "reuniao_confirmada", "reuniao_proposta",
                             "nao_fechou") and not res.get("citacao"):
        regras[f"resultado_{res['status']}_sem_prova→indefinido"] += 1
        res["status"] = "indefinido"
    for q in e["perguntas_descoberta"]:  # T3: sem resposta registrada não pode "atender"
        if not q.get("resposta_do_cliente") and q.get("resposta_atende") in ("sim", "parcial"):
            q["resposta_atende"] = "sem_resposta"
    preco = e.get("preco") or {}
    if preco.get("citacao") and not ok(preco["citacao"]):
        preco["citacao"] = ""
    preco["condicoes"] = filtra(preco.get("condicoes"), ["citacao"])
    e["preco"] = preco
    return e, cont


def processar(rid):
    destino = EXTR / f"{rid}.json"
    if destino.exists():
        return rid, json.loads(destino.read_text(encoding="utf-8"))
    if not pode_enviar():
        return rid, None
    texto = (P / "textos" / f"{rid}.txt").read_text(encoding="utf-8")
    t0 = time.time()
    bruto, uso = chat_json(SISTEMA, "TRANSCRIÇÃO:\n" + texto, modelo=MODELO, max_tokens=32000)
    limpo, cont = validar(bruto, texto)
    out = {"id": rid, "modelo": MODELO, "segundos": round(time.time() - t0), "uso": uso, "citacoes": cont,
           "extracao": limpo, "bruto": bruto}
    destino.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return rid, out


ANTES, DEPOIS = 3, 3


def trecho_em_volta(linhas_texto, linhas_norm, citacao):
    """As falas reais em volta da citação (3 antes, 3 depois), com quem disse.
    Sai da transcrição, não da IA — não tem como ser inventado."""
    alvo = norm(citacao)
    if not alvo:
        return ""
    i = next((k for k, l in enumerate(linhas_norm) if alvo in l), None)
    if i is None:  # citação que atravessa 2 falas: procura pelo começo
        inicio = " ".join(alvo.split()[:6])
        i = next((k for k, l in enumerate(linhas_norm) if inicio in l), None)
    if i is None:
        return ""
    trecho = []
    for k in range(max(0, i - ANTES), min(len(linhas_texto), i + DEPOIS + 1)):
        fala = linhas_texto[k]
        if k == i and len(fala) > 500:
            # Fala longa: janela centrada na citação (auditoria, linha 6 — o
            # pedaço mostrado era outro trecho da mesma fala).
            rotulo, _, corpo = fala.partition(": ")
            pal = alvo.split()[:4]
            m = re.search(r"\W+".join(re.escape(p) for p in pal), norm(corpo)) if pal else None
            c = int(m.start() * len(corpo) / max(1, len(norm(corpo)))) if m else 0
            ini, fim = max(0, c - 200), min(len(corpo), c + len(citacao) + 200)
            fala = f"{rotulo}: " + ("[…] " if ini else "") + corpo[ini:fim] + (" […]" if fim < len(corpo) else "")
        elif len(fala) > 400:
            fala = fala[:400] + " […]"
        trecho.append(("▶ " if k == i else "   ") + fala)
    return "\n".join(trecho)


def planilha_revisao(resultados):
    linhas = []
    for rid, r in sorted(resultados.items()):
        e = r["extracao"]
        texto = (P / "textos" / f"{rid}.txt").read_text(encoding="utf-8").splitlines()
        tn = [norm(re.sub(r"^(VENDEDOR|PESSOA_\w+): ", "", l)) for l in texto]

        cont = Counter()

        def linha(tipo, classif, citacao, interpretacao, resposta="", intencao="", reacao="", motivo="", evidencia=""):
            base = tipo.split(":")[0]
            cont[base] += 1
            item_id = f"{rid}-{base}-{cont[base]:02d}"  # T1: rastreável
            linhas.append([item_id, rid, tipo, classif, citacao, interpretacao, resposta, intencao, reacao, evidencia,
                           motivo, trecho_em_volta(texto, tn, citacao), ""])

        res = e["resultado"]
        linha("resultado", res.get("status"), res.get("citacao", ""), res.get("explicacao", ""),
              motivo=res.get("motivo", ""), evidencia=res.get("evidencia_aceite_cliente", ""))
        for k, campo in (("situacao_atual", "fato"), ("dores", "dor"), ("objetivos", "objetivo")):
            for it in e["cliente"][k]:
                linha(k, it.get(campo), it["citacao"], it.get("explicacao", ""))
        for o in e["objecoes"]:
            linha("objecao:" + o.get("categoria", ""), f"{o.get('tecnica')} → {o.get('desfecho')}", o["citacao_cliente"],
                  f"Contexto: {o.get('contexto', '')}\nO cliente quis dizer: {o.get('o_que_o_cliente_quis_dizer', '')}",
                  o.get("resposta_vendedor", ""), o.get("intencao_do_vendedor", ""), o.get("reacao_cliente", ""),
                  motivo=o.get("motivo", ""), evidencia=o.get("evidencia_desfecho", ""))
        for q in e["perguntas_descoberta"]:
            linha("pergunta:" + q.get("spin", ""), f"{q.get('dimensao')} / resposta atende: {q.get('resposta_atende')}",
                  q["citacao"], q.get("por_que_perguntou", ""), reacao=q.get("resposta_do_cliente", ""),
                  motivo=q.get("motivo", ""))
        for f in e["fechamento"]:
            linha("fechamento", f.get("tecnica"), f["citacao"], f.get("explicacao", ""))
    with open(P / f"revisao_{MODELO}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["item_id", "reuniao", "tipo_item", "classificacao_da_ia", "citacao", "interpretacao_da_ia (o que quis dizer)",
                    "resposta_vendedor", "intencao_do_vendedor (interpretacao)", "reacao_ou_resposta_do_cliente",
                    "evidencia (aceite/desfecho)", "motivo_da_ia",
                    "TRECHO DA CONVERSA (3 falas antes e depois; ▶ = a citada)", "CORRETO? (S/N/parcial)"])
        w.writerows(linhas)
    return len(linhas)


def main():
    arg = sys.argv[1]
    todos = sorted(p.stem for p in (P / "textos").glob("*.txt"))
    ids = (todos if arg == "todas" else arg.split(",") if "," in arg or arg[0] in "RC" else todos[:int(arg)])
    resultados = {}
    falhas = []

    def seguro(rid):
        try:
            return processar(rid)
        except Exception as e:  # uma reunião ruim não derruba o lote; rodar de novo tenta outra vez
            falhas.append(f"{rid}: {e}")
            return rid, None

    with ThreadPoolExecutor(max_workers=5) as ex:
        for rid, out in ex.map(seguro, ids):
            if out is None:
                continue
            resultados[rid] = out
            u = out["uso"]
            print(f"{rid}: {out['segundos']}s, entrada {u.get('prompt_tokens')} saída {u.get('completion_tokens')} "
                  f"(cache {u.get('prompt_cache_hit_tokens')}), citações ok {out['citacoes']['ok']} descartadas {out['citacoes']['descartado']} rebaixados {dict(out['citacoes'].get('rebaixados', {}))}",
                  flush=True)
    tin = sum(r["uso"].get("prompt_tokens", 0) for r in resultados.values())
    tout = sum(r["uso"].get("completion_tokens", 0) for r in resultados.values())
    ok = sum(r["citacoes"]["ok"] for r in resultados.values())
    desc = sum(r["citacoes"]["descartado"] for r in resultados.values())
    preco = (0.66, 1.98) if "pro" in MODELO else (0.15, 0.6)
    print(f"\nTOTAL {len(resultados)} reuniões | tokens entrada {tin} saída {tout} | "
          f"custo fora de pico ~US$ {tin / 1e6 * preco[0] + tout / 1e6 * preco[1]:.2f} | "
          f"citações verificadas {ok}, descartadas {desc} ({100 * desc / max(1, ok + desc):.1f}%)")
    faltam = len(ids) - len(resultados)
    if _parado["motivo"] or faltam:
        print(f"PARADO: {_parado['motivo'] or 'falhas'} — {faltam} de {len(ids)} reuniões sem extração; rodar de novo retoma")
    for f in falhas:
        print("FALHA", f)
    if resultados:
        print("linhas na planilha de revisão:", planilha_revisao(resultados))


main()
