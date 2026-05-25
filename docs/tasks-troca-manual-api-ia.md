# Tasks: botao para trocar o provedor de IA manualmente

## Issue 1 - Persistir ordem de prioridade dos provedores no backend

Arquivos:
- Modificar `api/ai_router.py`
- Modificar `api/main.py`

Reutilizacao:
- Reaproveitar `status_provedores()` e a ordem configuravel existente em `AI_PROVIDER_ORDER`.
- Reaproveitar o fallback automatico ja implementado.

Dependencias:
- Nenhuma nova dependencia.

Cenarios:
- Sucesso ao rotacionar a prioridade.
- Ordem persistida em arquivo local.
- Fallback para a ordem padrao quando o arquivo estiver ausente ou corrompido.
- Apenas um provedor configurado.

## Issue 2 - Exibir status e botao no popup da extensao

Arquivos:
- Modificar `chrome-extension/popup.html`
- Modificar `chrome-extension/popup.js`
- Modificar `chrome-extension/popup.css`
- Modificar `chrome-extension/background.js`

Reutilizacao:
- Reaproveitar o popup atual, que ja concentra configuracao da extensao.
- Reaproveitar o proxy de fetch do `background.js`.

Dependencias:
- Nenhuma nova dependencia.

Cenarios:
- Popup mostra os provedores e a prioridade atual.
- Botao troca a prioridade com feedback visual.
- Falha de rede ou backend indisponivel mostra erro claro.

## Issue 3 - Cobrir o fluxo com testes unitarios

Arquivos:
- Modificar `tests/test_ai_router.py`

Reutilizacao:
- Reaproveitar `unittest` e `unittest.mock`.

Dependencias:
- Nenhuma nova dependencia.

Cenarios:
- Ordem salva e lida corretamente.
- Rotacao da prioridade altera a ordem esperada.
- Ordem invalida cai para o comportamento padrao.
