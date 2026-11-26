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
5. Substitui os dados corrigidos diretamente nas colunas originais, preservando o layout original.
6. Não grava colunas de backup: a planilha original nunca é alterada (o resultado é um arquivo novo), então para comparar basta abrir as duas.
7. Adiciona a coluna de auditoria **`REVISADO_PELO_SCRIPT`** (`SIM` / `NÃO`) apenas quando houver alteração real de dados.
8. Adiciona **`STATUS_EMISSAO`** (`PRONTO` / `REVISAR`) e **`MOTIVO_REVISAO`** (o que impediu a emissão automática), para a equipe filtrar só o que precisa de conferência manual.
9. Tolera textos como `Favor entregar em: Rua X...`, `Cidade/UF - Casa B` e complementos só de unidade (`Conjunto 901`, `Sala 3`), que não são tratados como endereço.
10. Atualiza e valida CEPs municipais usando cache local em memória com redundância em cascata (**ViaCEP + BrasilAPI**) e Circuit Breaker corporativo.
11. Salva o arquivo final revisado diretamente **na mesma pasta do arquivo original com carimbo de data/hora** (`_REVISADO_YYYYMMDD_HHMMSS.xlsx`), evitando sobrescrever edições manuais.

---

## 📁 Estrutura do Projeto

```text
revisor-de-enderecos-cartoes/
├── src/
│   ├── address_parser.py          # Motor de regras e NLP/Regex para extração de endereços
│   ├── cep_service.py             # Validação com Cache + ViaCEP + BrasilAPI + Circuit Breaker
│   └── excel_processor.py         # Leitura dinâmica, substituição in-place e design Excel
├── tests/
│   ├── test_regressao.py          # Suíte de regressão e casos de borda (APIs simuladas)
│   └── test_suite.py              # Testes unitários do motor de parsing e serviços
├── run_automacao.py               # Script principal (com seletor visual, logging e auto-instalação)
├── requirements.txt               # Dependências leves do projeto (openpyxl e requests)
└── README.md                      # Documentação de uso
```

---

## 🚀 Como Executar

### 1. Preparação Inicial (Apenas uma vez)
- Ter o **Python** instalado no computador com a opção **`[x] Add python.exe to PATH`** marcada durante a instalação.
- *(O script possui auto-instalação e baixa automaticamente as bibliotecas leves `openpyxl` e `requests` na primeira execução).*

### 2. No Dia a Dia
Basta dar **duplo clique no arquivo `run_automacao.py`**:
1. Uma janela de seleção de arquivos do Windows abrirá na tela.
2. Escolha a planilha baixada do sistema de chamados.
3. O script processa e revisa os endereços em poucos segundos.
4. O arquivo final será gerado automaticamente na **mesma pasta** de onde você selecionou a planilha:
   `[PASTA_ORIGINAL]/[NOME_DA_PLANILHA]_REVISADO_YYYYMMDD_HHMMSS.xlsx`
5. Uma notificação visual de sucesso confirma a conclusão e o local do arquivo.
6. Em caso de erro, os detalhes ficam gravados em `revisor.log`, na mesma pasta do `run_automacao.py`.

---

## ⚠️ Limitações & Casos Especiais

* **Regra de Substituição de CEP:** O CEP cadastrado é tratado como uma "chave" que libera o campo (pode ser de qualquer lugar do país). O script só mexe no CEP quando o complemento traz um endereço:
  1. Se o complemento traz um CEP, esse CEP é usado e a cidade e a UF são corrigidas por ele.
  2. Se traz o endereço sem CEP, o CEP é descoberto pelo endereço na ViaCEP: cidade de CEP único, ou rua desempatada pelo número da casa (faixas dos Correios) e pelo bairro. A tabela local de cidades de CEP único é só cache.
  3. Se o cadastro já estava correto e o complemento só repete o endereço, o CEP cadastrado é mantido.
  4. Se o CEP do endereço não puder ser confirmado, a linha vai para revisão manual.
  5. Complemento sem endereço (ex: `Apto 101`) não altera a linha.
* **Validação de Cidade:** Quando a cidade do complemento é diferente da cadastrada, ela é confirmada por API: ViaCEP, reserva BrasilAPI e reserva IBGE. Se não for confirmada (ex: um bairro escrito como `Centro - PA`) ou se nenhuma API responder, a linha vai para revisão manual.
* **CEP Antigo de Outra Cidade:** Se a cidade mudou e nenhum CEP novo foi encontrado, a linha vai para revisão em vez de manter o CEP antigo.
* **Linhas Vazias:** Linhas sem endereço ou em branco são mantidas no arquivo para preservar a contagem exata de chamados e recebem `REVISADO_PELO_SCRIPT = NÃO`.
* **Resiliência de Rede (Modo Offline):** Caso os serviços públicos de CEP (ViaCEP e BrasilAPI) estejam temporariamente indisponíveis, o script utiliza o cache local em memória e mantém os dados originais para revisão manual, sem travar a execução.
* **Aviso de APIs indisponíveis:** se ViaCEP, BrasilAPI ou IBGE ficarem fora do ar durante o processamento, o popup final aparece como aviso amarelo e a coluna `MOTIVO_REVISAO` indica 'Consulta de CEP indisponível (rede/proxy)'.

---

## 🔒 Privacidade e Proteção de Dados (LGPD)

Este software manipula dados cadastrais operacionais (como nomes, CPFs, telefones e endereços). Recomenda-se:
* Executar a ferramenta exclusivamente em computadores e redes corporativas autorizadas.
* Não compartilhar as planilhas geradas fora dos canais homologados da área de viagens.
