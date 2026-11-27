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

_NUMEROS_EXTENSO = {
    "UM": "1", "UMA": "1", "PRIMEIRO": "1", "PRIMEIRA": "1", "1O": "1", "1A": "1",
    "DOIS": "2", "DUAS": "2", "SEGUNDO": "2", "SEGUNDA": "2", "2O": "2", "2A": "2",
    "TRES": "3", "TERCEIRO": "3", "TERCEIRA": "3", "3O": "3", "3A": "3",
    "QUATRO": "4", "QUARTO": "4", "QUARTA": "4", "4O": "4", "4A": "4",
    "CINCO": "5", "QUINTO": "5", "QUINTA": "5", "5O": "5", "5A": "5",
    "SEIS": "6", "SEXTO": "6", "SEXTA": "6", "6O": "6", "6A": "6",
    "SETE": "7", "SETIMO": "7", "SETIMA": "7", "7O": "7", "7A": "7",
    "OITO": "8", "OITAVO": "8", "OITAVA": "8", "8O": "8", "8A": "8",
    "NOVE": "9", "NONO": "9", "NONA": "9", "9O": "9", "9A": "9",
    "DEZ": "10", "DECIMO": "10", "DECIMA": "10", "10O": "10", "10A": "10",
    "ONZE": "11", "DOZE": "12", "TREZE": "13", "QUATORZE": "14", "CATORZE": "14",
    "QUINZE": "15", "DEZESSEIS": "16", "DEZESSETE": "17", "DEZOITO": "18",
    "DEZENOVE": "19", "VINTE": "20", "TRINTA": "30"
}


def _sem_acento_upper(texto):
    nfkd = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().upper()


def _norm_cidade(texto):
    return _sem_acento_upper(texto)


def normalizar_numeros_por_extenso(texto):
    """
    Converte números cardinais/ordinais escritos por extenso isolados em algarismos
    (ex: 'Rua tres' -> 'Rua 3', 'Rua Quinze de Novembro' -> 'Rua 15 de Novembro'),
    mantendo a capitalização original das demais palavras.
    """
    if not texto:
        return ""
    tokens = str(texto).split()
    resultado_tokens = []
    for tok in tokens:
        limpo = _sem_acento_upper(re.sub(r"[º°\.]+$", "", tok))
        if limpo in _NUMEROS_EXTENSO:
            resultado_tokens.append(_NUMEROS_EXTENSO[limpo])
        else:
            resultado_tokens.append(tok)
    return " ".join(resultado_tokens)


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

# Prefixos de logradouro para detecção estrutural
_RE_INICIO_VIA = re.compile(
    r"^(?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|rodovia|rod\.|estrada|estr\.|vicinal|vic\.|praça|praca)\b",
    re.IGNORECASE,
)


class AddressParser:
    """
    Parser especializado para extrair e normalizar endereços contidos
    em campos de texto livre (como o campo Complemento em cadastros de cartões).
    """

    @staticmethod
    def eh_endereco_completo(texto_comp, logradouro_atual="", cep_atual=""):
        """
        Detecta se o campo complemento contém um endereço completo ou se o CEP do sistema é genérico.
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

        # Padrões rigorosos com word boundary seguro para abreviações com ponto (r., av., pass.) e UFs com \b
        padroes_endereco = [
            r"(?:\b(?:rua|avenida|alameda|travessa|rodovia|estrada|passagem|conjunto|vicinal|loteamento|vila|praca|praça)\b|\b(?:r|av|al|trav|pass|conj|vic|lot)\.)",
            r"\b(curion[oó]polis|curionopolis|bar[aã]o de cocais|barao de cocais|santa b[aá]rbara|santa barbara|a[cç]ail[aâ]ndia|acailandia|marituba|parauapebas|bel[eé]m|belem|ananindeua|marab[aá]|maraba|nova lima)\b",
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
            return normalizar_numeros_por_extenso(texto_original)

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
            return normalizar_numeros_por_extenso(texto_original)

        return normalizar_numeros_por_extenso(texto_limpo)

    @classmethod
    def extrair(cls, texto_bruto, cidade_padrao="", estado_padrao="", numero_padrao=""):
        """
        Analisa o texto do complemento e extrai de forma estruturada:
        logradouro, numero, bairro, cidade, estado, cep, complemento_real
        """
        # 0. Normalizar tabulações, quebras de linha e espaços duplicados
        texto = re.sub(r"[\t\r\n]+", " ", str(texto_bruto or ""))
        texto = re.sub(r"\s{2,}", " ", texto).strip()
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
                m_bairro_comp = re.match(r"^(Nova|Novo|Vila|Jardim|Jd\.?|Parque|Pq\.?|Residencial|Condom[ií]nio|Cond\.?|Bairro)\s+([A-Za-zÀ-ÿ\s]+)$", cand_cidade, re.IGNORECASE)
                if m_bairro_comp and cand_cidade.upper() not in ("NOVA LIMA", "NOVA IGUACU", "NOVA FRIBURGO"):
                    resultado["estado"] = uf_sigla
                    resultado["cidade"] = m_bairro_comp.group(2).strip()
                    resultado["bairro"] = cand_cidade
                else:
                    resultado["estado"] = uf_sigla
                    resultado["cidade"] = cand_cidade
                    if _norm_cidade(cand_cidade) != _norm_cidade(cidade_padrao):
                        resultado["cidade_incerta"] = True
                texto = texto[:match_cidade_uf.start()].strip(" ,-\\/–")
                if cauda_apos_uf:
                    resultado["complemento_real"] = cauda_apos_uf

        # Bairro composto no fim, quando não há vírgula antes da UF:
        # "Rua São José 20 Nova Marituba - PA"
        if not resultado["cidade"]:
            match_bairro_composto = re.search(
                r"\b(Nova|Novo|Vila|Jardim|Jd\.?|Parque|Pq\.?|Residencial|Condom[ií]nio|Cond\.?|Bairro)\s+([A-Za-zÀ-ÿ\s]+?)\s*[-–]\s*(PA|MG|MA|SP|RJ|ES|GO|BA|PR|SC|RS|CE|PE)\s*$",
                texto,
                re.IGNORECASE,
            )
            if match_bairro_composto:
                bairro_encontrado = " ".join(match_bairro_composto.group(1, 2)).strip()
                cidade_encontrada = match_bairro_composto.group(2).strip()
                resultado["bairro"] = bairro_encontrado
                resultado["estado"] = match_bairro_composto.group(3).upper()
                resultado["cidade"] = cidade_encontrada
                texto = texto[:match_bairro_composto.start()].strip(" ,-\\/–")

        # Fallback de UF se não extraído acima (aceita também UF solta no final sem hífen/vírgula, ex: 'Centro Parauapebas PA')
        if not resultado["estado"]:
            match_uf = re.search(r"[-,\/–]\s*([A-Za-zÀ-ÿ]{2,15})\s*$", texto)
            if not match_uf:
                match_uf = re.search(r"[-,\/–]\s*(PA|MG|MA|SP|RJ|ES|GO|BA|PR|SC|RS|CE|PE|Par[aá]|Minas Gerais|Maranh[aã]o)\b", texto, re.IGNORECASE)
            if not match_uf:
                match_uf = re.search(rf"\s+({_UF_SIGLAS})\s*$", texto)
            if match_uf:
                uf_nome = match_uf.group(1).strip().upper()
                uf_sigla = MAPA_ESTADOS.get(uf_nome, uf_nome if len(uf_nome) == 2 else "")
                if uf_sigla:
                    resultado["estado"] = uf_sigla
                    texto = texto[:match_uf.start()] + " " + texto[match_uf.end():]
                    texto = texto.strip(" ,-\\/–")

        # 3. Extrair Cidade por lista conhecida apenas se não houver termo de via ou bairro colado antes
        if not resultado["cidade"]:
            padrao_antes_bloqueado = re.compile(
                r"(?:\b(?:rua|avenida|alameda|travessa|rodovia|estrada|passagem|vicinal|"
                r"bairro|vila|jardim|jd\.?|parque|pq\.?|residencial|res\.?|condom[ií]nio|cond\.?|loteamento|lot\.?|"
                r"conjunto|conj\.?|quadra|qd\.?|doutor|dr\.|prof\.|professor|padre|dom)\b"
                r"|\b(?:r|av|al|trav|pass|vic|lot|conj|qd|dr|prof)\.)\s*$",
                re.IGNORECASE,
            )
            padrao_bairro_composto_mesma_cidade = re.compile(
                r"(?:^|,)\s*(?:casa(?:\s*\d+)?\s*,\s*)?(?:rua|r\.|avenida|av\.)[^,]+,\s*(?:\d+\s*,\s*)?(?:nova|novo|vila|jardim|jd\.?|parque|pq\.?|residencial|res\.?|condom[ií]nio|cond\.?)\s+$",
                re.IGNORECASE,
            )
            for cid in CIDADES_CONHECIDAS:
                padrao_cid = rf"(?:^|[\s,;\-\/–]+)\b({re.escape(cid)})\b"
                matches = list(re.finditer(padrao_cid, texto, re.IGNORECASE))
                for match_cid in reversed(matches):
                    pos = match_cid.start(1)
                    texto_antes = texto[:pos].strip()
                    if padrao_antes_bloqueado.search(texto_antes):
                        continue
                    if (
                        cidade_padrao
                        and _norm_cidade(cid) == _norm_cidade(cidade_padrao)
                        and padrao_bairro_composto_mesma_cidade.search(texto[:pos])
                    ):
                        continue
                    resultado["cidade"] = cid
                    texto = texto[:match_cid.start()] + " " + texto[match_cid.end():]
                    texto = texto.strip(" ,-\\/–")
                    break
                if resultado["cidade"]:
                    break

        # Separar rótulos explícitos seguros antes de extrair bairro/complemento e dividir por vírgula
        texto = re.sub(
            r"\s+\b(bairro|complemento|comp|ref|refer[êe]ncia|obs|observa[çc][ãa]o)\b(?:\s*[:\-]\s*|\s+)",
            r", \1: ",
            texto,
            flags=re.IGNORECASE,
        )

        # Se começou com 'Bairro <nome> <TipoVia> ...' sem vírgula, separa o bairro da via antes de extrair Bairro
        texto = re.sub(
            r"^(\s*Bairro\s*:?\s*[A-Za-zÀ-ÿ0-9\s]{2,30}?)\s+((?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|rodovia|estrada)\b)",
            r"\1, \2",
            texto,
            flags=re.IGNORECASE,
        )

        # 4. Extrair referências explícitas de Bairro (ex: Bairro Liberdade, Bairro: Centro)
        match_bairro = re.search(r"\bBairro\s*:?\s*([^,\(\)\-\/]+)", texto, re.IGNORECASE)
        if match_bairro:
            resultado["bairro"] = match_bairro.group(1).strip(" ,-")
            texto = texto[:match_bairro.start()] + " " + texto[match_bairro.end():]
            texto = texto.strip()

        # 5. Extrair complemento real / observações / unidades internas explícitas
        match_obs = re.search(
            r"(\(.*?\)|complemento\s*:?\s*[^,\-\/]+|obs\s*:?\s*[^,\-\/]+|ref(?:er[êe]ncia)?\s*:?\s*[^,\-\/]+|"
            r"\b(?:apartamento|apto?\.?|bloco|bl\.?|sala|conjunto|conj\.?|cobertura|subsolo|andar|garagem|vaga|box)\s*[A-Za-z0-9-]*|"
            r"\bcasa\s+de\s+andar\b)",
            texto,
            re.IGNORECASE,
        )
        if match_obs:
            obs = re.sub(r"^(?:complemento|obs|ref(?:er[êe]ncia)?)\s*:?\s*", "", match_obs.group(0), flags=re.IGNORECASE).strip(" ()")
            if obs:
                resultado["complemento_real"] = f"{obs}, {resultado['complemento_real']}" if resultado["complemento_real"] else obs
            texto = texto[:match_obs.start()] + " " + texto[match_obs.end():]
            texto = texto.strip()

        # 6. Extrair Quadra e Lote:
        # Regra operacional: Lote (Lote/Lt.) vale como número da casa quando não houver outro número explícito
        lote_extraido = ""
        match_qd_lt = re.search(
            r"\b((?:Quadra|Qd\.?)(?![A-Za-zÀ-ÿ])\s*[A-Za-z0-9]+)\s*(?:[-,e]\s*)?((?:Lote|Lt\.?)\s*[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?)\b",
            texto,
            re.IGNORECASE,
        )
        if match_qd_lt:
            qd_txt = match_qd_lt.group(1).strip(" ,-")
            lote_extraido = match_qd_lt.group(2).strip(" ,-")
            resultado["complemento_real"] = f"{qd_txt}, {resultado['complemento_real']}" if resultado["complemento_real"] else qd_txt
            texto = (texto[:match_qd_lt.start()] + " " + texto[match_qd_lt.end():]).strip()
        else:
            match_qd = re.search(r"\b(?:Quadra|Qd\.?)(?![A-Za-zÀ-ÿ])\s*[A-Za-z0-9]+\b", texto, re.IGNORECASE)
            if match_qd:
                qd_txt = match_qd.group(0).strip(" ,-")
                resultado["complemento_real"] = f"{qd_txt}, {resultado['complemento_real']}" if resultado["complemento_real"] else qd_txt
                texto = (texto[:match_qd.start()] + " " + texto[match_qd.end():]).strip()

            match_lt = re.search(r"\b(?:Lote|Lt\.?)\s*[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?\b", texto, re.IGNORECASE)
            if match_lt:
                lote_extraido = match_lt.group(0).strip(" ,-")
                texto = (texto[:match_lt.start()] + " " + texto[match_lt.end():]).strip()

        # Normaliza vírgula virtual quando texto começa com unidade solta seguida direto de via sem vírgula
        # Ex: 'Casa 02 Rua das Flores 120 Centro' -> 'Casa 02, Rua das Flores 120 Centro'
        texto = re.sub(
            r"^((?:Apto|Apartamento|Sala|Bloco|Garagem|Conjunto|Conj\.?|Unidade|Loja)\s*\d+[a-zA-Z]?|Casa(?:\s*\d+[a-zA-Z]?)?)\s+((?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|rodovia|estrada|praça|praca)\b)",
            r"\1, \2",
            texto,
            flags=re.IGNORECASE,
        )

        # 7. Normalizar separadores estruturados (vírgula, hífen entre espaços, barra entre palavras/UF)
        texto_normalizado = re.sub(r"\s+[\-\/]\s+", ", ", texto)
        texto_normalizado = re.sub(r"(?<=[a-zA-ZÀ-ÿ])\/(?=[a-zA-ZÀ-ÿ]{2}\b)", ", ", texto_normalizado)
        partes = [re.sub(r"\s+", " ", p).strip(" ,-") for p in texto_normalizado.split(",") if p.strip(" ,-")]

        if partes:
            primeira_parte = partes[0]
            eh_unidade_inicial = bool(re.match(
                r"^(?:Apto|Apartamento|Sala|Bloco|Garagem|Conjunto|Conj\.?|Unidade|Loja)\s*\d+[a-zA-Z]?$|^Casa(?:\s*\d+[a-zA-Z]?)?$",
                primeira_parte,
                re.IGNORECASE,
            ))
            # Caso 1: Começa com unidade ('Casa', 'Casa 01', 'Apto 202') e o próximo segmento é a via
            if eh_unidade_inicial:
                if not resultado["complemento_real"]:
                    resultado["complemento_real"] = primeira_parte
                else:
                    resultado["complemento_real"] = f"{primeira_parte}, {resultado['complemento_real']}"
                resto_partes = partes[1:]
                if resto_partes and _RE_INICIO_VIA.match(resto_partes[0]):
                    resultado["logradouro"] = resto_partes[0]
                    resto_partes = resto_partes[1:]
            # Caso 2: Ordem invertida — começou pelo Bairro e o segundo segmento é a via
            # Ex: 'Centro, Rua 3, 45'
            elif (
                len(partes) >= 2
                and not _RE_INICIO_VIA.match(primeira_parte)
                and _RE_INICIO_VIA.match(partes[1])
                and not re.match(r"^(?:n[ºo°\.]?\s*)?\d+", primeira_parte, re.IGNORECASE)
                and not resultado["bairro"]
                and len(primeira_parte) > 2
            ):
                resultado["bairro"] = primeira_parte
                resultado["logradouro"] = partes[1]
                resto_partes = partes[2:]
            else:
                resultado["logradouro"] = primeira_parte
                resto_partes = partes[1:]

            palavras_proibidas_bairro = [
                r"\brua\b", r"\br\.", r"\bav\b", r"\bav\.", r"\blote\b", r"\blt\b",
                r"\bcasa\s+\d+\b", r"\bapto\b", r"\bquadra\b", r"\bqd\b", r"\bfundos\b", r"\bport[aã]o\b"
            ]

            for p in resto_partes:
                p_upper = p.upper()
                if p_upper in MAPA_ESTADOS.values() or p_upper in MAPA_ESTADOS:
                    if not resultado["estado"]:
                        resultado["estado"] = MAPA_ESTADOS.get(p_upper, p_upper)
                    continue

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

        if resultado["logradouro"]:
            eh_rodovia = bool(re.match(r"^(?:Rodovia|Estrada|BR|PA|MG|SP|RJ)\b", resultado["logradouro"], re.IGNORECASE))
            if not eh_rodovia:
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

                if not resultado["numero"] or resultado["logradouro"]:
                    match_num_fim = re.search(r"^(.*?)\s+((?:n[ºo°\.]?\s*)?\d{1,5}(?:-[a-zA-Z0-9]+|[a-zA-Z])?|S\/?N)$", resultado["logradouro"], re.IGNORECASE)
                    if match_num_fim:
                        nome_via = match_num_fim.group(1).strip()
                        if not re.match(r"^(Rua|R\.|Av\.|Avenida|Travessa|Alameda|Passagem)\s+[A-Za-z]?\d{1,4}$", nome_via, re.IGNORECASE):
                            if len(nome_via.split()) >= 2 or not re.match(r"^(?:rua|r\.|avenida|av\.|alameda|travessa|passagem|estrada|rodovia)$", nome_via, re.IGNORECASE):
                                resultado["logradouro"] = nome_via
                                if not resultado["numero"]:
                                    resultado["numero"] = re.sub(r"^n[ºo°\.]?\s*", "", match_num_fim.group(2).strip(), flags=re.IGNORECASE)

        # Aplicação da regra de Lote como número da casa:
        # Se não houve número explícito da casa, Lote vira o número; se já havia número explícito, Lote fica no complemento
        if lote_extraido:
            if not resultado["numero"] or re.fullmatch(r"0+", str(resultado["numero"]).strip()):
                resultado["numero"] = lote_extraido
            else:
                resultado["complemento_real"] = (
                    f"{lote_extraido}, {resultado['complemento_real']}".strip(" ,")
                    if resultado["complemento_real"] else lote_extraido
                )

        # Preserva o nome da via completo quando ele contém palavras comuns
        # como "Quadrante" e não confunde o trecho final com uma unidade ou número.
        if resultado["logradouro"].strip().lower() in {"rua", "r.", "avenida", "av.", "alameda", "travessa", "passagem"}:
            partes_via = locals().get("partes", [])
            if partes_via:
                primeira_via = partes_via[0].strip()
                if _RE_INICIO_VIA.match(primeira_via):
                    resultado["logradouro"] = primeira_via

        # Remover 'Casa de Andar' do final do bairro para não poluir o nome do bairro
        if resultado["bairro"]:
            m_andar = re.search(r"^(.*?)\s*[-–]?\s*\b(casa\s+de\s+andar)\s*$", resultado["bairro"], re.IGNORECASE)
            if m_andar:
                resultado["bairro"] = m_andar.group(1).strip(" ,-")
                obs_andar = m_andar.group(2).strip()
                resultado["complemento_real"] = (
                    f"{resultado['complemento_real']}, {obs_andar}".strip(" ,")
                    if resultado["complemento_real"] else obs_andar
                )

        if not resultado["cidade"] and cidade_padrao:
            resultado["cidade"] = str(cidade_padrao).strip()
        if not resultado["estado"] and estado_padrao:
            resultado["estado"] = str(estado_padrao).strip()

        resultado["logradouro"] = cls.limpar_logradouro_com_base_oficial(
            resultado["logradouro"],
            bairro=resultado["bairro"],
            cidade=resultado["cidade"],
            estado=resultado["estado"],
            texto_original_tinha_virgula=tinha_virgula
        )

        return resultado