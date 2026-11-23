import re
import requests

class CEPService:
    """
    Serviço para consulta e validação de CEP e busca de CEP por Cidade/UF.
    Possui cache em memória para evitar chamadas de rede repetidas.
    """
    def __init__(self):
        self._cache_cep = {}
        self._cache_cidade_cep = {
            ("CURIONÓPOLIS", "PA"): "68595-000",
            ("PARAUAPEBAS", "PA"): "68515-000",
            ("BARÃO DE COCAIS", "MG"): "35970-000",
            ("SANTA BÁRBARA", "MG"): "35960-000",
            ("AÇAILÂNDIA", "MA"): "65930-000",
            ("MARIANA", "MG"): "35420-000",
            ("OURO PRETO", "MG"): "35400-000"
        }

    def formatar_cep(self, cep_str):
        if not cep_str:
            return ""
        numeros = re.sub(r"\D", "", str(cep_str))
        if len(numeros) == 8:
            return f"{numeros[:5]}-{numeros[5:]}"
        return str(cep_str).strip()

    def consultar_cep(self, cep):
        """
        Consulta CEP com redundância dupla:
        1. Cache em memória
        2. ViaCEP
        3. BrasilAPI (fallback se o ViaCEP oscilar)
        """
        cep_limpo = re.sub(r"\D", "", str(cep))
        if len(cep_limpo) != 8:
            return None

        if cep_limpo in self._cache_cep:
            return self._cache_cep[cep_limpo]

        # 1. Tentativa via ViaCEP
        try:
            url_viacep = f"https://viacep.com.br/ws/{cep_limpo}/json/"
            resp = requests.get(url_viacep, timeout=2.5)
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
                    self._cache_cep[cep_limpo] = resultado
                    return resultado
        except Exception:
            pass

        # 2. Fallback via BrasilAPI
        try:
            url_brasilapi = f"https://brasilapi.com.br/api/cep/v1/{cep_limpo}"
            resp = requests.get(url_brasilapi, timeout=2.5)
            if resp.status_code == 200:
                dados = resp.json()
                resultado = {
                    "cep": dados.get("cep"),
                    "logradouro": dados.get("street", ""),
                    "bairro": dados.get("neighborhood", ""),
                    "cidade": dados.get("city", ""),
                    "uf": dados.get("state", "")
                }
                self._cache_cep[cep_limpo] = resultado
                return resultado
        except Exception:
            pass

        return None

    def obter_cep_por_cidade(self, cidade, uf):
        if not cidade or not uf:
            return None
        chave = (cidade.strip().upper(), uf.strip().upper())
        return self._cache_cidade_cep.get(chave)
