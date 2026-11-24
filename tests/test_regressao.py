"""
Testes de regressão do Revisor de Endereços.

Como rodar (na pasta do projeto):   python -m unittest discover -s tests -v
"""
import os, sys, logging, tempfile, unittest
from unittest import mock
import requests, openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.address_parser import AddressParser as P
from src.cep_service import CEPService
from src.excel_processor import ExcelProcessor

logging.disable(logging.CRITICAL)
SEDE = "34006049"
CABECALHO = ["ID_CHAMADO", "BENEFICIARIO_NOME", "BENEFICIARIO_CPF", "BENEFICIARIO_NASCIMENTO", "BENEFICIARIO_TELEFONE",
             "END_CEP", "END_LOGRADOURO", "END_NUMERO", "END_COMPLEMENTO", "END_BAIRRO", "END_CIDADE", "END_ESTADO"]


def linha(nome="Fulano", tel="91980001234", cep="", logr="", num="", comp="", bairro="", cid="", uf=""):
    return [1, nome, "12345678901", None, tel, cep, logr, num, comp, bairro, cid, uf]


class _Resp:
    def __init__(self, code, data): self.status_code, self._d = code, data
    def json(self): return self._d


def api_falsa(url, timeout=None):
    """ViaCEP/BrasilAPI simulados: só conhece 68515000 e 35420100; o resto = rede fora."""
    if "68515000" in url: return _Resp(200, {"cep": "68515-000", "logradouro": "", "bairro": "", "localidade": "Parauapebas", "uf": "PA"})
    if "35420100" in url: return _Resp(200, {"cep": "35420-100", "logradouro": "Rua Direita", "bairro": "Centro", "localidade": "Mariana", "uf": "MG"})
    raise requests.ConnectionError("sem rede")


class PlanilhaBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)

    def processar(self, linhas, cabecalho=CABECALHO, antes=(), cols_texto=(), outras_abas=()):
        wb = openpyxl.Workbook(); ws = wb.active
        for a in antes: ws.append(a)
        ws.append(cabecalho)
        for l in linhas: ws.append(l)
        for (r, c) in cols_texto: ws.cell(row=r, column=c).data_type = "s"   # força string (como num export de sistema)
        for titulo, cab, dados in outras_abas:
            w2 = wb.create_sheet(titulo); w2.append(cab); [w2.append(d) for d in dados]
        ent, sai = os.path.join(self.tmp.name, "in.xlsx"), os.path.join(self.tmp.name, "out.xlsx")
        wb.save(ent)
        with mock.patch("src.cep_service.requests.get", side_effect=api_falsa):
            ok, rev = ExcelProcessor().processar_planilha(ent, sai)
        out = openpyxl.load_workbook(sai)
        return ok, rev, out

    def linha_saida(self, out, n=2):
        ws = out.worksheets[0]
        return dict(zip([c.value for c in ws[1]], [c.value for c in ws[n]]))


# ------------------------------------------------------------------ PARSER
class TestParserFuncionando(unittest.TestCase):
    def test_hifen_antes_do_bairro(self):
        r = P.extrair("Rua A - Centro", "Parauapebas", "PA")
        self.assertEqual((r["logradouro"], r["bairro"]), ("Rua A", "Centro"))

    def test_estado_por_extenso(self):
        self.assertEqual(P.extrair("Rua X, 123, Centro, Parauapebas - Pará", "Parauapebas", "")["estado"], "PA")

    def test_rua_com_nome_de_cidade_no_meio(self):
        r = P.extrair("Rua Mariana Silva, 45, Centro, Mariana - MG")
        self.assertEqual((r["logradouro"], r["cidade"], r["estado"]), ("Rua Mariana Silva", "Mariana", "MG"))

    def test_rodovia_com_hifen(self):
        self.assertEqual(P.extrair("Rodovia PA-275, Km 5, Zona Rural, Curionópolis - PA")["logradouro"], "Rodovia PA-275")

    def test_bairro_nova_marituba_com_virgula(self):
        r = P.extrair("Rua São José, 20, Nova Marituba - PA")
        self.assertEqual((r["logradouro"], r["numero"], r["bairro"], r["cidade"], r["estado"]),
                         ("Rua São José", "20", "Nova Marituba", "Marituba", "PA"))

    def test_bairro_nova_marituba_sem_virgula(self):
        r = P.extrair("Rua São José 20 Nova Marituba - PA")
        self.assertEqual((r["logradouro"], r["numero"], r["bairro"], r["cidade"], r["estado"]),
                         ("Rua São José", "20", "Nova Marituba", "Marituba", "PA"))

    def test_bairro_nova_marituba_e_cidade_marituba(self):
        r = P.extrair("Rua São José, 20, Nova Marituba, Marituba - PA")
        self.assertEqual((r["logradouro"], r["numero"], r["bairro"], r["cidade"], r["estado"]),
                         ("Rua São José", "20", "Nova Marituba", "Marituba", "PA"))


    def test_ruas_com_data_no_nome(self):
        r1 = P.extrair("Rua 7 de Setembro, 100, Centro")
        self.assertEqual((r1["logradouro"], r1["numero"], r1["bairro"]), ("Rua 7 de Setembro", "100", "Centro"))

        r2 = P.extrair("Rua 15 de Novembro, 50, Centro")
        self.assertEqual((r2["logradouro"], r2["numero"], r2["bairro"]), ("Rua 15 de Novembro", "50", "Centro"))

        r3 = P.extrair("Travessa 9 de Janeiro, 5, Umarizal, Belém - PA")
        self.assertEqual((r3["logradouro"], r3["numero"], r3["bairro"], r3["cidade"], r3["estado"]),
                         ("Travessa 9 de Janeiro", "5", "Umarizal", "Belém", "PA"))

    def test_bairros_com_av_no_meio(self):
        r1 = P.extrair("Rua das Palmeiras, 10, Gravata")
        self.assertEqual(r1["bairro"], "Gravata")

        r2 = P.extrair("Rua Principal, 20, Cavalcante")
        self.assertEqual(r2["bairro"], "Cavalcante")

    def test_rua_doutor_mariana(self):
        r = P.extrair("Rua Doutor Mariana, 5, Centro, Belo Horizonte - MG")
        self.assertEqual((r["logradouro"], r["cidade"]), ("Rua Doutor Mariana", "Belo Horizonte"))

    def test_uf_isolada_no_meio_nao_vira_complemento(self):
        r = P.extrair("Rua X, 123 - PA, Centro")
        self.assertEqual(r["complemento_real"], "")


class TestParserBugsAbertos(unittest.TestCase):
    def test_cidade_hifen_uf_nao_vira_complemento(self):
        r = P.extrair("Rua X, 123, Centro - Parauapebas - PA", "Parauapebas", "PA")
        self.assertEqual(r["complemento_real"], "")

    def test_cidade_barra_uf(self):
        r = P.extrair("Rua X, 123, Centro, Parauapebas/PA", "Parauapebas", "PA")
        self.assertEqual(r["bairro"], "Centro")

    def test_numero_com_hifen(self):
        r = P.extrair("Rua X, 123-A, Centro")
        self.assertEqual((r["numero"], r["bairro"]), ("123-A", "Centro"))

    def test_numero_normalizado_sem_prefixo(self):
        self.assertEqual(P.extrair("Rua X, nº 123, Centro")["numero"], "123")

    def test_quadra_com_letra(self):
        r = P.extrair("Rua X, Quadra C, Lote 5, Centro")
        self.assertEqual(r["bairro"], "Centro")

    def test_qd_lt_abreviados(self):
        r = P.extrair("Rua X, Qd 12 Lt 5, Centro")
        self.assertEqual(r["bairro"], "Centro")

    def test_nenhuma_parte_do_texto_e_descartada(self):
        r = P.extrair("Rua X, 123, Centro, Fundos, Portão azul")
        self.assertIn("Portão azul", r["complemento_real"])

    def test_rodovia_com_espaco_nao_separa_numero(self):
        r = P.extrair("Rodovia PA 275, Km 5, Zona Rural, Curionópolis - PA")
        self.assertEqual((r["logradouro"], r["numero"]), ("Rodovia PA 275", ""))

    def test_heuristica_da_sede_usa_palavra_inteira(self):
        for txt in ("Apto 1685", "Sala 359", "3º andar. sala 4", "Garagem 2, bloco Gravata"):
            self.assertFalse(P.eh_endereco_completo(txt, "Rua das Flores", SEDE), txt)

    def test_apto_com_logradouro_vazio_nao_vira_rua(self):
        self.assertNotEqual(P.extrair("Apto 101")["logradouro"], "Apto")


# ------------------------------------------------------------------ CEP
class TestCEPService(unittest.TestCase):
    def test_formatacao_basica(self):
        s = CEPService()
        self.assertEqual(s.formatar_cep(1310100), "01310-100")
        self.assertEqual(s.formatar_cep("35.040-000"), "35040-000")
        self.assertEqual(s.formatar_cep("68515000"), "68515-000")

    def test_circuit_breaker_desliga_apos_3_falhas(self):
        s = CEPService(); chamadas = []
        def get(url, timeout=None): chamadas.append(url); raise requests.ConnectionError("x")
        with mock.patch("src.cep_service.requests.get", side_effect=get):
            for i in range(10): s.consultar_cep(f"9999{i:04d}")
        self.assertEqual(len(chamadas), 6)
        self.assertTrue(s._api_desativada)

    def test_falha_fica_em_cache(self):
        s = CEPService(); chamadas = []
        def get(url, timeout=None): chamadas.append(url); raise requests.ConnectionError("x")
        with mock.patch("src.cep_service.requests.get", side_effect=get):
            s.consultar_cep("99999999"); s.consultar_cep("99999999")
        self.assertEqual(len(chamadas), 2)

    def test_cep_lixo_nao_vira_cep_valido(self):
        for lixo in ("123", "0", "99"):
            self.assertNotRegex(CEPService().formatar_cep(lixo), r"^\d{5}-\d{3}$", lixo)

    def test_tabela_de_cidade_ignora_acento(self):
        s = CEPService()
        self.assertEqual(s.obter_cep_por_cidade("Acailandia", "MA"), "65930-000")
        self.assertEqual(s.obter_cep_por_cidade("Curionopolis", "PA"), "68595-000")


# ------------------------------------------------------------------ PLANILHA (pipeline completo)
class TestPlanilhaFuncionando(PlanilhaBase):
    def test_linha_correta_fica_intacta_e_pronta(self):
        ok, rev, out = self.processar([linha(cep="68515-000", logr="Rua das Flores", num="10", comp="Casa 2", bairro="Centro", cid="Parauapebas", uf="PA")])
        d = self.linha_saida(out)
        self.assertEqual((ok, rev, d["REVISADO_PELO_SCRIPT"], d["END_COMPLEMENTO"]), (1, 0, "NÃO", "Casa 2"))

    def test_cep_explicito_no_complemento_nao_e_sobrescrito(self):
        ok, rev, out = self.processar([linha(cep=SEDE, logr="Rua Sede", num="359", cid="Nova Lima", uf="MG",
                                             comp="Rua Direita, 50, Centro, Mariana - MG, 35420-100")])
        d = self.linha_saida(out)
        self.assertEqual((d["END_CEP"], d["END_LOGRADOURO"], d["END_NUMERO"], d["END_CIDADE"]), ("35420-100", "Rua Direita", "50", "Mariana"))

    def test_cep_com_ponto_e_numerico(self):
        _, _, out = self.processar([linha(cep="35.040-000", logr="Rua A", num="5", cid="Belo Horizonte", uf="MG"),
                                    linha(cep=1310100, logr="Av Paulista", num="1000", cid="São Paulo", uf="SP")])
        self.assertEqual((self.linha_saida(out, 2)["END_CEP"], self.linha_saida(out, 3)["END_CEP"]), ("35040-000", "01310-100"))

    def test_cep_vazio_vai_para_revisao(self):
        ok, rev, _ = self.processar([linha(cep="", logr="Rua A", num="5", cid="Parauapebas", uf="PA")])
        self.assertEqual((ok, rev), (0, 1))

    def test_cabecalho_fora_da_linha_1_da_erro_claro(self):
        with self.assertRaises(ValueError):
            self.processar([linha(cep="68515-000", logr="", comp="Rua X, 1, Centro")], antes=[["Relatório 23/11"]])

    def test_aba_de_dados_depois_da_capa(self):
        wb = openpyxl.Workbook(); wb.active.title = "Capa"; wb.active.append(["Relatório", "x"]); wb.active.append(["a", "b"])
        ws = wb.create_sheet("Chamados"); ws.append(CABECALHO); ws.append(linha(cep="68515-000", logr="Rua A", num="1", cid="Parauapebas", uf="PA"))
        wb.active = 0; ent, sai = os.path.join(self.tmp.name, "m.xlsx"), os.path.join(self.tmp.name, "m_out.xlsx"); wb.save(ent)
        with mock.patch("src.cep_service.requests.get", side_effect=api_falsa):
            self.assertEqual(ExcelProcessor().processar_planilha(ent, sai), (1, 0))

    def test_reprocessar_nao_duplica_coluna_de_auditoria(self):
        _, _, out = self.processar([linha(cep="68515-000", logr="Rua A", num="1", cid="Parauapebas", uf="PA")])
        ent, sai = os.path.join(self.tmp.name, "r_in.xlsx"), os.path.join(self.tmp.name, "r_out.xlsx"); out.save(ent)
        with mock.patch("src.cep_service.requests.get", side_effect=api_falsa):
            ExcelProcessor().processar_planilha(ent, sai)
        cab = [c.value for c in openpyxl.load_workbook(sai).active[1]]
        self.assertEqual(cab.count("REVISADO_PELO_SCRIPT"), 1)

    def test_formula_vira_texto_em_qualquer_coluna(self):
        _, _, out = self.processar([linha(nome='=HYPERLINK("http://x.com","a")', cep="68515-000", logr="Rua A", num="1", cid="Parauapebas", uf="PA")],
                                   cols_texto=[(2, 2)])
        self.assertNotEqual(out.active["B2"].data_type, "f")


class TestPlanilhaBugsAbertos(PlanilhaBase):
    def test_cep_da_sede_em_outra_cidade_vai_para_revisao(self):
        ok, rev, _ = self.processar([linha(cep=SEDE, logr="Rua Sede", num="359", cid="Nova Lima", uf="MG", comp="Rua B, 20, Centro, Marituba - PA")])
        self.assertEqual((ok, rev), (0, 1))

    def test_sede_para_cidade_sem_acento_troca_o_cep(self):
        _, _, out = self.processar([linha(cep=SEDE, logr="Rua Sede", num="359", cid="Nova Lima", uf="MG", comp="Rua C, 30, Centro, Acailandia - MA")])
        self.assertEqual(self.linha_saida(out)["END_CEP"], "65930-000")

    def test_texto_corrido_com_dados_da_sede_nao_fica_pronto(self):
        ok, rev, out = self.processar([linha(cep=SEDE, logr="Rua Sede", num="359", cid="Nova Lima", uf="MG",
                                             comp="Rua Sete de Setembro 123 Centro Parauapebas - PA")])
        d = self.linha_saida(out)
        self.assertEqual((ok, rev, d["END_CEP"], d["END_NUMERO"], d["END_BAIRRO"], d["END_CIDADE"]),
                         (1, 0, "68515-000", "123", "Centro", "Parauapebas"))

    def test_cidade_sem_acento_mantem_cep_especifico(self):
        ok, rev, out = self.processar([linha(cep="35970-123", logr="Rua Principal", num="10", cid="BARAO DE COCAIS", uf="MG",
                                             comp="Rua Principal, 10, Centro, Barão de Cocais - MG")])
        d = self.linha_saida(out)
        self.assertEqual((ok, rev, d["END_CEP"]), (1, 0, "35970-123"))

    def test_passagem_belem_com_sede_vai_para_revisao_se_sem_cep(self):
        ok, rev, out = self.processar([linha(cep=SEDE, logr="Alameda Sede", num="359", cid="Nova Lima", uf="MG",
                                             comp="Passagem São Pedro, 10, Guamá, Belém - PA")])
        # Sem rede para consulta de CEP de Belém, deve ir para revisão com segurança
        self.assertEqual((ok, rev), (0, 1))

    def test_cep_lixo_vai_para_revisao(self):
        ok, rev, _ = self.processar([linha(cep="123", logr="Rua A", num="5", cid="Parauapebas", uf="PA")])
        self.assertEqual((ok, rev), (0, 1))

    def test_colunas_essenciais_sao_obrigatorias(self):
        with self.assertRaises(ValueError):
            self.processar([["x", "68515-000", "Rua X, 1, Centro, Parauapebas - PA"]], cabecalho=["ID", "END_CEP", "END_COMPLEMENTO"])

    def test_complemento_original_e_guardado(self):
        _, _, out = self.processar([linha(cep=SEDE, logr="Rua Sede", num="359", cid="Nova Lima", uf="MG", comp="Sala 359")])
        self.assertIn("COMPLEMENTO_ORIGINAL", [c.value for c in out.active[1]])

    def test_telefone_com_mais_nao_ganha_apostrofo(self):
        _, _, out = self.processar([linha(tel="+55 91 98000-1234", cep="68515-000", logr="Rua A", num="1", cid="Parauapebas", uf="PA")])
        self.assertEqual(self.linha_saida(out)["BENEFICIARIO_TELEFONE"], "+55 91 98000-1234")


if __name__ == "__main__":
    unittest.main(verbosity=2)
