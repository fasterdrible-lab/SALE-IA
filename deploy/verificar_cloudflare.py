#!/usr/bin/env python3
"""
SALEIA — Verificador de configuração Cloudflare
Testa se o Cloudflare está corretamente configurado para os 2 VPS.

Uso: python deploy/verificar_cloudflare.py
"""

import sys
import urllib.request
import urllib.error
import json
import time

# ── Configure aqui ────────────────────────────────────────────
VPS1_IP  = "204.168.180.25"
VPS2_IP  = input("IP do 2º VPS: ").strip() if len(sys.argv) < 2 else sys.argv[1]
DOMINIO  = "api.saleia.com.br"
TIMEOUT  = 8
# ─────────────────────────────────────────────────────────────


def checar(url, label):
    try:
        t0 = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "SALEIA-check/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            dados = json.loads(r.read())
            ms = int((time.time() - t0) * 1000)
            status = dados.get("status", "?")
            ia = dados.get("ia", {})
            print(f"  ✅ {label}: {status}  ({ms}ms)  IA={ia}")
            return True
    except Exception as e:
        print(f"  ❌ {label}: {e}")
        return False


print("\n=== SALEIA — Verificação de infraestrutura ===\n")

print(f"1. VPS 1 direto ({VPS1_IP})")
ok1 = checar(f"http://{VPS1_IP}:8000/health", "VPS1")

print(f"\n2. VPS 2 direto ({VPS2_IP})")
ok2 = checar(f"http://{VPS2_IP}:8000/health", "VPS2")

print(f"\n3. Domínio via Cloudflare ({DOMINIO})")
okd = checar(f"https://{DOMINIO}/health", "Cloudflare→API")

print("\n=== Resumo ===")
print(f"  VPS1:       {'✅ online' if ok1 else '❌ offline'}")
print(f"  VPS2:       {'✅ online' if ok2 else '❌ offline'}")
print(f"  Cloudflare: {'✅ roteando' if okd else '❌ falhou (DNS ainda não propagou?)'}")

if ok1 and ok2 and okd:
    print("\n✅ Alta disponibilidade configurada com sucesso!")
elif ok1 or ok2:
    print("\n⚠️  Parcial — pelo menos 1 VPS online. Configure failover no Cloudflare.")
else:
    print("\n🚨 Nenhum backend online. Rode deploy/deploy.ps1 nos 2 VPS.")

print("""
── Checklist Cloudflare (faça no painel cloudflare.com) ──────────────────────

1. DNS → Adicionar:
   Tipo: A  Nome: api  IP: """ + VPS1_IP + """  Proxied: ✅ (nuvem laranja)

2. DNS → Adicionar:
   Tipo: A  Nome: api  IP: """ + VPS2_IP + """  Proxied: ✅ (nuvem laranja)
   (2 registros A = round-robin automático)

3. Traffic → Load Balancing → Criar Pool:
   - Pool 1: """ + VPS1_IP + """:8000  Health check: GET /health  expect: "online"
   - Pool 2: """ + VPS2_IP + """:8000  Health check: GET /health  expect: "online"
   - Failover: se Pool 1 falhar, rotear 100% para Pool 2

4. SSL/TLS → Full (strict)

5. Speed → Optimization → desativar "Rocket Loader" (quebra WebSocket)

6. Security → WAF → Rate Limiting:
   - /tempo-real   → max 60 req/min por IP
   - /recapitulacao* → max 20 req/min por IP

──────────────────────────────────────────────────────────────────────────────
Cloudflare Free suporta tudo isso. Load Balancing requer plano Pro ($20/mês).
Alternativa free: usar 2 registros A (round-robin) + UptimeRobot para alertas.
""")
