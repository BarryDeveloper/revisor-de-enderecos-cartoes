import logging
import re
import urllib.parse
import unicodedata
import requests

logger = logging.getLogger("CEPService")


def _remover_acentos(texto):
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(texto))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).strip().upper()


def _normalizar_bairro_comparacao(bairro):
    """Normaliza bairro para comparação (acentos, espaços e sufixos como II / LL / 2)."""
    b = _remover_acentos(bairro)
    b = re.sub(r"\s+", " ", b).strip()
    # Trata 'LL' isolado/no fim como algarismo romano 'II'
    b = re.sub(r"\bLL\b", "II", b)
    return b


def _bairros_compativeis(bairro_informado, bairro_api):
    a = _normalizar_bairro_comparacao(bairro_informado)
    p = _normalizar_bairro_comparacao(bairro_api)
    if not a or not p:
        return False
    if a in p or p in a:
        return True
    a_num = re.sub(r"\bII\b", "2", a)
    p_num = re.sub(r"\bII\b", "2", p)
    return a_num in p_num or p_num in a_num


_TIPOS_VIA = {
    "R": "RUA", "RUA": "RUA",
    "AV": "AVENIDA", "AVENIDA": "AVENIDA",
    "AL": "ALAMEDA", "ALAMEDA": "ALAMEDA",
    "TRAV": "TRAVESSA", "TRAVESSA": "TRAVESSA",
    "PASS": "PASSAGEM", "PASSAGEM": "PASSAGEM",
    "VIC": "VICINAL", "VICINAL": "VICINAL",
    "ESTR": "ESTRADA", "ESTRADA": "ESTRADA",
    "ROD": "RODOVIA", "RODOVIA": "RODOVIA",
    "PCA": "PRACA", "PC": "PRACA", "PRACA": "PRACA",
}
_RE_TIPO_VIA = re.compile(r"^(" + "|".join(sorted(_TIPOS_VIA, key=len, reverse=True)) + r")\.?\s+(.+)$")


def _separar_tipo_via(logradouro):
    """Retorna (tipo normalizado, nome normalizado). Tipo vazio se não reconhecido."""
    norm = _remover_acentos(logradouro)
    m = _RE_TIPO_VIA.match(norm)
    if m:
        return _TIPOS_VIA[m.group(1)], m.group(2).strip()
    return "", norm


def _numero_int(numero):
    """Parte numérica inicial do número do imóvel ('123', '123A', '123-B'); None para 'S/N' ou vazio."""
    m = re.match(r"\d+", str(numero or "").strip())
    return int(m.group()) if m else None


def _cobertura_numero(complemento, numero):
    """
    A ViaCEP descreve faixas no campo 'complemento' ('até 653 - lado ímpar', 'de 1701 a 2659 - lado par',
    'de 3202 ao fim') e CEPs de endereços específicos ('867', '1270 2 andar Sala 202').
    Retorna 'exato', 'faixa' ou None.
    """
    comp = _remover_acentos(complemento)
    m = re.match(r"(\d+)(?:\s|$)", comp)
    if m:
        return "exato" if int(m.group(1)) == numero else None
    if "LADO IMPAR" in comp and numero % 2 == 0:
        return None
    if "LADO PAR" in comp and numero % 2 == 1:
        return None
    m = re.search(r"DE (\d+) A (\d+)", comp)
    if m:
        return "faixa" if int(m.group(1)) <= numero <= int(m.group(2)) else None
    m = re.search(r"DE (\d+) AO FIM", comp)
    if m:
        return "faixa" if numero >= int(m.group(1)) else None
    m = re.search(r"ATE (\d+)", comp)
    if m:
        return "faixa" if numero <= int(m.group(1)) else None
    return None


class CEPService:
    """
    Serviço para consulta, validação e padronização de CEP com redundância dupla,
    cache de sucessos/falhas e circuit breaker para ambientes corporativos com proxy.
    """
    def __init__(self):
        self._cache_cep = {}
        self._cache_busca_logradouro = {}
        self._cache_viacep_cidade = {}
        self._cache_municipios = {}
        self._cache_cidade_validada = {}
        self._falhas_rede_consecutivas = 0
        self._api_desativada = False
        tabela_base = {
            ("CURIONOPOLIS", "PA"): "68523-000",
            ("PARAUAPEBAS", "PA"): "68515-000",
            ("BARAO DE COCAIS", "MG"): "35970-000",
            ("SANTA BARBARA", "MG"): "35960-000",
            ("ACAILANDIA", "MA"): "65930-000"
        }
        self._cache_cidade_cep = tabela_base

    def formatar_cep(self, cep_str):
        bruto = "" if cep_str is None else str(cep_str).strip()
        n = re.sub(r"\D", "", re.sub(r"\.0+$", "", bruto))
        if len(n) == 7:
            n = n.zfill(8)
        return f"{n[:5]}-{n[5:]}" if len(n) == 8 else bruto

    def consultar_cep(self, cep):
        """
        Consulta CEP com redundância dupla:
        1. Cache em memória (sucessos e falhas)
        2. Circuit Breaker (desativa chamadas se houver bloqueio de rede/proxy)
        3. ViaCEP
        4. BrasilAPI (fallback se o ViaCEP oscilar)
        """
        cep_limpo = re.sub(r"\D", "", str(cep)).zfill(8)
        if len(cep_limpo) != 8:
            return None

        if cep_limpo in self._cache_cep:
            return self._cache_cep[cep_limpo]

        if self._api_desativada:
            return None

        houve_erro_rede = False

        # 1. Tentativa principal: ViaCEP
        try:
            url_viacep = f"https://viacep.com.br/ws/{cep_limpo}/json/"
            resp = requests.get(url_viacep, timeout=2.0)
            if resp.status_code == 200:
                dados = resp.json()
                if not dados.get("erro"):
                    resultado = {
                        "cep": dados.get("cep"),
                        "logradouro": dados.get("logradouro", ""),
                        "bairro": dados.get("bairro", ""),
                        "cidade": dados.get("localidade", ""),
                        "uf": dados.get("uf", "")
                    }
                    self._falhas_rede_consecutivas = 0
                    self._cache_cep[cep_limpo] = resultado
                    return resultado
                else:
                    self._cache_cep[cep_limpo] = None
                    return None
        except (requests.RequestException, ValueError) as e:
            houve_erro_rede = True
            logger.warning(f"ViaCEP indisponível para CEP {cep_limpo}: {e}. Tentando BrasilAPI...")

        # 2. Fallback: BrasilAPI
        try:
            url_brasilapi = f"https://brasilapi.com.br/api/cep/v1/{cep_limpo}"
            resp = requests.get(url_brasilapi, timeout=2.0)
            if resp.status_code == 200:
                dados = resp.json()
                resultado = {
                    "cep": dados.get("cep"),
                    "logradouro": dados.get("street", ""),
                    "bairro": dados.get("neighborhood", ""),
                    "cidade": dados.get("city", ""),
                    "uf": dados.get("state", "")
                }
                self._falhas_rede_consecutivas = 0
                self._cache_cep[cep_limpo] = resultado
                return resultado
            elif resp.status_code == 404:
                self._cache_cep[cep_limpo] = None
                return None
        except (requests.RequestException, ValueError) as e:
            houve_erro_rede = True
            logger.warning(f"BrasilAPI indisponível para CEP {cep_limpo}: {e}")

        if houve_erro_rede:
            self._falhas_rede_consecutivas += 1
            if self._falhas_rede_consecutivas >= 3:
                self._api_desativada = True
                logger.error("Rede/Proxy corporativo inacessível após 3 tentativas consecutivas. Desativando consultas de API externas.")

        self._cache_cep[cep_limpo] = None
        return None

    def obter_cep_por_cidade(self, cidade, uf):
        if not cidade or not uf:
            return None
        chave = (_remover_acentos(cidade), _remover_acentos(uf))
        return self._cache_cidade_cep.get(chave)

    def _get_json(self, url):
        """
        GET com timeout e circuit breaker compartilhado.
        Retorna None se a API estiver indisponível e [] se ela respondeu 400/404 (sem resultado).
        """
        if self._api_desativada:
            return None
        try:
            resp = requests.get(url, timeout=2.5)
            if resp.status_code == 200:
                self._falhas_rede_consecutivas = 0
                return resp.json()
            if resp.status_code in (400, 404):
                self._falhas_rede_consecutivas = 0
                return []
            return None
        except (requests.RequestException, ValueError) as e:
            self._falhas_rede_consecutivas += 1
            logger.warning(f"API indisponível ({type(e).__name__})")
            if self._falhas_rede_consecutivas >= 3:
                self._api_desativada = True
                logger.error("Rede corporativa inacessível. Desativando consultas de API externas.")
            return None

    @staticmethod
    def _uf_valida(uf):
        uf_limpa = str(uf or "").strip().upper()
        return uf_limpa if re.fullmatch(r"[A-Z]{2}", uf_limpa) else None

    def _dados_viacep_cidade(self, uf, cidade):
        """Consulta ViaCEP por UF + cidade (termo genérico 'Rua'). Retorna lista, ou None se a API não respondeu."""
        uf_limpa = self._uf_valida(uf)
        cidade_limpa = str(cidade or "").strip()
        if not uf_limpa or len(cidade_limpa) < 3:
            return None
        chave = (uf_limpa, _remover_acentos(cidade_limpa))
        if chave in self._cache_viacep_cidade:
            return self._cache_viacep_cidade[chave]
        url = f"https://viacep.com.br/ws/{urllib.parse.quote(uf_limpa, safe='')}/{urllib.parse.quote(cidade_limpa, safe='')}/Rua/json/"
        dados = self._get_json(url)
        if dados is None:
            return None
        lista = dados if isinstance(dados, list) else []
        self._cache_viacep_cidade[chave] = lista
        return lista

    def _municipios_uf(self, uf_limpa):
        """Municípios da UF (BrasilAPI e, na falha, IBGE). Retorna {nome sem acento: nome oficial ou None} ou None."""
        if uf_limpa in self._cache_municipios:
            return self._cache_municipios[uf_limpa]
        fontes = (
            (f"https://brasilapi.com.br/api/ibge/municipios/v1/{uf_limpa}", False),
            (f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf_limpa}/municipios", True),
        )
        for url, nome_confiavel in fontes:
            dados = self._get_json(url)
            if isinstance(dados, list) and dados:
                try:
                    mapa = {_remover_acentos(i["nome"]): (i["nome"] if nome_confiavel else None) for i in dados}
                except (KeyError, TypeError):
                    continue
                self._cache_municipios[uf_limpa] = mapa
                return mapa
        return None

    def validar_cidade(self, uf, cidade):
        """
        Confirma que a cidade existe na UF. Ordem: cache fixo, ViaCEP, BrasilAPI e IBGE (reservas).
        Retorna o nome da cidade (oficial quando a fonte fornece) ou None se não confirmada
        (cidade inexistente ou todas as APIs indisponíveis).
        """
        uf_limpa = self._uf_valida(uf)
        cidade_limpa = str(cidade or "").strip()
        if not uf_limpa or len(cidade_limpa) < 3:
            return None
        cidade_norm = _remover_acentos(cidade_limpa)
        chave = (uf_limpa, cidade_norm)

        if chave in self._cache_cidade_validada:
            return self._cache_cidade_validada[chave]
        if (cidade_norm, uf_limpa) in self._cache_cidade_cep:
            return cidade_limpa

        for item in self._dados_viacep_cidade(uf_limpa, cidade_limpa) or []:
            if _remover_acentos(item.get("localidade", "")) == cidade_norm and str(item.get("uf", "")).upper() == uf_limpa:
                self._cache_cidade_validada[chave] = item["localidade"]
                return item["localidade"]

        municipios = self._municipios_uf(uf_limpa)
        if municipios is None:
            return None
        if cidade_norm in municipios:
            nome = municipios[cidade_norm] or cidade_limpa
            self._cache_cidade_validada[chave] = nome
            return nome
        self._cache_cidade_validada[chave] = None
        return None

    def cidade_inexistente(self, uf, cidade):
        """True somente quando as APIs responderam e a cidade não existe na UF (ex: bairro lido como cidade)."""
        uf_limpa = self._uf_valida(uf)
        chave = (uf_limpa, _remover_acentos(cidade))
        return chave in self._cache_cidade_validada and self._cache_cidade_validada[chave] is None

    @staticmethod
    def mesmo_logradouro(logr_a, logr_b):
        """Mesmo tipo de via (quando ambos informam) e mesmo nome, sem acento e sem abreviação."""
        tipo_a, nome_a = _separar_tipo_via(logr_a)
        tipo_b, nome_b = _separar_tipo_via(logr_b)
        if tipo_a and tipo_b and tipo_a != tipo_b:
            return False
        return bool(nome_a) and nome_a == nome_b

    @staticmethod
    def _escolher_candidato(candidatos, bairro, numero):
        """
        Escolhe um único CEP entre os candidatos de mesma rua. O número da casa (faixas dos Correios)
        vale mais que o bairro digitado, que costuma ser informal; o bairro só desempata.
        """
        if len(candidatos) == 1:
            return candidatos[0]
        if not candidatos:
            return None

        def desempatar(lista):
            if len(lista) == 1:
                return lista[0]
            if bairro:
                por_bairro = [d for d in lista if _bairros_compativeis(bairro, d.get("bairro", ""))]
                if len(por_bairro) == 1:
                    return por_bairro[0]
            return None

        n = _numero_int(numero)
        if n is not None:
            cobertura = [(d, _cobertura_numero(d.get("complemento", ""), n)) for d in candidatos]
            for tipo_alvo in ("exato", "faixa"):
                achados = [d for d, tipo in cobertura if tipo == tipo_alvo]
                if achados:
                    return desempatar(achados)
        return desempatar(candidatos) if bairro else None

    def resolver_cep_endereco(self, uf, cidade, logradouro, bairro="", numero=""):
        """
        Descobre o CEP a partir do endereço (UF, cidade, rua, bairro e número da casa):
        1. Cidade de CEP único (ViaCEP devolve um único registro, sem rua).
        2. Busca por rua, desempatando por bairro e pelas faixas de numeração dos Correios.
        3. Tabela local (só cache), apenas quando a ViaCEP está indisponível.
        """
        cep_unico = self.buscar_cep_unico(uf, cidade)
        if cep_unico:
            return cep_unico
        if self._dados_viacep_cidade(uf, cidade) is None:
            return self.obter_cep_por_cidade(cidade, uf)
        return self.buscar_cep_por_logradouro(uf, cidade, logradouro, bairro, numero)

    def buscar_cep_unico(self, uf, cidade):
        """
        CEP único da cidade via ViaCEP: a cidade tem um único registro, sem logradouro.
        Retorna None se a cidade tem CEPs por rua ou se a API não respondeu.
        """
        lista = self._dados_viacep_cidade(uf, cidade)
        if lista and len(lista) == 1 and not lista[0].get("logradouro"):
            if _remover_acentos(lista[0].get("localidade", "")) == _remover_acentos(cidade):
                return lista[0].get("cep")
        return None

    def buscar_cep_por_logradouro(self, uf, cidade, logradouro, bairro="", numero=""):
        """
        Busca o CEP nos Correios a partir da UF, Cidade e Nome da Rua.
        Utiliza cache em memória e desambiguação por Bairro e número da casa.
        """
        if not uf or not cidade or not logradouro:
            return None

        termo_busca = re.sub(
            r"^(?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|vicinal|vic\.|estrada|estr\.|rodovia|rod\.|praca|praça)\s+",
            "",
            str(logradouro).strip(),
            flags=re.IGNORECASE,
        ).strip()
        if len(termo_busca) < 3:
            termo_busca = str(logradouro).strip()
            if len(termo_busca) < 1:
                return None

        uf_limpa = str(uf).strip().upper()
        cidade_limpa = str(cidade).strip()
        termo_busca_norm = _remover_acentos(termo_busca)
        tipo_busca, _ = _separar_tipo_via(logradouro)
        chave_cache = (
            uf_limpa,
            _remover_acentos(cidade_limpa),
            tipo_busca,
            termo_busca_norm,
            _normalizar_bairro_comparacao(bairro),
            _numero_int(numero),
        )

        if chave_cache in self._cache_busca_logradouro:
            return self._cache_busca_logradouro[chave_cache]

        if self._api_desativada:
            return None

        def _logradouro_bate_estritamente(item_retornado):
            logr_api = item_retornado.get("logradouro", "")
            tipo_api, _ = _separar_tipo_via(logr_api)
            if tipo_busca and tipo_api != tipo_busca:
                return False
            logr_api_core = _remover_acentos(
                re.sub(
                    r"^(?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|vicinal|vic\.|estrada|estr\.|rodovia|rod\.|praca|praça)\s+",
                    "",
                    logr_api,
                    flags=re.IGNORECASE,
                ).strip()
            )
            return termo_busca_norm == logr_api_core or termo_busca_norm == _remover_acentos(logr_api)

        try:
            url_uf = urllib.parse.quote(uf_limpa, safe="")
            url_cid = urllib.parse.quote(cidade_limpa, safe="")
            url_logr = urllib.parse.quote(termo_busca, safe="")
            url = f"https://viacep.com.br/ws/{url_uf}/{url_cid}/{url_logr}/json/"
            resp = requests.get(url, timeout=2.5)
            if resp.status_code == 200:
                dados = resp.json()
                if isinstance(dados, list) and dados:
                    self._falhas_rede_consecutivas = 0

                    candidatos_validos = [d for d in dados if _logradouro_bate_estritamente(d)]
                    if not candidatos_validos and bairro and len(termo_busca_norm) >= 4:
                        candidatos_parciais = [
                            d for d in dados
                            if (not tipo_busca or _separar_tipo_via(d.get("logradouro", ""))[0] == tipo_busca)
                            and termo_busca_norm in _remover_acentos(d.get("logradouro", ""))
                            and _bairros_compativeis(bairro, d.get("bairro", ""))
                        ]
                        escolhido = self._escolher_candidato(candidatos_parciais, bairro, numero)
                    else:
                        escolhido = self._escolher_candidato(candidatos_validos, bairro, numero)

                    cep_encontrado = escolhido.get("cep") if escolhido else None
                    self._cache_busca_logradouro[chave_cache] = cep_encontrado
                    return cep_encontrado
                else:
                    self._cache_busca_logradouro[chave_cache] = None
                    return None
            elif resp.status_code == 400:
                self._cache_busca_logradouro[chave_cache] = None
                return None
        except (requests.RequestException, ValueError) as e:
            self._falhas_rede_consecutivas += 1
            logger.warning(f"Erro na busca de CEP por logradouro ({uf_limpa}/{cidade_limpa}/{termo_busca}): {e}")
            if self._falhas_rede_consecutivas >= 3:
                self._api_desativada = True
                logger.error("Rede corporativa inacessível. Desativando consultas de API externas.")

        self._cache_busca_logradouro[chave_cache] = None
        return None

    def logradouro_ambiguo_na_cidade(self, uf, cidade, logradouro, bairro="", numero=""):
        """
        Retorna True quando o ViaCEP encontrou múltiplos registros para o mesmo logradouro
        na cidade (ex: várias 'Rua 3' em bairros diferentes) e não houve desempate único.
        """
        if not uf or not cidade or not logradouro:
            return False

        termo_busca = re.sub(
            r"^(?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|vicinal|vic\.|estrada|estr\.|rodovia|rod\.|praca|praça)\s+",
            "",
            str(logradouro).strip(),
            flags=re.IGNORECASE,
        ).strip()
        if len(termo_busca) < 1:
            return False

        uf_limpa = str(uf).strip().upper()
        cidade_limpa = str(cidade).strip()
        termo_busca_norm = _remover_acentos(termo_busca)
        tipo_busca, _ = _separar_tipo_via(logradouro)
        chave_cache = (
            uf_limpa,
            _remover_acentos(cidade_limpa),
            tipo_busca,
            termo_busca_norm,
            _normalizar_bairro_comparacao(bairro),
            _numero_int(numero),
        )

        if chave_cache in self._cache_busca_logradouro and self._cache_busca_logradouro[chave_cache] is not None:
            return False

        if self._api_desativada:
            return False

        try:
            url_uf = urllib.parse.quote(uf_limpa, safe="")
            url_cid = urllib.parse.quote(cidade_limpa, safe="")
            url_logr = urllib.parse.quote(termo_busca, safe="")
            url = f"https://viacep.com.br/ws/{url_uf}/{url_cid}/{url_logr}/json/"
            resp = requests.get(url, timeout=2.5)
            if resp.status_code == 200:
                dados = resp.json()
                if isinstance(dados, list):
                    mesmo_nome = [
                        d for d in dados
                        if (not tipo_busca or _separar_tipo_via(d.get("logradouro", ""))[0] == tipo_busca)
                        and (
                            termo_busca_norm
                            == _remover_acentos(
                                re.sub(
                                    r"^(?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|vicinal|vic\.|estrada|estr\.|rodovia|rod\.|praca|praça)\s+",
                                    "",
                                    d.get("logradouro", ""),
                                    flags=re.IGNORECASE,
                                ).strip()
                            )
                            or termo_busca_norm == _remover_acentos(d.get("logradouro", ""))
                        )
                    ]
                    return len(mesmo_nome) > 1
        except (requests.RequestException, ValueError):
            return False

        return False

    def sugerir_via_parecida(self, uf, cidade, logradouro, textos_extras=()):
        """
        Só para o motivo de revisão: se existir um ÚNICO logradouro com o mesmo nome (tipo de via
        diferente), devolve (logradouro, bairro, cep, bairro_aparece_no_texto). Nunca é usado como CEP.
        """
        uf_limpa = self._uf_valida(uf)
        cidade_limpa = str(cidade or "").strip()
        _, nome = _separar_tipo_via(logradouro)
        if not uf_limpa or len(cidade_limpa) < 3 or len(nome) < 3:
            return None
        termo = re.sub(
            r"^(?:rua|r\.|avenida|av\.|alameda|al\.|travessa|trav\.|passagem|pass\.|vicinal|vic\.|estrada|estr\.|rodovia|rod\.|praca|praça)\s+",
            "",
            str(logradouro).strip(),
            flags=re.IGNORECASE,
        ).strip()
        url = (
            f"https://viacep.com.br/ws/{urllib.parse.quote(uf_limpa, safe='')}/"
            f"{urllib.parse.quote(cidade_limpa, safe='')}/{urllib.parse.quote(termo, safe='')}/json/"
        )
        dados = self._get_json(url)
        if not isinstance(dados, list):
            return None
        mesmos = [d for d in dados if _separar_tipo_via(d.get("logradouro", ""))[1] == nome]
        if len(mesmos) != 1:
            return None
        item = mesmos[0]
        bairro_norm = _normalizar_bairro_comparacao(item.get("bairro", ""))
        no_texto = bool(bairro_norm) and any(bairro_norm in _normalizar_bairro_comparacao(t) for t in textos_extras)
        return item.get("logradouro"), item.get("bairro"), item.get("cep"), no_texto