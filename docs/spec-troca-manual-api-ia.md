# Spec: botao para trocar o provedor de IA manualmente

## Descricao geral

Adicionar uma acao manual na extensao Chrome para que o usuario possa trocar a prioridade do provedor de IA quando perceber falha, lentidao ou indisponibilidade em um dos provedores configurados.

O comportamento deve permanecer seguro: o frontend nunca recebe chaves, nunca decide qual modelo chamar diretamente e nunca contorna o backend. A troca apenas altera a ordem de preferencia dos provedores no backend, que continua fazendo o fallback automatico em todas as chamadas.

## Superficies afetadas

### Extensao Chrome

Componentes:
- `chrome-extension/popup.html`
- `chrome-extension/popup.js`
- `chrome-extension/popup.css`
- `chrome-extension/background.js`

Comportamento do usuario:
- O usuario abre o popup da extensao.
- Visualiza o estado atual dos provedores de IA.
- Clica no botao de troca para mover o proximo provedor para a frente da fila.
- Recebe feedback imediato se a troca foi aplicada ou se o backend esta indisponivel.

### API FastAPI

Componentes:
- `api/ai_router.py`
- `api/main.py`

Comportamento do usuario:
- O backend mantem a ordem de preferencia dos provedores.
- O endpoint de troca persiste a nova ordem em arquivo local seguro no servidor.
- O endpoint `/health` continua informando status operacional sem expor segredos.

## Componentes da tela

- Status resumido da IA no popup.
- Lista curta com o estado dos provedores configurados.
- Botao de acao para trocar a prioridade do provedor principal.
- Mensagem de retorno com sucesso, erro ou fallback aplicado.

## Comportamentos esperados

Sucesso:
- O usuario clica no botao.
- O backend rotaciona a ordem de prioridade.
- O popup exibe o novo provedor preferido.

Erro:
- O backend esta offline.
- Nenhum provedor esta configurado.
- O arquivo de ordem nao pode ser salvo.

Edge cases:
- Apenas um provedor esta configurado.
- Um provedor esta em cooldown, mas ainda deve aparecer no status.
- O arquivo local de ordem esta corrompido e o backend deve voltar para a ordem padrao.

## Banco de dados

Nao ha alteracao de banco. A preferencia de ordem fica em arquivo local no backend, fora do frontend.

## Seguranca

- Nenhuma chave sai do backend.
- O frontend apenas solicita a troca e exibe o resultado.
- A ordem salva nao deve conter dados sensiveis.
