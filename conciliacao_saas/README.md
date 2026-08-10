# Conciliação Transitoria de Fornecedores

Protótipo (Opção A) do SaaS de conciliação da conta **91001001 – TRANSITÓRIA DE FORNECEDORES**.

## Estabelecimentos suportados
- 101, 103, 104, 106

## Como rodar

```bash
cd conciliacao_saas
pip install -r requirements.txt
streamlit run app.py
```

Acesse no navegador: `http://localhost:8501`

## Funcionalidades

### Nova Conciliação
1. Selecione o estabelecimento
2. Informe o período (ex: 07/2026)
3. Faça upload das duas planilhas:
   - **Financeiro** (colunas: Título, Valor Movto, Dat Transac, Série)
   - **Recebimentos** (colunas: Documento, Crédito, Data Trans, Série)
4. Clique em **Executar Conciliação**
5. Veja o resumo e a lista de divergências
6. Baixe o Excel das divergências

### Histórico
- Todas as conciliações são salvas automaticamente em SQLite
- É possível filtrar por estabelecimento e visualizar as divergências de qualquer execução anterior

## Regras de comparação

- **Chave única** = Documento + Série (após normalização)
- Duplicados do mesmo documento+série são **sumarizados** (soma dos valores)
- Tipos de divergência:
  - **Só no Financeiro**
  - **Só no Recebimento**
  - **Valor Diferente** (acima da tolerância configurável, padrão R$ 0,02)

### Normalização de Série
As planilhas gravam a série de formas diferentes (ex: `700` vs `70000`, `9` vs `900`).  
O sistema remove zeros à direita de séries numéricas para alinhar os valores.

## Estrutura

```
conciliacao_saas/
├── app.py                      # Aplicação Streamlit
├── requirements.txt
├── historico_conciliacoes.db   # Criado automaticamente (histórico)
├── uploads/                    # Arquivos enviados são salvos aqui
└── README.md
```

## Próximos passos (evolução para SaaS completo)

1. Autenticação multi-usuário
2. Multi-empresa
3. API REST
4. Frontend Next.js
5. Notificações por e-mail das divergências
6. Agendamento automático de conciliação
