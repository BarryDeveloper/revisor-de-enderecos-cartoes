import re
import unicodedata

MAPA_ESTADOS = {
    "PARÁ": "PA",
    "PARA": "PA",
    "MARANHÃO": "MA",
    "MARANHAO": "MA",
    "MINAS GERAIS": "MG",
    "SÃO PAULO": "SP",
    "SAO PAULO": "SP",
    "RIO DE JANEIRO": "RJ",
    "ESPÍRITO SANTO": "ES",
    "ESPIRITO SANTO": "ES",
    "BAHIA": "BA",
    "GOIÁS": "GO",
    "GOIAS": "GO",
    "PARANÁ": "PR",
    "PARANA": "PR",
    "SANTA CATARINA": "SC",
    "RIO GRANDE DO SUL": "RS",
    "CEARÁ": "CE",
    "CEARA": "CE",
    "PERNAMBUCO": "PE"
}

CIDADES_CONHECIDAS = [
    "Curionópolis", "Curionopolis",
    "Parauapebas",
    "Barão de Cocais", "Barao de Cocais",
    "Santa Bárbara", "Santa Barbara",
    "Imperatriz",
    "São Luís", "Sao Luis",
    "Açailândia", "Acailandia",
    "Itaúna", "Itauna",
    "Conselheiro Lafaiete",
    "Ouro Preto",
    "Mariana",
    "Nova Lima",
    "Belo Horizonte",
    "Marituba",
    "Belém", "Belem",
    "Ananindeua",
    "Marabá", "Maraba",
    "Santarém", "Santarem",
    "Castanhal",
    "Altamira"
]

def _norm_cidade(texto):
    nfkd = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().upper()

# Frases que antecedem o endereço real ("Favor entregar em: Rua X", "Endereço correto: Rua Y")
_RE_PREFIXO_FRASE = re.compile(
    r"^\s*(?:favor|endere[çc]o|entregar|enviar|obs|observa[çc][ãa]o)[^,:\d]{0,40}:\s*", re.IGNORECASE)

# Unidade solta sem rua ("Conjunto 901", "Sala 3 Casa 2"): é complemento, não endereço
_RE_SO_UNIDADE = re.compile(
    r"(?:(?:conjunto|conj\.?|bloco|bl\.?|sala|unidade|apto?\.?|apartamento|casa|loja|andar)\s*[A-Za-z]?\d+[A-Za-z]?(?:\s*[-,]\s*|\s+)?)+",
    re.IGNORECASE)

# UF válida no final do trecho "Cidade/UF - complemento": siglas em maiúsculas ou nome do estado
_UF_SIGLAS = "AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO"
_UF_NOMES = "|".join(re.escape(n) for n in sorted(MAPA_ESTADOS, key=len, reverse=True))
_RE_CIDADE_UF_COM_CAUDA = re.compile(
    rf"(?:,\s*|\s+[-–\/]\s+)([A-Za-zÀ-ÿ\s]{{2,35}})\s*[-,\/–]\s*((?i:{_UF_NOMES})|{_UF_SIGLAS})"
    r"(?P<cauda>\s*[-–]\s*[^,]+|\s*\([^)]*\))\s*$")

class AddressParser:
    """
    Parser especializado para extrair e normalizar endereços contidos
    em campos de texto livre (como o campo Complemento em cadastros de cartões).
    """

    @staticmethod
    def eh_endereco_completo(texto_comp, logradouro_atual="", cep_atual=""):
        """
        Detecta se o campo complemento contém um endereço completo ou se o CEP do sistema é falso/genérico.
        """
        if not texto_comp:
            return False

        texto = str(texto_comp).strip()
        if not texto:
            return False

        # Se o logradouro está vazio, obrigatoriamente precisamos extrair
        if not logradouro_atual or str(logradouro_atual).strip() == "":
            return True

        # Só unidade/andar/bloco (ex: 'Conjunto 901', 'Sala 3'): o endereço já está nas colunas certas
        if _RE_SO_UNIDADE.fullmatch(texto):
            return False

        # Se tem outro CEP explícito no complemento (ex: 68515-000, 68.515-000, 68515000)
        if re.search(r"\b(?:\d{2}\.?\d{3}-?\d{3}|\d{5}-?\d{3}|\d{8})\b", texto):
            return True

        # Se tem CEP de escritório (Nova Lima 34006049) e o complemento tem outra cidade/rua
        cep_limpo = re.sub(r"\D", "", str(cep_atual))
        if cep_limpo == "34006049":
            termos_sede = [
                r"\b(?:rua|avenida|alameda|travessa|rodovia|estrada|passagem|conjunto|vicinal|loteamento|vila|praca|praça)\b",
                r"\b(?:r|av|al|trav|pass|conj|vic|lot)\.",
                r"[-,\/–]\s*([A-Za-zÀ-ÿ]{2,})\s*[-,\/–]\s*(PA|MG|MA|SP|RJ|ES|GO|BA|PR|SC|RS|CE|PE|Par[aá]|Minas Gerais|Maranh[aã]o)\b",
                r"\b(curion[oó]polis|curionopolis|bar[aã]o de cocais|barao de cocais|santa b[aá]rbara|santa barbara|marituba|parauapebas|a[cç]ail[aâ]ndia|acailandia|bel[eé]m|belem|ananindeua|santarem|santar[eé]m|marab[aá]|maraba|castanhal|altamira)\b",
                r"^[A-Za-zÀ-ÿ\s\.\d]+,\s*\d+"
            ]
            if any(re.search(p, texto, re.IGNORECASE) for p in termos_sede):
                return True
            return False

        # Padrões rigorosos com word boundary seguro para abreviações com ponto (r., av., pass.) e UFs com \b
        padroes_endereco = [
            r"(?:\b(?:rua|avenida|alameda|travessa|rodovia|estrada|passagem|conjunto|vicinal|loteamento|vila|praca|praça)\b|\b(?:r|av|al|trav|pass|conj|vic|lot)\.)",
            r"\b(curion[oó]polis|curionopolis|bar[aã]o de cocais|barao de cocais|santa b[aá]rbara|santa barbara|a[cç]ail[aâ]ndia|acailandia|marituba|parauapebas|bel[eé]m|belem|ananindeua|marab[aá]|maraba)\b",
            r"[-,\/–]\s*(PA|MG|MA|SP|RJ|ES|GO|BA|PR|SC|RS|CE|PE|Par[aá]|Minas Gerais|Maranh[aã]o)\b"
        ]

        for padrao in padroes_endereco:
            if re.search(padrao, texto, re.IGNORECASE):
                return True

        return False

    @classmethod
    def limpar_logradouro_com_base_oficial(cls, logradouro, bairro="", cidade="", estado="", texto_original_tinha_virgula=False):
        """
        Limpeza segura de sufixos de bairro/cidade que tenham ficado grudados no logradouro.
        Só atua no final da string e NUNCA remove termos que formem o nome próprio da via
        (ex: 'Rua da Liberdade', 'Rua da Casa Branca', 'Rua Nova Esperança', 'Rua Doutor Parauapebas').
        """
        if not logradouro:
            return ""

        texto_original = str(logradouro).strip()
        texto = texto_original

        # Se a entrada já era separada por vírgula, a primeira parte é o logradouro legítimo
        if texto_original_tinha_virgula:
            return texto_original

        # Lista de prefixos que nunca podem ficar sozinhos ou acompanhados só de preposição
        prefixos_incompletos = [
            r"^(?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|vicinal|vic\.|estrada|estr\.|rodovia|rod\.|praça|praca|conjunto|conj\.|vila|loteamento|lot\.)$",
            r"^(?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|vicinal|vic\.|estrada|estr\.|rodovia|rod\.|praça|praca|conjunto|conj\.|vila|loteamento|lot\.)\s+(?:da|de|do|das|dos|e|doutor|dr\.|prof\.|professor|nova|novo|são|santo|santa)$",
            r"^(?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|vicinal|vic\.|estrada|estr\.|rodovia|rod\.|praça|praca|conjunto|conj\.|vila|loteamento|lot\.)\s+principal\s+do$",
            r"^$"
        ]

        def ficou_incompleto(t):
            t_clean = re.sub(r"\s+", " ", t).strip(" ,-")
            return any(re.match(p, t_clean, re.IGNORECASE) for p in prefixos_incompletos)

        # 1. Remover Bairro exato no FINAL do logradouro se houver pelo menos 2 palavras antes
        if bairro and len(str(bairro).strip()) >= 3:
            b = str(bairro).strip()
            padrao_bairro_fim = rf"\s+\b{re.escape(b)}\b\s*$"
            if re.search(padrao_bairro_fim, texto, re.IGNORECASE):
                candidato = re.sub(padrao_bairro_fim, "", texto, flags=re.IGNORECASE).strip()
                if not ficou_incompleto(candidato):
                    texto = candidato

        # 2. Remover Cidade exata no FINAL do logradouro
        if cidade and len(str(cidade).strip()) >= 3:
            c = str(cidade).strip()
            padrao_cidade_fim = rf"\s+\b{re.escape(c)}\b\s*$"
            if re.search(padrao_cidade_fim, texto, re.IGNORECASE):
                candidato = re.sub(padrao_cidade_fim, "", texto, flags=re.IGNORECASE).strip()
                if not ficou_incompleto(candidato):
                    texto = candidato

        # 3. Remover Estado / UF no final
        for uf_extenso, uf_sigla in MAPA_ESTADOS.items():
            padrao_uf_fim = rf"\s+[-,\/]?\s*\b({re.escape(uf_extenso)}|{re.escape(uf_sigla)})\b\s*$"
            if re.search(padrao_uf_fim, texto, re.IGNORECASE):
                candidato = re.sub(padrao_uf_fim, "", texto, flags=re.IGNORECASE).strip()
                if not ficou_incompleto(candidato):
                    texto = candidato
                    break

        texto_limpo = re.sub(r"\s+", " ", texto).strip(" ,-")
        if ficou_incompleto(texto_limpo):
            return texto_original

        return texto_limpo

    @classmethod
    def extrair(cls, texto_bruto, cidade_padrao="", estado_padrao="", numero_padrao=""):
        """
        Analisa o texto do complemento e extrai de forma estruturada:
        logradouro, numero, bairro, cidade, estado, cep, complemento_real
        """
        texto = str(texto_bruto).strip()
        texto = _RE_PREFIXO_FRASE.sub("", texto)
        tinha_virgula = "," in texto

        resultado = {
            "logradouro": "",
            "numero": "",
            "bairro": "",
            "cidade": "",
            "estado": "",
            "cep": "",
            "complemento_real": "",
            "cidade_incerta": False
        }

        if not texto:
            return resultado

        # 1. Extrair CEP (com pontuação ou sem, e remover prefixo CEP)
        match_cep = re.search(r"(?:CEP\s*:?\s*)?\b(\d{2}\.?\d{3}-?\d{3}|\d{5}-?\d{3}|\d{8})\b", texto, re.IGNORECASE)
        if match_cep:
            cep_raw = match_cep.group(1)
            resultado["cep"] = re.sub(r"\D", "", cep_raw).zfill(8)
            texto = texto[:match_cep.start()] + " " + texto[match_cep.end():]
            texto = re.sub(r"\bCEP\s*:?\s*", " ", texto, flags=re.IGNORECASE).strip()

        # 2. Extrair Cidade e Estado / UF dinamicamente (padrão <Cidade> - <UF> ou <Cidade>/<UF>)
        match_cidade_uf = re.search(r"(?:,\s*|\s+[-–\/]\s+)([A-Za-zÀ-ÿ\s]{2,35})\s*[-,\/–]\s*([A-Za-zÀ-ÿ]{2,15})\s*$", texto)
        cauda_apos_uf = ""
        if not match_cidade_uf:
            # 'Cidade/UF - Casa B' ou 'Cidade/UF (Sala 03)': o que vem depois da UF é complemento
            match_cidade_uf = _RE_CIDADE_UF_COM_CAUDA.search(texto)
            if match_cidade_uf:
                cauda_apos_uf = match_cidade_uf.group("cauda").strip(" -–()")
        if match_cidade_uf:
            cand_cidade = match_cidade_uf.group(1).strip(" ,-–/")
            cand_uf = match_cidade_uf.group(2).strip().upper()
            uf_sigla = MAPA_ESTADOS.get(cand_uf, cand_uf if len(cand_uf) == 2 else "")
            if uf_sigla and len(cand_cidade) >= 2 and not re.search(r"^(?:rua|r\.|avenida|av\.|alameda|travessa|passagem|rodovia|bairro)\b", cand_cidade, re.IGNORECASE):
                # Se for bairro composto com nome de cidade (ex: 'Nova Marituba', 'Vila Marituba')
                m_bairro_comp = re.match(r"^(Nova|Novo|Vila|Jardim|Jd\.?|Parque|Pq\.?|Residencial|Bairro)\s+([A-Za-zÀ-ÿ\s]+)$", cand_cidade, re.IGNORECASE)
                if m_bairro_comp and cand_cidade.upper() not in ("NOVA LIMA", "NOVA IGUACU", "NOVA FRIBURGO"):
                    resultado["estado"] = uf_sigla
                    resultado["cidade"] = m_bairro_comp.group(2).strip()
                    resultado["bairro"] = cand_cidade
                else:
                    resultado["estado"] = uf_sigla
                    resultado["cidade"] = cand_cidade
                    # Pode ser um bairro (ex: 'Rua A, 10, Centro - PA'): se for diferente da cadastrada,
                    # o processador confirma nas APIs (ViaCEP, BrasilAPI, IBGE); sem confirmação, vai para revisão
                    if _norm_cidade(cand_cidade) != _norm_cidade(cidade_padrao):
                        resultado["cidade_incerta"] = True
                texto = texto[:match_cidade_uf.start()].strip(" ,-\\/–")
                if cauda_apos_uf:
                    resultado["complemento_real"] = cauda_apos_uf

        # Fallback de UF se não extraído acima
        if not resultado["estado"]:
            match_uf = re.search(r"[-,\/–]\s*([A-Za-zÀ-ÿ]{2,15})\s*$", texto)
            if not match_uf:
                match_uf = re.search(r"[-,\/–]\s*(PA|MG|MA|SP|RJ|ES|GO|BA|PR|SC|RS|CE|PE|Par[aá]|Minas Gerais|Maranh[aã]o)\b", texto, re.IGNORECASE)
            if match_uf:
                uf_nome = match_uf.group(1).strip().upper()
                uf_sigla = MAPA_ESTADOS.get(uf_nome, uf_nome if len(uf_nome) == 2 else "")
                if uf_sigla:
                    resultado["estado"] = uf_sigla
                    texto = texto[:match_uf.start()] + " " + texto[match_uf.end():]
                    texto = texto.strip(" ,-\\/–")

        # 3. Extrair Cidade por lista conhecida (priorizando última ocorrência e protegendo nomes próprios de pessoas/vias)
        if not resultado["cidade"]:
            for cid in CIDADES_CONHECIDAS:
                padrao_cid = rf"(?:^|[\s,;\-\/–]+)\b({re.escape(cid)})\b"
                matches = list(re.finditer(padrao_cid, texto, re.IGNORECASE))
                for match_cid in reversed(matches):
                    pos = match_cid.start(1)
                    texto_antes = texto[:pos].strip()
                    # Não extrair se for parte de nome de pessoa ou rua (ex: 'Rua Mariana', 'Rua Doutor Mariana', 'Rua da Mariana')
                    if re.search(r"(?:\b(?:rua|avenida|alameda|travessa|rodovia|passagem|doutor|dr\.|prof\.|professor|padre|dom|almirante|general|presidente)\b|\b(?:r|av|dr|prof)\.)\s*$", texto_antes, re.IGNORECASE):
                        continue
                    # Se for precedido por qualificador de bairro (ex: 'Nova Marituba', 'Vila Marituba', 'Jardim Marituba')
                    # e a cidade em si não começa com essa palavra (ex: 'Nova Lima' já casa o bloco 'Nova Lima' inteiro)
                    if re.search(r"\b(?:nova|novo|vila|jardim|jd\.?|parque|pq\.?|residencial|res\.?|bairro|conjunto|conj\.?)\s*$", texto_antes, re.IGNORECASE):
                        if not resultado["cidade"]:
                            resultado["cidade"] = cid
                        continue
                    resultado["cidade"] = cid
                    texto = texto[:match_cid.start()] + " " + texto[match_cid.end():]
                    texto = texto.strip(" ,-\\/–")
                    break
                if resultado["cidade"]:
                    break

        # 4. Extrair referências explícitas de Bairro (ex: Bairro Liberdade, Bairro: Centro)
        match_bairro = re.search(r"\bBairro\s*:?\s*([^,\(\)\-\/]+)", texto, re.IGNORECASE)
        if match_bairro:
            resultado["bairro"] = match_bairro.group(1).strip(" ,-")
            texto = texto[:match_bairro.start()] + " " + texto[match_bairro.end():]
            texto = texto.strip()

        # 5. Extrair complemento real / observações
        match_obs = re.search(r"(\(.*?\)|complemento\s+[^,\-\/]+|Apartamento\s*\d+|Apt\s*\d+\s*bl\s*\d+|Casa\s+de\s+Andar)", texto, re.IGNORECASE)
        if match_obs:
            obs = match_obs.group(0).replace("complemento", "").strip(" ()")
            resultado["complemento_real"] = f"{obs}, {resultado['complemento_real']}" if resultado["complemento_real"] else obs
            texto = texto[:match_obs.start()] + " " + texto[match_obs.end():]
            texto = texto.strip()

        # 6. Extrair Lote / Quadra detalhado com letras e abreviações (ex: Quadra C, Lote 5, Qd 12 Lt 5)
        # Exige espaço após Quadra/Lote para não casar 'Quadrante'
        padrao_lote = r"\b(?:(?:Quadra\s+|Qd\.?\s*)[A-Za-z0-9]+(?:\s*(?:-|e|,)?\s*(?:Lote\s+|Lt\.?\s*|Casa\s*)[A-Za-z0-9]+)?|(?:Lote\s+|Lt\.?\s*)[A-Za-z0-9]+)\b"
        match_lote = re.search(padrao_lote, texto, re.IGNORECASE)
        if match_lote:
            lote_detalhe = match_lote.group(0).strip(" ,-")
            if not resultado["complemento_real"]:
                resultado["complemento_real"] = lote_detalhe
            else:
                resultado["complemento_real"] = f"{lote_detalhe}, {resultado['complemento_real']}"
            texto = texto[:match_lote.start()] + " " + texto[match_lote.end():]
            texto = texto.strip()

        # 7. Normalizar separadores estruturados (vírgula, hífen entre espaços, barra entre palavras/UF)
        # Preserva hífens internos como '123-A' e 'PA-275'
        texto_normalizado = re.sub(r"\s+[\-\/]\s+", ", ", texto)
        texto_normalizado = re.sub(r"(?<=[a-zA-ZÀ-ÿ])\/(?=[a-zA-ZÀ-ÿ]{2}\b)", ", ", texto_normalizado)
        partes = [re.sub(r"\s+", " ", p).strip(" ,-") for p in texto_normalizado.split(",") if p.strip(" ,-")]

        if partes:
            primeira_parte = partes[0]
            # Se for apenas 'Apto 101' ou 'Sala 359' sem nome de rua, não joga como logradouro
            if re.match(r"^(?:Apto|Apartamento|Sala|Bloco|Casa|Garagem|Conjunto|Conj\.?|Unidade|Loja)\s*\d+[a-zA-Z]?$", primeira_parte, re.IGNORECASE):
                if not resultado["complemento_real"]:
                    resultado["complemento_real"] = primeira_parte
                else:
                    resultado["complemento_real"] = f"{primeira_parte}, {resultado['complemento_real']}"
                resto_partes = partes[1:]
            else:
                resultado["logradouro"] = primeira_parte
                resto_partes = partes[1:]

            palavras_proibidas_bairro = [
                r"\brua\b", r"\br\.", r"\bav\b", r"\bav\.", r"\blote\b", r"\blt\b",
                r"\bcasa\b", r"\bapto\b", r"\bquadra\b", r"\bqd\b", r"\bfundos\b", r"\bport[aã]o\b"
            ]

            for p in resto_partes:
                # Se for apenas UF isolada (ex: 'PA', 'MG'), não joga em complemento nem bairro
                p_upper = p.upper()
                if p_upper in MAPA_ESTADOS.values() or p_upper in MAPA_ESTADOS:
                    if not resultado["estado"]:
                        resultado["estado"] = MAPA_ESTADOS.get(p_upper, p_upper)
                    continue

                # Reconhecer números formatados: dígitos, 123A, 123-A, nº 123, S/N, sem número
                m_num = re.match(r"^(?:n[ºo°\.]?\s*)?(\d+(?:-[a-zA-Z0-9]+|[a-zA-Z])?|[a-zA-Z]?\d+|s\/?n|sem\s+n[uú]mero)$", p, re.IGNORECASE)
                if m_num and not resultado["numero"]:
                    resultado["numero"] = re.sub(r"^n[ºo°\.]?\s*", "", p, flags=re.IGNORECASE).strip()
                elif not resultado["bairro"] and len(p) > 2 and not any(re.search(pat, p, re.IGNORECASE) for pat in palavras_proibidas_bairro):
                    resultado["bairro"] = p
                else:
                    if not resultado["complemento_real"]:
                        resultado["complemento_real"] = p
                    else:
                        resultado["complemento_real"] = f"{resultado['complemento_real']}, {p}"

        # Se o logradouro contiver número no meio/final (ex: Rua Sete de Setembro 123 ou Rua São José 20 Nova Marituba)
        # Não separar se for Rodovia (ex: Rodovia PA 275, Rodovia PA-275)
        if resultado["logradouro"]:
            eh_rodovia = bool(re.match(r"^(?:Rodovia|Estrada|BR|PA|MG|SP|RJ)\b", resultado["logradouro"], re.IGNORECASE))
            if not eh_rodovia:
                # Caso A: número no meio seguido de bairro (ex: 'Rua São José 20 Nova Marituba' ou 'Rua A 10 Centro')
                # NÃO casar se o número for parte do nome da via por data (ex: '7 de Setembro', '15 de Novembro', '9 de Janeiro')
                match_num_meio = re.search(r"^(.*?)\s+((?:n[ºo°\.]?\s*)?\d{1,5}(?:-[a-zA-Z0-9]+|[a-zA-Z])?|S\/?N)\s+([A-Za-zÀ-ÿ].*)$", resultado["logradouro"], re.IGNORECASE)
                if match_num_meio and not re.match(r"^(Rua|R\.|Av\.|Avenida|Travessa|Alameda|Passagem)\s+[A-Za-z]?\d{1,4}$", match_num_meio.group(1).strip(), re.IGNORECASE):
                    resto_via = match_num_meio.group(3).strip(" ,-")
                    eh_data_rua = bool(re.match(r"^(?:de|do|da|dos|das|janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b", resto_via, re.IGNORECASE))
                    if not eh_data_rua:
                        nome_via = match_num_meio.group(1).strip()
                        num_via = re.sub(r"^n[ºo°\.]?\s*", "", match_num_meio.group(2).strip(), flags=re.IGNORECASE)
                        if len(nome_via.split()) >= 2 or not re.match(r"^(?:rua|r\.|avenida|av\.|alameda|travessa|passagem|estrada|rodovia)$", nome_via, re.IGNORECASE):
                            resultado["logradouro"] = nome_via
                            if not resultado["numero"]:
                                resultado["numero"] = num_via
                            if not resultado["bairro"] and len(resto_via) > 2:
                                resultado["bairro"] = resto_via
                            elif resto_via and resto_via != resultado["bairro"]:
                                if not resultado["complemento_real"]:
                                    resultado["complemento_real"] = resto_via
                                else:
                                    resultado["complemento_real"] = f"{resultado['complemento_real']}, {resto_via}"

                # Caso B: número no final (ex: 'Rua Sete de Setembro 123' ou 'Rua 15 de Novembro 50')
                if not resultado["numero"] or resultado["logradouro"]:
                    match_num_fim = re.search(r"^(.*?)\s+((?:n[ºo°\.]?\s*)?\d{1,5}(?:-[a-zA-Z0-9]+|[a-zA-Z])?|S\/?N)$", resultado["logradouro"], re.IGNORECASE)
                    if match_num_fim:
                        nome_via = match_num_fim.group(1).strip()
                        if not re.match(r"^(Rua|R\.|Av\.|Avenida|Travessa|Alameda|Passagem)\s+[A-Za-z]?\d{1,4}$", resultado["logradouro"], re.IGNORECASE):
                            if len(nome_via.split()) >= 2 or not re.match(r"^(?:rua|r\.|avenida|av\.|alameda|travessa|passagem|estrada|rodovia)$", nome_via, re.IGNORECASE):
                                resultado["logradouro"] = nome_via
                                if not resultado["numero"]:
                                    resultado["numero"] = re.sub(r"^n[ºo°\.]?\s*", "", match_num_fim.group(2).strip(), flags=re.IGNORECASE)

        # Se cidade ou estado não foram encontrados no texto, usa o padrão caso fornecido
        if not resultado["cidade"] and cidade_padrao:
            resultado["cidade"] = str(cidade_padrao).strip()
        if not resultado["estado"] and estado_padrao:
            resultado["estado"] = str(estado_padrao).strip()

        # 8. Limpeza Segura do Logradouro
        resultado["logradouro"] = cls.limpar_logradouro_com_base_oficial(
            resultado["logradouro"],
            bairro=resultado["bairro"],
            cidade=resultado["cidade"],
            estado=resultado["estado"],
            texto_original_tinha_virgula=tinha_virgula
        )

        return resultado
