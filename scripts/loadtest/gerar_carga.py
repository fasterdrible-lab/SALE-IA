"""
scripts/loadtest/gerar_carga.py — D7 (seção 32 do PROMPT MESTRE V2): simula
N reuniões simultâneas contra a instância de TESTE (porta 8010) e mede
latência, erros, timeouts, CPU, RAM, banco, fila e tokens da IA (falsa).

Cada reunião faz o que a extensão 1.4.37 faz: /iniciar-sessao, um
/tempo-real a cada 20 s com as falas novas (conversa sintética, sem dado de
cliente) e /encerrar-sessao. Os níveis rodam um depois do outro.

**Trava de produção**: a cada 15 s lê `reunioes_ativas` da PRODUÇÃO
(porta 8000); se uma reunião real começar, para tudo na hora.

Uso (na VPS, chamado por scripts/loadtest/rodar.sh):
    venv/bin/python -m scripts.loadtest.gerar_carga --niveis 10,50,100 --minutos 5 --saida /root/loadtest/x.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time

import httpx

ALVO = "http://127.0.0.1:8010"
PRODUCAO = "http://127.0.0.1:8000"
FAKE_AI = "http://127.0.0.1:8099"
INTERVALO_S = 20          # ritmo da extensão (A11)
TIMEOUT_S = 60            # o content.js libera a trava em 120 s; 60 s já é inaceitável
JANELA_PARCIAL = 60       # falas em transcricao_parcial
JANELA_HISTORICO = 150

FALAS_CLIENTE = [
    "hoje a gente fatura uns {n} mil por mês mas a margem está apertada",
    "o maior problema é que o time comercial não tem processo",
    "eu já tentei uma consultoria antes e não deu certo",
    "quanto que fica o investimento disso aí",
    "preciso conversar com o meu sócio antes de decidir",
    "a gente perde uns {n} clientes por mês por falta de acompanhamento",
    "faz sentido mas agora não é o melhor momento",
    "como funciona o pagamento, dá para parcelar em {n} vezes",
    "meu medo é investir e não ter retorno",
    "a concorrência está vendendo mais barato que a gente",
]
FALAS_VENDEDOR = [
    "e o que acontece se isso continuar pelos próximos {n} meses",
    "me conta como é o processo de vendas de vocês hoje",
    "entendi, e quanto isso custa para a empresa por mês",
    "deixa eu te mostrar como a gente resolve exatamente isso",
    "se a gente resolver isso, o que muda para você",
    "o investimento é de {n} mil e dá para fazer no cartão",
    "faz sentido para você esse modelo de trabalho",
    "quem mais participa dessa decisão aí na empresa",
]


def fala(i: int) -> str:
    vendedor = i % 2 == 0
    nome = "Vendedor Teste" if vendedor else "Cliente Teste"
    modelo = random.choice(FALAS_VENDEDOR if vendedor else FALAS_CLIENTE)
    # número + índice: falas distintas (a deduplicação não pode descartá-las)
    return f"{nome}: {modelo.format(n=random.randint(2, 90))} (ponto {i})"


def pct(v: list, q: float):
    return round(sorted(v)[min(len(v) - 1, int(len(v) * q))], 3) if v else None


class Reuniao:
    def __init__(self, n: int, nivel: int):
        self.id = f"lt{nivel:03d}-{n:03d}-{random.randint(100, 999)}"
        self.falas: list[str] = []
        self.enviadas = 0
        self.t0 = time.time()

    def payload(self) -> dict:
        for _ in range(random.randint(3, 6)):  # ~20 s de conversa
            self.falas.append(fala(len(self.falas)))
        novas = self.falas[self.enviadas:]
        agora_ms = int((time.time() - self.t0) * 1000)
        turnos = [{"falante": l.split(":")[0], "inicio_ms": agora_ms - 3000 * (len(novas) - k),
                   "fim_ms": agora_ms - 3000 * (len(novas) - k) + 2500, "texto": l.split(": ", 1)[1]}
                  for k, l in enumerate(novas)]
        self.enviadas = len(self.falas)
        return {
            "transcricao_parcial": "\n".join(self.falas[-JANELA_PARCIAL:]),
            "transcricao_nova": "\n".join(novas),
            "historico": "\n".join(self.falas[-JANELA_HISTORICO:]),
            "perfil_disc_atual": None, "mapa_financeiro": {}, "meeting_id": self.id,
            "participantes": [], "turnos_novos": turnos,
        }


async def rodar_reuniao(cli: httpx.AsyncClient, r: Reuniao, fim: float, parar: asyncio.Event, res: list):
    await cli.post(f"{ALVO}/iniciar-sessao", json={"meeting_id": r.id})
    await asyncio.sleep(random.uniform(0, INTERVALO_S))  # chegadas espalhadas, como reuniões reais
    while time.time() < fim and not parar.is_set():
        inicio = time.time()
        try:
            resp = await cli.post(f"{ALVO}/tempo-real", json=r.payload(), timeout=TIMEOUT_S)
            res.append({"s": time.time() - inicio, "status": resp.status_code})
        except httpx.TimeoutException:
            res.append({"s": time.time() - inicio, "status": "timeout"})
        except httpx.HTTPError as e:
            res.append({"s": time.time() - inicio, "status": f"erro:{type(e).__name__}"})
        await asyncio.sleep(max(0.0, INTERVALO_S - (time.time() - inicio)))
    try:
        await cli.post(f"{ALVO}/encerrar-sessao", json={"meeting_id": r.id}, timeout=10)
    except httpx.HTTPError:
        pass


def _cpu():
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    return v[3] + v[4], sum(v)  # ocioso (idle+iowait), total


def _mem_usada_mb():
    info = {}
    with open("/proc/meminfo") as f:
        for linha in f:
            k, v = linha.split(":")
            info[k] = int(v.split()[0])
    return (info["MemTotal"] - info["MemAvailable"]) // 1024


def _rss_instancia_mb():
    total = 0
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ")
            if b"8010" in cmd and (b"uvicorn" in cmd or b"multiprocessing" in cmd or b"api.main" in cmd):
                with open(f"/proc/{pid}/status") as f:
                    total += next(int(l.split()[1]) for l in f if l.startswith("VmRSS"))
        except (OSError, StopIteration, ValueError):
            pass
    return total // 1024


def _mysql_status(conn):
    with conn.cursor() as cur:
        cur.execute("SHOW GLOBAL STATUS WHERE Variable_name IN ('Threads_connected','Threads_running','Questions','Slow_queries')")
        return {k: int(v) for k, v in cur.fetchall()}


async def amostrar(cli: httpx.AsyncClient, conn, parar: asyncio.Event, amostras: list, motivo: dict):
    ocioso0, total0 = _cpu()
    ultimo_prod = 0.0
    while not parar.is_set():
        await asyncio.sleep(2)
        ocioso1, total1 = _cpu()
        cpu = 100 * (1 - (ocioso1 - ocioso0) / max(1, total1 - total0))
        ocioso0, total0 = ocioso1, total1
        a = {"t": time.time(), "cpu": round(cpu, 1), "mem_mb": _mem_usada_mb(), "rss_mb": _rss_instancia_mb()}
        try:
            a["mysql"] = _mysql_status(conn)
        except Exception as e:  # noqa: BLE001 — amostra é melhor esforço
            a["mysql_erro"] = str(e)[:80]
        try:
            a["ia"] = (await cli.get(f"{FAKE_AI}/stats", timeout=5)).json()
        except httpx.HTTPError:
            pass
        amostras.append(a)
        if time.time() - ultimo_prod >= 15:
            ultimo_prod = time.time()
            try:
                ativas = (await cli.get(f"{PRODUCAO}/health", timeout=10)).json().get("reunioes_ativas")
            except (httpx.HTTPError, ValueError):
                ativas = None
            if ativas:
                motivo["abortado"] = f"reunião real ativa na produção ({ativas}) às {time.strftime('%H:%M:%S')}"
                parar.set()


def resumir(nivel: int, res: list, amostras: list, ia0: dict, ia1: dict, duracao_s: float) -> dict:
    lat = [r["s"] for r in res if r["status"] == 200]
    status = {}
    for r in res:
        status[str(r["status"])] = status.get(str(r["status"]), 0) + 1
    q0 = amostras[0].get("mysql", {}).get("Questions", 0) if amostras else 0
    q1 = amostras[-1].get("mysql", {}).get("Questions", 0) if amostras else 0
    minutos = max(duracao_s / 60, 1e-9)
    return {
        "reunioes": nivel, "duracao_s": round(duracao_s),
        "pedidos": len(res), "por_status": status,
        "taxa_sucesso": round(len(lat) / max(1, len(res)), 4),
        "timeouts": status.get("timeout", 0),
        "latencia_s": {"p50": pct(lat, .5), "p95": pct(lat, .95), "p99": pct(lat, .99), "max": max(lat) if lat else None,
                       "media": round(statistics.mean(lat), 3) if lat else None},
        "cpu_pct": {"media": round(statistics.mean(a["cpu"] for a in amostras), 1) if amostras else None,
                    "max": max((a["cpu"] for a in amostras), default=None)},
        "mem_usada_mb_max": max((a["mem_mb"] for a in amostras), default=None),
        "rss_instancia_mb_max": max((a["rss_mb"] for a in amostras), default=None),
        "mysql": {"threads_conectadas_max": max((a.get("mysql", {}).get("Threads_connected", 0) for a in amostras), default=None),
                  "threads_rodando_max": max((a.get("mysql", {}).get("Threads_running", 0) for a in amostras), default=None),
                  "consultas_por_s": round((q1 - q0) / max(1, duracao_s), 1)},
        "ia": {"chamadas": ia1.get("total", 0) - ia0.get("total", 0),
               "chamadas_por_min": round((ia1.get("total", 0) - ia0.get("total", 0)) / minutos, 1),
               "fila_max": max((a.get("ia", {}).get("max_em_andamento", 0) for a in amostras), default=None),
               "tokens_entrada_por_min": round((ia1.get("tokens_entrada", 0) - ia0.get("tokens_entrada", 0)) / minutos),
               "tokens_saida_por_min": round((ia1.get("tokens_saida", 0) - ia0.get("tokens_saida", 0)) / minutos)},
    }


async def principal(niveis: list[int], minutos: float, saida: str):
    import pymysql
    from dotenv import dotenv_values

    env = dotenv_values(os.path.join(os.getcwd(), ".env"))
    conn = pymysql.connect(host=env.get("DB_HOST") or "127.0.0.1", port=int(env.get("DB_PORT") or 3306),
                           user=env.get("DB_USER"), password=env.get("DB_PASS"), autocommit=True)
    relatorio = {"inicio_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "niveis": [],
                 "intervalo_s": INTERVALO_S, "timeout_s": TIMEOUT_S}
    motivo: dict = {}
    limites = httpx.Limits(max_connections=400, max_keepalive_connections=200)
    async with httpx.AsyncClient(limits=limites, timeout=TIMEOUT_S, headers={"X-Extensao-Versao": "loadtest"}) as cli:
        for nivel in niveis:
            parar = asyncio.Event()
            await cli.post(f"{FAKE_AI}/stats/zerar_pico")
            ia0 = (await cli.get(f"{FAKE_AI}/stats")).json()
            res: list = []
            amostras: list = []
            t0 = time.time()
            fim = t0 + minutos * 60
            print(f"[{time.strftime('%H:%M:%S')}] nível {nivel}: {minutos} min", flush=True)
            amostrador = asyncio.create_task(amostrar(cli, conn, parar, amostras, motivo))
            await asyncio.gather(*(rodar_reuniao(cli, Reuniao(n, nivel), fim, parar, res) for n in range(nivel)))
            parar.set()
            await amostrador
            ia1 = (await cli.get(f"{FAKE_AI}/stats")).json()
            r = resumir(nivel, res, amostras, ia0, ia1, time.time() - t0)
            relatorio["niveis"].append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            with open(saida, "w", encoding="utf-8") as f:
                json.dump({**relatorio, **motivo}, f, ensure_ascii=False, indent=2)
            if motivo:
                print("ABORTADO:", motivo["abortado"], flush=True)
                break
            await asyncio.sleep(30)  # deixa a instância esvaziar entre os níveis
    relatorio.update(motivo)
    relatorio["fim_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--niveis", default="10,50,100")
    p.add_argument("--minutos", type=float, default=5)
    p.add_argument("--saida", required=True)
    a = p.parse_args()
    asyncio.run(principal([int(x) for x in a.niveis.split(",")], a.minutos, a.saida))


if __name__ == "__main__":
    main()
