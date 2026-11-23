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
    "Belo Horizonte",
    "Marituba"
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
            r"\b(curion[oó]polis|bar[aã]o de cocais|santa b[aá]rbara|a[cç]ail[aâ]ndia|marituba)\b",
            r"-\s*(PA|MG|MA|SP|RJ|ES|Par[aá]|Minas Gerais|Maranh[aã]o)"
        ]

        for padrao in padroes_endereco:
            if re.search(padrao, texto, re.IGNORECASE):
                return True

        return False

    @classmethod
    def limpar_logradouro_com_base_oficial(cls, logradouro, bairro="", cidade="", estado=""):
        """
        Executa limpeza cruzada no nome da rua, removendo sobras de bairro, cidade,
        estado ou loteamento que tenham ficado grudadas quando o texto original não tinha pontuação.
        Possui trava de segurança para preservar vias homônimas como 'Rua Bandeirantes', 'Rua Pará', 'Avenida Curitiba'.
        """
        if not logradouro:
            return ""

        texto_original = str(logradouro).strip()
        texto = texto_original

        # 1. Se o Bairro confirmado estiver dentro do logradouro (e não for logo após 'Rua/Av'), remove
        if bairro and len(str(bairro).strip()) > 2:
            bairro_limpo = str(bairro).strip()
            if not re.search(rf"\b(rua|r\.|avenida|av\.|alameda|travessa)\s+{re.escape(bairro_limpo)}\b", texto, re.IGNORECASE):
                padrao_bairro = rf"\b{re.escape(bairro_limpo)}\b"
                texto = re.sub(padrao_bairro, " ", texto, flags=re.IGNORECASE).strip()

        # 2. Se a Cidade confirmada estiver dentro do logradouro (e não for logo após 'Rua/Av'), remove
        if cidade and len(str(cidade).strip()) > 2:
            cid_limpa = str(cidade).strip()
            if not re.search(rf"\b(rua|r\.|avenida|av\.|alameda|travessa)\s+{re.escape(cid_limpa)}\b", texto, re.IGNORECASE):
                padrao_cid = rf"\b{re.escape(cid_limpa)}\b"
                texto = re.sub(padrao_cid, " ", texto, flags=re.IGNORECASE).strip()

        # 3. Remover menções a estados que sobraram no final ou no meio (sem ser nome da rua)
        for uf_extenso, uf_sigla in MAPA_ESTADOS.items():
            if not re.search(rf"\b(rua|r\.|avenida|av\.|alameda|travessa)\s+({re.escape(uf_extenso)}|{re.escape(uf_sigla)})\b", texto, re.IGNORECASE):
                texto = re.sub(rf"\b({re.escape(uf_extenso)}|{re.escape(uf_sigla)})\b", " ", texto, flags=re.IGNORECASE).strip()

        # 4. Remover termos de lote/quadra/casa que tenham ficado colados no nome da rua
        texto = re.sub(r"\b(quadra|lote|qd|lt)\b.*$", " ", texto, flags=re.IGNORECASE).strip()

        texto_limpo = re.sub(r"\s+", " ", texto).strip(" ,-")

        # TRAVA DE SEGURANÇA CONTRA VIAS HOMÔNIMAS:
        # Se após a limpeza sobrou apenas o prefixo (ex: "Rua", "Avenida") ou ficou vazio,
        # significa que o nome da via era idêntico ao bairro/cidade (ex: "Rua Bandeirantes").
        # Nesses casos, mantemos o logradouro original para não apagar o nome legítimo da rua.
        prefixos_soltos = [r"^(rua|r\.|avenida|av\.|alameda|travessa|rodovia)$", r"^$"]
        if any(re.match(p, texto_limpo, re.IGNORECASE) for p in prefixos_soltos):
            return texto_original

        return texto_limpo

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
        for cid in CIDADES_CONHECIDAS:
            padrao_cid = rf"(?:^|[,;\-\/]\s*)\b({re.escape(cid)})\b"
            match_cid = re.search(padrao_cid, texto, re.IGNORECASE)
            if match_cid:
                pos = match_cid.start(1)
                texto_antes = texto[:pos].strip()
                if not re.search(r"\b(rua|r\.|avenida|av\.|alameda|travessa)\s*$", texto_antes, re.IGNORECASE):
                    resultado["cidade"] = cid
                    texto = texto[:match_cid.start()] + " " + texto[match_cid.end():]
                    texto = texto.strip()
                    break

        # 4. Extrair referências explícitas de Bairro
        match_bairro = re.search(r"\bBairro\s*:?\s*([^,\(\)\-\/]+)", texto, re.IGNORECASE)
        if match_bairro:
            resultado["bairro"] = match_bairro.group(1).strip(" ,-")
            texto = texto[:match_bairro.start()] + " " + texto[match_bairro.end():]
            texto = texto.strip()

        # 5. Extrair complemento real / observações
        match_obs = re.search(r"(\(.*?\)|complemento\s+[^,\-\/]+|Apartamento\s*\d+|Apt\s*\d+\s*bl\s*\d+|Casa\s+de\s+Andar)", texto, re.IGNORECASE)
        if match_obs:
            resultado["complemento_real"] = match_obs.group(0).replace("complemento", "").strip(" ()")
            texto = texto[:match_obs.start()] + " " + texto[match_obs.end():]
            texto = texto.strip()

        # 6. Extrair Lote / Quadra detalhado
        match_lote = re.search(r"(Quadra\s*\d+.*?Lote\s*\d+|Quadra\s*\d+\s*-\s*Casa\s*\d+|Quadra\s*\w+)", texto, re.IGNORECASE)
        if match_lote:
            lote_detalhe = match_lote.group(0).strip(" ,-")
            if not resultado["complemento_real"]:
                resultado["complemento_real"] = lote_detalhe
            else:
                resultado["complemento_real"] = f"{lote_detalhe}, {resultado['complemento_real']}"
            texto = texto[:match_lote.start()] + " " + texto[match_lote.end():]
            texto = texto.strip()

        # 7. Normalizar separadores de bairro/rua com hífen ou barra
        texto_normalizado = re.sub(r"\s+[\-\/]\s+", ", ", texto)
        partes = [re.sub(r"\s+", " ", p).strip(" ,-") for p in texto_normalizado.split(",") if p.strip(" ,-")]

        if partes:
            resultado["logradouro"] = partes[0]

            for p in partes[1:]:
                if re.match(r"^\d+$", p):
                    resultado["numero"] = p
                elif not resultado["bairro"] and len(p) > 2 and not any(k in p.lower() for k in ["rua", "av", "lote"]):
                    resultado["bairro"] = p
                elif not resultado["complemento_real"]:
                    resultado["complemento_real"] = p

        # Se o logradouro contiver número no final
        if resultado["logradouro"]:
            if not re.match(r"^(Rua|R\.|Av\.|Avenida|Travessa)\s+[A-Za-z]?\d{1,4}$", resultado["logradouro"], re.IGNORECASE):
                match_num_fim = re.search(r"^(.*?)\s+(\d{1,5})$", resultado["logradouro"])
                if match_num_fim:
                    resultado["logradouro"] = match_num_fim.group(1).strip()
                    if not resultado["numero"] or resultado["numero"] == str(numero_padrao):
                        resultado["numero"] = match_num_fim.group(2).strip()

        # 8. Limpeza Reversa do Logradouro com Trava de Segurança
        resultado["logradouro"] = cls.limpar_logradouro_com_base_oficial(
            resultado["logradouro"],
            bairro=resultado["bairro"],
            cidade=resultado["cidade"],
            estado=resultado["estado"]
        )

        return resultado
