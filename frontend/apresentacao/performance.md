# Prompt — Performance

## Objetivo

Gerar uma apresentação focada em performance e resultados concretos esperados para o cliente, com base no perfil e nos dados financeiros identificados na reunião.

## Dados de entrada esperados

O endpoint `/cenario/{meeting_id}/conducao` receberá:

```json
{
  "tipo": "performance",
  "dados": { /* objeto completo retornado por /api/cenario/{meeting_id} */ }
}
```

## Estrutura da resposta esperada

O backend deve retornar um objeto com o campo `conteudo` (string Markdown):

```json
{ "conteudo": "**Performance — Resultados Esperados para {Nome do Cliente}**\n\n..." }
```

## Prompt para o modelo de IA

```
Você é um consultor de vendas especialista em resultados. Com base no perfil do cliente
abaixo, gere uma apresentação de performance que mostre os resultados concretos que o
cliente pode esperar ao investir no produto recomendado.

PERFIL DO CLIENTE:
- Nome: {nome_cliente}
- Perfil DISC: {perfil_disc.tipo} — {perfil_disc.descricao}
- Faturamento / Renda: {mapa_financeiro.faturamento_mensal ou renda_clt}
- Capacidade de investimento: {mapa_financeiro.capacidade_investimento}
- Produto recomendado: {mapa_financeiro.produto_indicado.nome}
- Justificativa do produto: {mapa_financeiro.produto_indicado.justificativa}
- Score de interesse: {score_compra.valor}/100

REGRAS:
1. Não invente dados que não estejam nos dados fornecidos.
2. Use linguagem de resultado (ROI, crescimento, proteção, eficiência).
3. Adapte o tom ao perfil DISC (D=números e resultados, I=reconhecimento e crescimento,
   S=segurança e estabilidade, C=dados comparativos e análise).
4. Apresente 3 cenários realistas: conservador, moderado e otimista.
5. Máximo 350 palavras. Finalize com um próximo passo claro.
6. Responda apenas em português do Brasil.
```

## Observações de segurança

- Nunca expor chaves de API no retorno.
- Nunca fabricar projeções financeiras sem base nos dados fornecidos.
- Deixar explícito que são estimativas baseadas no perfil, não garantias.
- Apenas usuários autenticados podem acionar este endpoint.
