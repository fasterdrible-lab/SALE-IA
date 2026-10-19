"""Sinais de venda nas reuniões do Paulo — lista PROVISÓRIA de quem comprou,
lida do resumo do Gemini e da transcrição, cada sinal com a frase que o prova.
Sem IA, tudo local. Substitui o `fechou_pelo_resumo` da Etapa 1 (uma regex só
no resumo); a lista oficial de compradores, quando chegar, mede o acerto.

Níveis por reunião (o mais forte vence):
  PAGOU          pagamento/comprovante confirmado na reunião ou no resumo
  FECHOU_VERBAL  ritual de fechamento do Paulo ("seja bem-vindo… parabéns por
                 essa decisão… 12 meses lado a lado") sem prova de pagamento —
                 o cliente disse sim; às vezes o Paulo "adianta" as boas-vindas
                 antes do pagamento (coluna `antecipado`)
  COMPROMISSO    combinou pagar (entrada, link, comprovante pedido no fim)
  NAO_FECHOU   recusa explícita
  VAI_PENSAR   vai analisar/conversar com alguém
  SEM_SINAL

Uso: python -I sinais_venda.py <pasta_dados>   (lê reunioes.jsonl da Etapa 1)
Saídas na mesma pasta: sinais_venda_reunioes.csv, sinais_venda_clientes.csv,
resumo_sinais_venda.json.
"""
import csv, json, re, sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
PASTA = sys.argv[1]
VENDEDOR = "paulo henrique"
# Primeiros nomes dos clientes que o Paulo conta como caso de sucesso em várias
# reuniões — 1 por linha, em <pasta>/casos_de_sucesso.txt (fora do git: nome de
# cliente não vai para o repositório). Sem o arquivo, a regra só perde esse filtro.
try:
    CASOS = [l.strip().lower() for l in open(f"{PASTA}/casos_de_sucesso.txt", encoding="utf-8-sig") if l.strip()]
except FileNotFoundError:
    CASOS = []
CASOS_RX = "|".join(re.escape(n) for n in CASOS) or r"(?!x)x"
NIVEIS = ["PAGOU", "FECHOU_VERBAL", "COMPROMISSO", "NAO_FECHOU", "VAI_PENSAR", "SEM_SINAL"]
FIM_DA_REUNIAO = 0.6  # ritual de fechamento acontece no fim; antes disso é pitch/história


def rx(*partes):
    return re.compile("|".join(partes), re.I)


# Resumo/detalhes/próximas etapas do Gemini (frase a frase).
RESUMO = {
    "PAGOU": rx(r"(enviou|encaminhou|mandou|compartilhou) o comprovante",
                r"pagamento (da entrada |inicial )?(foi )?(aprovado|realizado|efetuado|confirmado|conclu[ií]do)",
                r"transa[cç][aã]o (foi )?aprovada",
                r"(efetuou|realizou|fez|concluiu|pagou) (a |o )?(entrada|pagamento|pix)\b",
                r"(comprovante|pagamento).{0,80}bem[- ]vind",
                r"ap[oó]s a confirma[cç][aã]o.{0,40}boas[- ]vindas"),
    "FECHOU_VERBAL": rx(r"parabeniz\w* .{0,60}(decis[aã]o|contrata|fechamento|ades[aã]o)",
                        r"(confirmou|formalizou|oficializou) (a |o )?(contrata[cç][aã]o|ades[aã]o|compra|in[ií]cio do projeto)",
                        r"bem[- ]vind\w*.{0,80}(projeto|parceria|oficial)",
                        r"decidiu fechar|(fechou|fecharam) (o |um )?(neg[oó]cio|contrato)|resultando no fechamento",
                        r"assinatura do contrato por|assinou o contrato"),
    "COMPROMISSO": rx(r"(vai|ir[aá]|far[aá]|faria|se comprometeu a|compromisso de|ficou de|combinou de) (fazer|realizar|efetuar|pagar|dar|enviar) (a |o )?(entrada|pagamento|pix|comprovante)",
                      r"\] (enviar|encaminhar|realizar|efetuar|fazer) (o |a )?(comprovante|pagamento|entrada|pix)",
                      r"(enviou|enviar[aá]|vai enviar|enviaria) o link (de|do|para o?) pagamento",
                      r"(aceitou|aceite d[ao]|concordou com) (a |o )?(proposta|condi[cç][aã]o|valor)",
                      r"(se comprometeu a|compromisso de) fechar"),
    "NAO_FECHOU": rx(r"(decidiu|optou por) n[aã]o (fechar|contratar|seguir|prosseguir|avan[cç]ar|investir)",
                     r"n[aã]o (vai|ir[aá]|pretende) (fechar|contratar|seguir|prosseguir|avan[cç]ar)",
                     r"(recusou|declinou) (a )?(proposta|oferta)(?! do sinal)",
                     r"desistiu d[ao] (proposta|projeto|contrata|neg[oó]cio)",
                     r"n[aã]o (tem|possui|teria) (condi[cç][oõ]es|dinheiro|recursos|verba) (financeiras? )?(para|de) (investir|contratar|fechar|pagar)"),
    "VAI_PENSAR": rx(r"(vai|ir[aá]|precisa|precisar[aá]) (pensar|analisar|avaliar|refletir)",
                     r"recusou a proposta do sinal",
                     r"(nova reuni[aã]o|retomar a conversa).{0,120}fech(ar|amento)",
                     r"(analisar|avaliar) a proposta",
                     r"(conversar|alinhar|consultar) com (a esposa|o marido|o s[oó]cio|a s[oó]cia|os s[oó]cios|a fam[ií]lia|o pai|a m[aã]e)"),
}
# Frase que fala de outra compra (mentoria/curso anterior) ou de outro cliente.
RESUMO_FORA = rx(r"anterior|outra mentoria|outro curso|outra empresa|outra consultoria|j[aá] pagou",
                 r"exemplo|caso d[eo]|outro cliente|outros clientes|detalhou o processo|explicou (o|que)|apresentou casos",
                 rf"\b({CASOS_RX})\b")  # caso de sucesso que o Paulo conta em várias reuniões

# Falas da transcrição (só no fim da reunião).
FALA_PAULO = {
    "PAGOU": rx(r"(chegou|caiu)( sim| aqui| certinho| j[aá])?.{0,40}comprovante|comprovante.{0,40}(chegou|caiu)"),
    "FECHOU_VERBAL": rx(r"agora (sim,? )?(é|e|t[aá]|est[aá]) oficial|de forma oficial",
                        r"parab[eé]ns (pela|por essa|por esta|pela sua|por sua) decis[aã]o",
                        r"(seja|sejam) (muito )?bem[- ]vind\w*.{0,60}aben[cç]oe (esse|este) projeto",
                        r"adiant\w* (um |o )?(seja )?(muito )?bem[- ]vind"),
    "COMPROMISSO": rx(r"(manda|mande|envia|envie|me envi\w*)( a[ií])?( pra mim| para mim)?( por gentileza)? o comprovante",
                      r"(vou (te )?(mandar|enviar)|te mand\w+|te envi\w+) (a chave|o link (de|do) pagamento)"),
}
FALA_CLIENTE = {
    "PAGOU": rx(r"\b(j[aá] )?(fiz o pix|fiz o pagamento|paguei a entrada|mandei o comprovante|enviei o comprovante|acabei de pagar|t[aá] pago|pagamento (foi )?aprovado)\b"),
    # "não vou fechar agora / nada agora" é adiamento, não recusa.
    "VAI_PENSAR": rx(r"n[aã]o (vou|vamos|consigo) (fechar|contratar)( nada)? (agora|hoje|nesse momento|neste momento)",
                     r"(vou|vamos|preciso) (pensar|analisar|avaliar)"),
    "NAO_FECHOU": rx(r"n[aã]o (vou|vamos|d[aá] pra|d[aá] para|consigo|tenho como) (fechar|contratar|investir|seguir)(?!( nada)? (agora|hoje|nesse momento|neste momento|ex))",
                     r"n[aã]o vamos seguir"),
}
# Paulo contando a história de outro cliente ("ele falou: pode mandar o Pix").
HISTORIA = rx(r"\b(eu falei|ele falou|ela falou|falei pra ele|falei para ele|ele disse|ela disse)\b", rf"\bo ({CASOS_RX})\b")
# Pré-fechamento condicional ("se você entender que somos a empresa ideal, seja
# bem-vindo… posso contar com o sincero sim ou não?") — ainda não é o sim.
CONDICIONAL = rx(r"se voc[eê] entender|se fizer sentido|sincero,? sim ou n[aã]o|posso contar com o sincero")
# "Oficial"/boas-vindas logo depois de o pagamento chegar = PAGOU ("Opa, chegou
# sim… agora sim é oficial"). Janela: a própria fala e as 4 anteriores.
# Só palavras de dinheiro CHEGANDO — "pix"/"pagamento" sozinhos aparecem na
# proposta ("essa entrada fica melhor em 12 vezes… seja bem-vindo").
PAGAMENTO_PERTO = rx(r"\b(chegou|caiu|comprovante|aprovad[oa]|paguei|deu certo|recebi|acabei de receber|confirmei)\b")
ANTECIPADO = rx(r"adiant\w* (um |o )?(seja )?(muito )?bem[- ]vind")


def frases(texto):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", texto or "") if s.strip()]


def sinais_da_reuniao(r):
    achados = []  # (nivel, fonte, evidencia)
    for s in frases("\n".join([r["resumo"], r["detalhes"], r["proximas_etapas"]])):
        for nivel, pat in RESUMO.items():
            if pat.search(s) and not (nivel in ("PAGOU", "FECHOU_VERBAL", "COMPROMISSO") and RESUMO_FORA.search(s)):
                achados.append((nivel, "resumo", s))
    falas = r["falas"]
    for i, f in enumerate(falas):
        if i < FIM_DA_REUNIAO * len(falas):
            continue
        paulo = VENDEDOR in f["falante"].lower()
        if paulo and (HISTORIA.search(f["texto"]) or CONDICIONAL.search(f["texto"])):
            continue
        for nivel, pat in (FALA_PAULO if paulo else FALA_CLIENTE).items():
            if pat.search(f["texto"]):
                if nivel == "PAGOU" and paulo and FALA_PAULO["COMPROMISSO"].search(f["texto"]):
                    nivel = "COMPROMISSO"  # "confere se chegou… envie o comprovante" = pedido, não confirmação
                if nivel == "FECHOU_VERBAL" and not ANTECIPADO.search(f["texto"]) and any(
                        PAGAMENTO_PERTO.search(g["texto"]) for g in falas[max(0, i - 4):i + 1]):
                    nivel = "PAGOU"
                achados.append((nivel, "fala_" + ("paulo" if paulo else "cliente"), f["texto"]))
    return achados


def main():
    reunioes = [json.loads(l) for l in open(f"{PASTA}/reunioes.jsonl", encoding="utf-8")]
    linhas, por_cliente = [], defaultdict(list)
    for r in reunioes:
        achados = sinais_da_reuniao(r)
        cont = Counter(n for n, _, _ in achados)
        nivel = next((n for n in NIVEIS if cont[n]), "SEM_SINAL")
        # Prova principal: do nível escolhido, preferindo o resumo (mais curto e já interpretado).
        prova = sorted((a for a in achados if a[0] == nivel), key=lambda a: a[1] != "resumo")
        linha = {
            "cliente": r.get("cliente"), "data": r["data"], "tipo": r["tipo"], "arquivo": r["arquivo"],
            "nivel": nivel, "fontes": "+".join(sorted({a[1] for a in achados if a[0] == nivel})),
            "conflito": bool(nivel in ("PAGOU", "FECHOU_VERBAL", "COMPROMISSO") and cont["NAO_FECHOU"]),
            "antecipado": any(ANTECIPADO.search(a[2]) for a in achados),
            "fechou_pelo_resumo_etapa1": r["fechou_pelo_resumo"],
            "evidencia": prova[0][2][:400] if prova else "",
            "outros_sinais": "; ".join(f"{n}×{c}" for n, c in cont.items() if n != nivel),
        }
        linhas.append(linha)
        por_cliente[linha["cliente"]].append(linha)

    jornada = {row["cliente"]: row for row in csv.DictReader(open(f"{PASTA}/clientes_jornada.csv", encoding="utf-8-sig"), delimiter=";")}
    clientes = []
    for cod, ls in por_cliente.items():
        ls.sort(key=lambda l: l["data"] or "")
        melhor = min(ls, key=lambda l: (NIVEIS.index(l["nivel"]), l["data"] or ""))
        j = jornada.get(cod, {})
        clientes.append({
            "cliente": cod, "nomes_reais": j.get("nomes_reais", ""), "reunioes": len(ls),
            "primeira": ls[0]["data"], "ultima": ls[-1]["data"],
            "nivel": melhor["nivel"], "data_do_sinal": melhor["data"], "evidencia": melhor["evidencia"],
            "fechou_provisorio_etapa1": j.get("fechou_provisorio", ""),
            "lista_oficial_comprou": "",  # preencher quando a lista oficial chegar
        })
    clientes.sort(key=lambda c: (NIVEIS.index(c["nivel"]), c["primeira"] or ""))

    with open(f"{PASTA}/sinais_venda_reunioes.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(linhas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    with open(f"{PASTA}/sinais_venda_clientes.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(clientes[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(clientes)

    etapa1 = Counter((c["nivel"], c["fechou_provisorio_etapa1"] == "True") for c in clientes)
    resumo = {
        "reunioes": len(linhas), "clientes": len(clientes),
        "reunioes_por_nivel": dict(Counter(l["nivel"] for l in linhas)),
        "clientes_por_nivel": dict(Counter(c["nivel"] for c in clientes)),
        "reunioes_PAGOU_por_fonte": dict(Counter(l["fontes"] for l in linhas if l["nivel"] == "PAGOU")),
        "reunioes_FECHOU_VERBAL_antecipado": sum(l["antecipado"] for l in linhas if l["nivel"] == "FECHOU_VERBAL"),
        "reunioes_com_conflito": sum(l["conflito"] for l in linhas),
        "clientes_nivel_x_etapa1": {f"{n} / etapa1={'sim' if e else 'nao'}": c for (n, e), c in sorted(etapa1.items())},
    }
    json.dump(resumo, open(f"{PASTA}/resumo_sinais_venda.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


main()
