import unittest
from src.address_parser import AddressParser
from src.cep_service import CEPService

class TestAddressParser(unittest.TestCase):

    def test_item1_preservacao_nomes_ruas_com_termos_comuns(self):
        """Item 1: Ruas que contêm 'Casa', 'Liberdade', 'Esperança', 'Centro', 'Doutor' não devem ser truncadas."""
        casos = [
            ("Rua da Liberdade, 10, Bairro Liberdade", "Rua da Liberdade"),
            ("Rua da Casa Branca, 20, Centro", "Rua da Casa Branca"),
            ("Rua Nova Esperança, 30, Bairro Esperança", "Rua Nova Esperança"),
            ("Rua Principal do Centro, 40, Bairro Centro", "Rua Principal do Centro"),
            ("Rua Doutor Parauapebas, 50, Parauapebas - PA", "Rua Doutor Parauapebas")
        ]
        for texto, esperado in casos:
            res = AddressParser.extrair(texto)
            self.assertEqual(res["logradouro"], esperado, f"Falha para texto: '{texto}'")

    def test_item2_complemento_comum_escritorio_nao_sobrescreve_logradouro(self):
        """Item 2: Complementos como 'Sala 3 - Escritório' não devem acionar detecção de estado (ES) nem sobrescrever."""
        self.assertFalse(
            AddressParser.eh_endereco_completo("Sala 3 - Escritório", logradouro_atual="Rua das Flores"),
            "Sala 3 - Escritório não deveria ser detectado como endereço completo"
        )
        self.assertFalse(
            AddressParser.eh_endereco_completo("Pavilhão 2 - Pavimento Superior", logradouro_atual="Avenida Central"),
            "Pavilhão não deveria acionar detecção"
        )

    def test_item3_reconhecimento_numeros_e_bairros(self):
        """Item 3: Reconhecer S/N, nº 123, 123A e não confundir 'Quadrante' com 'Quadra'."""
        # S/N
        r1 = AddressParser.extrair("Rua X, S/N, Centro")
        self.assertEqual(r1["logradouro"], "Rua X")
        self.assertEqual(r1["numero"], "S/N")
        self.assertEqual(r1["bairro"], "Centro")

        # nº 123
        r2 = AddressParser.extrair("Rua X, nº 123, Centro")
        self.assertEqual(r2["logradouro"], "Rua X")
        self.assertEqual(r2["numero"], "123")
        self.assertEqual(r2["bairro"], "Centro")

        # 123A
        r3 = AddressParser.extrair("Rua X, 123A, Centro")
        self.assertEqual(r3["logradouro"], "Rua X")
        self.assertEqual(r3["numero"], "123A")
        self.assertEqual(r3["bairro"], "Centro")

        # Rua Quadrante (não casar com regex Quadra)
        r4 = AddressParser.extrair("Rua Quadrante, 100, Centro")
        self.assertEqual(r4["logradouro"], "Rua Quadrante")
        self.assertEqual(r4["numero"], "100")
        self.assertEqual(r4["bairro"], "Centro")

    def test_item6_abreviacoes_r_e_av_e_ceps_com_pontuacao(self):
        """Item 6: Reconhecer Av., R., CEPs pontuados (68.515-000) e prefixo 'CEP'."""
        self.assertTrue(AddressParser.eh_endereco_completo("Av. Brasil, 100, Centro"))
        self.assertTrue(AddressParser.eh_endereco_completo("R. Sete de Setembro, 200, Centro"))

        r1 = AddressParser.extrair("Rua Minas Gerais, 100, CEP 68.515-000")
        self.assertEqual(r1["cep"], "68515000")
        self.assertEqual(r1["complemento_real"], "")

        r2 = AddressParser.extrair("Rua Bahia, 50, CEP: 68515000")
        self.assertEqual(r2["cep"], "68515000")
        self.assertEqual(r2["complemento_real"], "")

    def test_cep_service_formatacao_e_circuit_breaker(self):
        """Valida que o CEPService formata corretamente com 8 dígitos e não quebra com zeros à esquerda."""
        service = CEPService()
        self.assertEqual(service.formatar_cep("1310100"), "01310-100")
        self.assertEqual(service.formatar_cep("35040000"), "35040-000")
        self.assertEqual(service.formatar_cep("68515-000"), "68515-000")

    def test_buscar_cep_por_logradouro_mock(self):
        """Valida busca reversa de CEP por logradouro com desambiguação por bairro."""
        from unittest import mock
        service = CEPService()
        
        # 1. Caso com 1 resultado exato
        resp_mock = mock.MagicMock()
        resp_mock.status_code = 200
        resp_mock.json.return_value = [{"cep": "67200-100", "logradouro": "Rua B", "bairro": "Centro"}]
        with mock.patch("requests.get", return_value=resp_mock):
            cep = service.buscar_cep_por_logradouro("PA", "Marituba", "Rua B", "Centro")
            self.assertEqual(cep, "67200-100")

        # 2. Caso com múltiplos resultados desambiguados pelo bairro
        resp_multi = mock.MagicMock()
        resp_multi.status_code = 200
        resp_multi.json.return_value = [
            {"cep": "67200-010", "logradouro": "Rua São José", "bairro": "Decouville"},
            {"cep": "67200-020", "logradouro": "Rua São José", "bairro": "Centro"}
        ]
        with mock.patch("requests.get", return_value=resp_multi):
            cep = service.buscar_cep_por_logradouro("PA", "Marituba", "Rua São José", "Centro")
            self.assertEqual(cep, "67200-020")

if __name__ == "__main__":
    unittest.main()
