"""Chamada ao DeepSeek (API compatível com OpenAI) lendo a chave do .env do SALEIA."""
import json, time, urllib.request, urllib.error

ENV = r"C:\Users\phpos\OneDrive\SALE-IA\SALEIA\.env"
BASE = "https://api.deepseek.com"


def chave():
    for linha in open(ENV, encoding="utf-8"):
        if linha.startswith("DEEPSEEK_API_KEY="):
            return linha.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("DEEPSEEK_API_KEY não encontrada no .env")


def _req(caminho, corpo=None, timeout=600):
    r = urllib.request.Request(BASE + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                               headers={"Authorization": "Bearer " + chave(), "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.load(resp)


def saldo():
    return _req("/user/balance")


def chat_json(sistema, usuario, modelo="deepseek-v4-pro", max_tokens=8000, tentativas=3):
    corpo = {"model": modelo, "temperature": 0.1, "max_tokens": max_tokens,
             "response_format": {"type": "json_object"},
             "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
    erro = None
    for i in range(tentativas):
        try:
            resp = _req("/chat/completions", corpo)
            texto = resp["choices"][0]["message"]["content"]
            return json.loads(texto), resp.get("usage", {})
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as e:
            erro = e
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"falhou após {tentativas} tentativas: {erro}")
