# Revisor de Endereços para Cartões Corporativos

Automação em Python desenvolvida para higienização, extração inteligente e padronização de endereços na base de chamados de emissão de cartões corporativos.

---

## 🎯 Objetivo

Resolver o gargalo operacional onde colaboradores em municípios com **CEP Único** (ex: Curionópolis, Parauapebas) ou com dificuldades no formulário preenchem um CEP genérico/escritório no sistema e escrevem o endereço real completo no campo de texto livre **`END_COMPLEMENTO`**.

A automação:
1. Permite selecionar qualquer planilha diretamente pelo **Seletor de Arquivos visual** do Windows.
2. Localiza dinamicamente as colunas do Excel por correspondência exata e filtros negativos (imune a mudanças de ordem).
3. Identifica automaticamente quando o endereço real está no campo complemento.
4. Extrai com precisão: **Logradouro**, **Número**, **Bairro**, **Cidade**, **Estado**, **CEP** e **Complemento Real**.
5. Substitui os dados corrigidos diretamente nas colunas originais, preservando o layout original de 25 colunas.
6. Adiciona a coluna de auditoria **`REVISADO_PELO_SCRIPT`** (`SIM` / `NÃO`) para conferência rápida pelo time.
7. Atualiza e valida CEPs municipais usando cache local em memória com redundância em cascata (**ViaCEP + BrasilAPI**).
8. Salva o arquivo final revisado diretamente **na mesma pasta do arquivo original**, com design corporativo limpo e sem avisos de reparo.

---

## 📁 Estrutura do Projeto

```text
revisor-de-enderecos-cartoes/
├── src/
│   ├── address_parser.py          # Motor de regras e NLP/Regex para extração de endereços
│   ├── cep_service.py             # Validação com Cache + ViaCEP + BrasilAPI
│   └── excel_processor.py         # Leitura dinâmica, substituição in-place e design Excel
├── run_automacao.py               # Script principal (com seletor visual, logging e auto-instalação)
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

---

## ⚠️ Limitações & Casos Especiais

* **Regra de Substituição de CEP:** O script só substitui o CEP do sistema se:
  1. O CEP cadastrado for o CEP da sede corporativa de Nova Lima (`34006-049`) usado como contorno.
  2. A cidade real extraída do complemento for diferente da cidade cadastrada no chamado e pertencer à tabela de municípios de CEP único.
* **Linhas Vazias:** Linhas sem endereço ou em branco são mantidas no arquivo para preservar a contagem exata de chamados e recebem `REVISADO_PELO_SCRIPT = NÃO`.
* **Resiliência de Rede (Modo Offline):** Caso os serviços públicos de CEP (ViaCEP e BrasilAPI) estejam temporariamente indisponíveis, o script utiliza o cache local em memória e mantém os dados originais para revisão manual, sem travar a execução.

---

## 🔒 Privacidade e Proteção de Dados (LGPD)

Este software manipula dados cadastrais operacionais (como nomes, CPFs, telefones e endereços). Recomenda-se:
* Executar a ferramenta exclusivamente em computadores e redes corporativas autorizadas.
* Não compartilhar as planilhas geradas fora dos canais homologados da área de viagens.
