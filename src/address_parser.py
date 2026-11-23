import re

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
    "GOIAS": "GO"
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
    "Belo Horizonte"
]

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

        # Se tem outro CEP explícito no complemento
        if re.search(r"\b\d{5}-?\d{3}\b", texto):
            return True

        # Se tem CEP de escritório (Nova Lima 34006049) e o complemento tem outra cidade/rua
        cep_limpo = str(cep_atual).replace("-", "").strip()
        if cep_limpo == "34006049" and any(k in texto.lower() for k in ["rua", "av", "cocais", "santa bárbara", "359"]):
            return True

        padroes_endereco = [
            r"\b(rua|r\.|avenida|av\.|alameda|travessa|rodovia)\b",
            r"\b(curion[oó]polis|bar[aã]o de cocais|santa b[aá]rbara|a[cç]ail[aâ]ndia)\b",
            r"-\s*(PA|MG|MA|SP|RJ|ES|Par[aá]|Minas Gerais|Maranh[aã]o)"
        ]

        for padrao in padroes_endereco:
            if re.search(padrao, texto, re.IGNORECASE):
                return True

        return False

    @classmethod
    def extrair(cls, texto_bruto, cidade_padrao="", estado_padrao="", numero_padrao=""):
        """
        Analisa o texto do complemento e extrai de forma estruturada:
        logradouro, numero, bairro, cidade, estado, cep, complemento_real
        """
        texto = str(texto_bruto).strip()
        resultado = {
            "logradouro": "",
            "numero": str(numero_padrao).strip() if numero_padrao else "",
            "bairro": "",
            "cidade": str(cidade_padrao).strip() if cidade_padrao else "",
            "estado": str(estado_padrao).strip() if estado_padrao else "",
            "cep": "",
            "complemento_real": ""
        }

        if not texto:
            return resultado

        # 1. Extrair CEP se existir no texto
        match_cep = re.search(r"\b(\d{5}-?\d{3}|\d{8})\b", texto)
        if match_cep:
            resultado["cep"] = match_cep.group(1).replace("-", "")
            texto = texto.replace(match_cep.group(0), " ").strip()

        # 2. Extrair Estado / UF
        match_uf = re.search(r"-\s*([A-Za-zÀ-ÿ]{2,15})\b", texto)
        if match_uf:
            uf_nome = match_uf.group(1).strip().upper()
            uf_sigla = MAPA_ESTADOS.get(uf_nome, uf_nome if len(uf_nome) == 2 else resultado["estado"])
            resultado["estado"] = uf_sigla
            texto = texto[:match_uf.start()] + " " + texto[match_uf.end():]
            texto = texto.strip()

        # 3. Extrair Cidade (com proteção para não apagar nomes de rua como 'Rua Mariana Silva')
        # Só extrai se a cidade for precedida de separador (, ou - ou fim de texto) e não estiver logo após 'Rua/Avenida'
        for cid in CIDADES_CONHECIDAS:
            padrao_cid = rf"(?:^|[,;\-\/]\s*)\b({re.escape(cid)})\b"
            match_cid = re.search(padrao_cid, texto, re.IGNORECASE)
            if match_cid:
                # Verifica se não faz parte do início de logradouro (ex: "Rua Mariana")
                pos = match_cid.start(1)
                texto_antes = texto[:pos].strip()
                if not re.search(r"\b(rua|r\.|avenida|av\.|alameda|travessa)\s*$", texto_antes, re.IGNORECASE):
                    resultado["cidade"] = cid
                    texto = texto[:match_cid.start()] + " " + texto[match_cid.end():]
                    texto = texto.strip()
                    break

        # 4. Extrair referências explícitas de Bairro (ex: "Bairro Guanabara", "Bairro: Chácaras do Sol - Primavera")
        match_bairro = re.search(r"\bBairro\s*:?\s*([^,\(\)\-\/]+)", texto, re.IGNORECASE)
        if match_bairro:
            resultado["bairro"] = match_bairro.group(1).strip(" ,-")
            texto = texto[:match_bairro.start()] + " " + texto[match_bairro.end():]
            texto = texto.strip()

        # 5. Extrair complemento real / observações (ex: "Complexo Vs10", "Apto 103", "(Próximo a ...)")
        match_obs = re.search(r"(\(.*?\)|complemento\s+[^,\-\/]+|Apartamento\s*\d+|Apt\s*\d+\s*bl\s*\d+|Casa\s+de\s+Andar)", texto, re.IGNORECASE)
        if match_obs:
            resultado["complemento_real"] = match_obs.group(0).replace("complemento", "").strip(" ()")
            texto = texto[:match_obs.start()] + " " + texto[match_obs.end():]
            texto = texto.strip()

        # 6. Extrair Lote / Quadra detalhado
        match_lote = re.search(r"(Quadra\s*\d+.*?Lote\s*\d+|Quadra\s*\d+\s*-\s*Casa\s*\d+)", texto, re.IGNORECASE)
        if match_lote:
            lote_detalhe = match_lote.group(0).strip(" ,-")
            if not resultado["complemento_real"]:
                resultado["complemento_real"] = lote_detalhe
            else:
                resultado["complemento_real"] = f"{lote_detalhe}, {resultado['complemento_real']}"
            texto = texto[:match_lote.start()] + " " + texto[match_lote.end():]
            texto = texto.strip()

        # 7. Normalizar separadores de bairro/rua com hífen ou barra (ex: "Rua A - Centro" -> "Rua A, Centro")
        texto_normalizado = re.sub(r"\s+[\-\/]\s+", ", ", texto)
        partes = [re.sub(r"\s+", " ", p).strip(" ,-") for p in texto_normalizado.split(",") if p.strip(" ,-")]

        if partes:
            resultado["logradouro"] = partes[0]

            for p in partes[1:]:
                # Se for número isolado e ainda não tem número definitivo
                if re.match(r"^\d+$", p):
                    resultado["numero"] = p
                # Se for bairro
                elif not resultado["bairro"] and len(p) > 2 and not any(k in p.lower() for k in ["rua", "av", "lote"]):
                    resultado["bairro"] = p
                # Se sobrar algo como complemento
                elif not resultado["complemento_real"]:
                    resultado["complemento_real"] = p

        # Se o logradouro contiver número no final (ex: "Avenida Espirito Santo 56") MAS não for nome de rua numerada (como "Rua 22", "Rua 15", "Rua M17")
        if resultado["logradouro"]:
            if not re.match(r"^(Rua|R\.|Av\.|Avenida|Travessa)\s+[A-Za-z]?\d{1,4}$", resultado["logradouro"], re.IGNORECASE):
                match_num_fim = re.search(r"^(.*?)\s+(\d{1,5})$", resultado["logradouro"])
                if match_num_fim:
                    resultado["logradouro"] = match_num_fim.group(1).strip()
                    if not resultado["numero"] or resultado["numero"] == str(numero_padrao):
                        resultado["numero"] = match_num_fim.group(2).strip()

        return resultado
