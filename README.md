# Automação de Emissão de Cartões Corporativos - Time de Viagens

Projeto desenvolvido para higienização, extração inteligente e padronização de endereços da base de chamados de emissão de cartões corporativos.

---

## 🎯 Objetivo

Resolver o gargalo operacional onde colaboradores em municípios com **CEP Único** (ex: Curionópolis, Parauapebas) ou com dificuldades de CEP preenchem um CEP genérico/escritório no sistema e escrevem o endereço real completo no campo livre **`END_COMPLEMENTO`**.

A automação:
1. Permite selecionar qualquer planilha diretamente pelo **Seletor de Arquivos visual** do Windows.
2. Localiza dinamicamente as colunas do Excel independentemente da ordem.
3. Identifica automaticamente quando o endereço real está no campo complemento.
4. Extrai com precisão: **Logradouro**, **Número**, **Bairro**, **Cidade**, **Estado**, **CEP** e **Complemento Real**.
5. Substitui os dados corrigidos diretamente nas colunas originais, preservando o layout de 25 colunas.
6. Atualiza e valida CEPs municipais usando cache local com redundância em cascata (**ViaCEP + BrasilAPI**).
7. Salva o arquivo final revisado diretamente **na mesma pasta do arquivo original**, com design limpo e sem avisos de reparo.

---

## 📁 Estrutura do Projeto

```text
Time Viajens/
├── src/
│   ├── address_parser.py          # Motor de regras e NLP/Regex para extração de endereços
│   ├── cep_service.py             # Validação com Cache + ViaCEP + BrasilAPI
│   └── excel_processor.py         # Leitura dinâmica, substituição in-place e design Excel
├── run_automacao.py               # Script principal (com seletor visual e auto-instalação)
├── requirements.txt               # Dependências do projeto
└── README.md                      # Documentação de uso
```

---

## 🚀 Como Executar

### 1. Preparação Inicial (Apenas uma vez)
- Ter o **Python** instalado no computador com a opção **`[x] Add python.exe to PATH`** marcada durante a instalação.
- *(O script possui auto-instalação e baixa automaticamente as bibliotecas `pandas`, `openpyxl` e `requests` na primeira execução).*

### 2. No Dia a Dia
Basta dar **duplo clique no arquivo `run_automacao.py`**:
1. Uma janela de seleção de arquivos do Windows abrirá na tela.
2. Escolha a planilha baixada do sistema de chamados.
3. O script processa e revisa os endereços em poucos segundos.
4. O arquivo final será gerado automaticamente na **mesma pasta** de onde você selecionou a planilha:
   `[PASTA_ORIGINAL]/[NOME_DA_PLANILHA]_REVISADO.xlsx`
5. Uma notificação visual de sucesso confirma a conclusão e o local do arquivo.
