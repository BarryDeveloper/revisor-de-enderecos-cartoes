import logging
import re
import unicodedata
import requests

logger = logging.getLogger("CEPService")

def _remover_acentos(texto):
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(texto))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).strip().upper()

class CEPService:
    """
    Serviço para consulta, validação e padronização de CEP com redundância dupla,
    cache de sucessos/falhas e circuit breaker para ambientes corporativos com proxy.
    """
    def __init__(self):
        self._cache_cep = {}
        self._cache_busca_logradouro = {}
        self._falhas_rede_consecutivas = 0
        self._api_desativada = False
        tabela_base = {
            ("CURIONOPOLIS", "PA"): "68595-000",
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
                    # CEP não existe na base dos Correios: armazena no cache para não consultar de novo
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

    def buscar_cep_por_logradouro(self, uf, cidade, logradouro, bairro=""):
        """
        Busca o CEP nos Correios a partir da UF, Cidade e Nome da Rua.
        Utiliza cache em memória e desambiguação por Bairro quando houver múltiplos resultados.
        """
        if not uf or not cidade or not logradouro:
            return None

        # Limpa o nome do logradouro para a busca no ViaCEP (ex: 'Rua São José' -> 'São José')
        termo_busca = re.sub(r"^(?:rua|r\.|avenida|av\.|alameda|travessa|rodovia|estrada|praca|praça)\s+", "", str(logradouro).strip(), flags=re.IGNORECASE).strip()
        if len(termo_busca) < 3:
            termo_busca = str(logradouro).strip()
            if len(termo_busca) < 3:
                return None

        uf_limpa = str(uf).strip().upper()
        cidade_limpa = str(cidade).strip()
        chave_cache = (uf_limpa, _remover_acentos(cidade_limpa), _remover_acentos(termo_busca), _remover_acentos(bairro))

        if chave_cache in self._cache_busca_logradouro:
            return self._cache_busca_logradouro[chave_cache]

        if self._api_desativada:
            return None

        try:
            url = f"https://viacep.com.br/ws/{uf_limpa}/{cidade_limpa}/{termo_busca}/json/"
            resp = requests.get(url, timeout=2.5)
            if resp.status_code == 200:
                dados = resp.json()
                if isinstance(dados, list) and dados:
                    self._falhas_rede_consecutivas = 0
                    # 1. Se retornou apenas 1 resultado exato nos Correios
                    if len(dados) == 1:
                        cep_encontrado = dados[0].get("cep")
                        self._cache_busca_logradouro[chave_cache] = cep_encontrado
                        return cep_encontrado

                    # 2. Se retornou múltiplos resultados, tenta desambiguar pelo Bairro
                    if bairro:
                        b_norm = _remover_acentos(bairro)
                        candidatos = [
                            d for d in dados
                            if b_norm in _remover_acentos(d.get("bairro", "")) or _remover_acentos(d.get("bairro", "")) in b_norm
                        ]
                        if len(candidatos) == 1:
                            cep_encontrado = candidatos[0].get("cep")
                            self._cache_busca_logradouro[chave_cache] = cep_encontrado
                            return cep_encontrado

                    # Se continuar ambíguo (ruas homônimas em bairros diferentes sem confirmação), não inventa
                    self._cache_busca_logradouro[chave_cache] = None
                    return None
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
