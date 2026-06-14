# SALEIA — Instruções para Claude Code

## Leia sempre ao iniciar uma conversa

1. **[CHANGELOG.md](CHANGELOG.md)** — Registro completo de tudo implementado
2. **[docs/CURRENT_STATE.md](docs/CURRENT_STATE.md)** — Estado atual, infraestrutura, pendências

## Contexto do projeto

**SALEIA** é um assistente de vendas com IA para Google Meet.
- Backend: FastAPI + Python 3.14, porta 8000
- Frontend: HTML/JS vanilla (login.html, dashboard.html, cenario.html, manual.html, visual-scenario.html)
- Banco: MySQL local na VPS (`127.0.0.1`, ~2ms)
- VPS: `37.27.214.33` (Hetzner CPX32, Helsinki) — serviço `saleia.service` (systemd)
- Domínio: `api.saleia.app.br`
- Repo: `https://github.com/fasterdrible-lab/SALE-IA.git` branch `main`
- Versão atual: **V.1.4.28**
- Usuário admin: `phpos35@gmail.com`

## Deploy

```bash
cd /opt/saleia && git pull origin main && systemctl restart saleia
```

Não sobrescrever em deploy: `.env`, `venv/`, `data/`, `logs/`

## Regras importantes

- Nunca commitar `.env`, `data/saleia.db`, `data/metricas.db` ou PDFs com nomes de clientes
- Nunca expor chaves de API no frontend
- Frontend usa `fetchJsonWithFallback(path, init)` que retorna um `Response` — sempre chamar `.json()` depois
- Extensão Chrome: após qualquer mudança em `chrome-extension/`, precisa ser reinstalada manualmente no browser

## Stack técnica

| Camada | Tecnologia |
|---|---|
| API | FastAPI + Uvicorn (Python 3.14) |
| Auth | JWT (PyJWT) + bcrypt |
| IA | DeepSeek → OpenAI → Anthropic → Gemini (fallback chain) |
| RAG | NumPy cosine similarity + `text-embedding-3-small` |
| Banco | MySQL local (PyMySQL) |
| Frontend | HTML/CSS/JS vanilla, sem framework |
| Deploy | Hetzner VPS + Nginx + Certbot SSL + Cloudflare |
| Observabilidade | SQLite rolling 24h + OpenTelemetry → Grafana Cloud Tempo |

## Arquitetura do Motor de Análise (V.1.4.28)

O endpoint `POST /tempo-real` retorna:
- `next_best_action` — ação consultiva recomendada (tipo: question/insight/warning/next_step)
- `conversation_stage` — estágio SPIN atual (abertura → compromisso)
- `kare_type` — classificação da conta (keep/attain/recapture/expand)
- `maturity_score` — maturidade da oportunidade (0-100, 7 critérios)
- `score_compra` — score de compra independente (0-100)
- `next_best_question` — alias de backward compat para extensões antigas
