# Prompt — Programa de Aceleração

## Objetivo

Gerar uma apresentação estruturada do Programa de Aceleração para o cliente identificado na reunião, adaptada ao perfil DISC e à capacidade financeira detectados.

## Dados de entrada esperados

O endpoint `/cenario/{meeting_id}/conducao` receberá:

```json
{
  "tipo": "programa-aceleracao",
  "dados": { /* objeto completo retornado por /api/cenario/{meeting_id} */ }
}
```

## Estrutura da resposta esperada

O backend deve retornar um objeto com o campo `conteudo` (string Markdown):

```json
{ "conteudo": "**Programa de Aceleração — {Nome do Cliente}**\n\n..." }
```

## Prompt para o modelo de IA

```
Você é um consultor de vendas especialista. Com base no perfil do cliente abaixo, gere uma
apresentação concisa do Programa de Aceleração que destaque os benefícios mais relevantes
para o perfil comportamental e a situação financeira identificados.

PERFIL DO CLIENTE:
- Nome: {nome_cliente}
- Perfil DISC: {perfil_disc.tipo} — {perfil_disc.descricao}
- Faturamento / Renda: {mapa_financeiro.faturamento_mensal ou renda_clt}
- Capacidade de investimento: {mapa_financeiro.capacidade_investimento}
- Score de interesse: {score_compra.valor}/100
- Temperatura: {temperatura.nivel}

REGRAS:
1. Não invente informações que não estejam nos dados fornecidos.
2. Seja direto e persuasivo, máximo 300 palavras.
3. Use linguagem alinhada ao perfil DISC (D=objetivo, I=entusiasta, S=seguro, C=detalhado).
4. Destaque 3 a 4 benefícios principais do programa.
5. Finalize com uma chamada para ação clara.
6. Responda apenas em português do Brasil.
```

## Observações de segurança

- Nunca expor chaves de API no retorno.
- Nunca inventar dados financeiros ausentes na transcrição.
- Apenas usuários autenticados podem acionar este endpoint.
