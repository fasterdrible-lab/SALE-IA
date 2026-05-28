# SALEIA — Instruções para Claude Code

## Leia sempre ao iniciar uma conversa

1. **[CHANGELOG.md](CHANGELOG.md)** — Registro completo de tudo implementado (V.1.3.4 + V.1.3.5)
2. **[DOCUMENTACAO_PROJETO.md](DOCUMENTACAO_PROJETO.md)** — Arquitetura, endpoints, infraestrutura

## Contexto do projeto

**SALEIA** é um assistente de vendas com IA para Google Meet.
- Backend: FastAPI + Python, porta 8000
- Frontend: HTML/JS vanilla (dashboard.html, cenario.html, login.html, manual.html)
- Banco: MySQL remoto (`fast5342_AV3D`)
- VPS: `204.168.180.25` — serviço `saleia.service` (systemd)
- Domínio: `api.saleia.com.br`
- Repo: `https://github.com/fasterdrible-lab/SALE-IA.git` branch `main`

## Deploy

Os arquivos **não são deployados via git pull** (repo VPS está desatualizado).
**Deploy = SFTP** dos arquivos alterados para `/opt/saleia/` + `systemctl restart saleia`.

## Regras importantes

- Nunca commitar `.env`, `data/saleia.db` ou PDFs com nomes de clientes
- Nunca expor chaves de API no frontend
- Frontend usa `fetchJsonWithFallback(path, init)` que retorna um `Response` — sempre chamar `.json()` depois
- Versão atual: **V.1.3.6**
- Usuário admin: `phpos35@gmail.com`

## Stack técnica

| Camada | Tecnologia |
|---|---|
| API | FastAPI + Uvicorn (Python 3.12) |
| Auth | JWT (PyJWT) + bcrypt |
| IA | DeepSeek → OpenAI → Anthropic → Gemini (fallback chain) |
| RAG | NumPy cosine similarity + `text-embedding-3-small` |
| Banco | MySQL (PyMySQL) |
| Frontend | HTML/CSS/JS vanilla, sem framework |
| Deploy | Hetzner VPS + Nginx + Certbot SSL |
