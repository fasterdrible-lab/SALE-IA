# 📂 Pasta de Dados — SALEIA

Esta pasta contém os dados estruturados que alimentam o sistema SALEIA.

## Subpastas

### `/data/clientes/`
Contém arquivos JSON com os perfis de clientes extraídos dos diagnósticos.

- Cada arquivo representa um cliente
- Seguir a estrutura de `exemplo_cliente.json`
- Nomeação sugerida: `{id_cliente}.json`

### `/data/precos/`
Contém a tabela de preços e planos disponíveis.

- `valores.json` — estrutura principal de planos e preços
- **Atenção:** Atualizar com os valores reais extraídos do `Valores.xlsx`

### `/data/scripts/`
Contém os scripts de vendas estruturados como prompts para a IA.

- Transformar o `🚀 SCRIPT OTIMIZADO — VERSÃO FINAL (3).docx` em formato JSON/TXT
- Cada fase do script deve ser um arquivo separado
- Exemplo: `abertura.txt`, `diagnostico_script.txt`, `fechamento.txt`

## Como adicionar um novo cliente

1. Copie o arquivo `clientes/exemplo_cliente.json`
2. Renomeie para o ID do cliente (ex: `cliente_002.json`)
3. Preencha os campos com as informações reais
4. O sistema usará esses dados para personalizar o diagnóstico e o suporte em tempo real
