import os
import re
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from src.address_parser import AddressParser
from src.cep_service import CEPService

class ExcelProcessor:
    def __init__(self):
        self.cep_service = CEPService()

    @staticmethod
    def _limpar_nome_cabecalho(texto):
        if not texto:
            return ""
        s = str(texto).strip()
        match = re.search(r"\[(.*?)\]", s)
        if match:
            return match.group(1).strip()
        return s

    def _localizar_colunas_cabecalho(self, cabecalhos):
        mapa_colunas = {}
        for idx, val in enumerate(cabecalhos):
            if val is not None:
                nome_limpo = self._limpar_nome_cabecalho(val).upper()
                mapa_colunas[nome_limpo] = idx

        def achar_indice(palavras_chave):
            for nome, idx in mapa_colunas.items():
                for kw in palavras_chave:
                    if kw.upper() in nome:
                        return idx
            return None

        return {
            "cep": achar_indice(["END_CEP", "CEP"]),
            "num": achar_indice(["END_NUMERO", "NUMERO"]),
            "comp": achar_indice(["END_COMPLEMENTO", "COMPLEMENTO"]),
            "logr": achar_indice(["END_LOGRADOURO", "LOGRADOURO", "RUA"]),
            "bairro": achar_indice(["BAIRRO"]),
            "cidade": achar_indice(["CIDADE", "MUNICIPIO"]),
            "estado": achar_indice(["ESTADO", "UF"]),
            "nasc": achar_indice(["NASCIMENTO"]),
            "cpf": achar_indice(["CPF"]),
            "tel": achar_indice(["TELEFONE"])
        }

    def processar_planilha(self, caminho_arquivo_entrada, caminho_arquivo_saida):
        if not os.path.exists(caminho_arquivo_entrada):
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho_arquivo_entrada}")

        # 1. Carregar planilha de entrada (somente leitura de dados para não arrastar tabelas XML corrompidas)
        wb_orig = openpyxl.load_workbook(caminho_arquivo_entrada, data_only=True)
        ws_orig = wb_orig.active
        nome_aba = ws_orig.title or "CartaoCorporativo"

        # Ler todas as linhas brutas
        todas_linhas = list(ws_orig.iter_rows(values_only=True))
        if not todas_linhas:
            return 0, 0

        cabecalho_bruto = [self._limpar_nome_cabecalho(c) for c in todas_linhas[0]]
        cols = self._localizar_colunas_cabecalho(cabecalho_bruto)

        col_cep = cols.get("cep")
        col_num = cols.get("num")
        col_comp = cols.get("comp")
        col_logr = cols.get("logr")
        col_bairro = cols.get("bairro")
        col_cidade = cols.get("cidade")
        col_estado = cols.get("estado")
        col_nasc = cols.get("nasc")
        col_cpf = cols.get("cpf")
        col_tel = cols.get("tel")

        total_sucesso = 0
        total_revisao = 0

        linhas_processadas = [cabecalho_bruto]

        # 2. Processar linhas de dados
        for row in todas_linhas[1:]:
            if not row or not any(row):
                continue

            linha = list(row)

            def get_val(idx):
                if idx is None or idx >= len(linha) or linha[idx] is None:
                    return ""
                return str(linha[idx]).strip()

            cep_orig = get_val(col_cep).replace(".0", "")
            num_orig = get_val(col_num).replace(".0", "")
            comp_orig = get_val(col_comp)
            logr_orig = get_val(col_logr)
            bairro_orig = get_val(col_bairro)
            cidade_orig = get_val(col_cidade)
            estado_orig = get_val(col_estado)

            if not any([cep_orig, comp_orig, logr_orig, cidade_orig]):
                continue

            deve_extrair = AddressParser.eh_endereco_completo(comp_orig, logr_orig, cep_orig)

            if deve_extrair:
                dados_ext = AddressParser.extrair(
                    texto_bruto=comp_orig,
                    cidade_padrao=cidade_orig,
                    estado_padrao=estado_orig,
                    numero_padrao=num_orig
                )

                logradouro_final = dados_ext["logradouro"] or logr_orig
                numero_final = dados_ext["numero"] or num_orig
                bairro_final = dados_ext["bairro"] or bairro_orig
                cidade_final = dados_ext["cidade"] or cidade_orig
                estado_final = dados_ext["estado"] or estado_orig
                cep_final = dados_ext["cep"] or cep_orig
                complemento_final = dados_ext["complemento_real"]

                cep_cidade = self.cep_service.obter_cep_por_cidade(cidade_final, estado_final)
                if cep_cidade and (not dados_ext["cep"] or cidade_final.upper() != cidade_orig.upper()):
                    cep_final = cep_cidade
            else:
                logradouro_final = logr_orig
                numero_final = num_orig
                bairro_final = bairro_orig
                cidade_final = cidade_orig
                estado_final = estado_orig
                cep_final = cep_orig
                complemento_final = comp_orig

            cep_formatado = self.cep_service.formatar_cep(cep_final)

            # Atualizar colunas de endereço
            if col_logr is not None and col_logr < len(linha):
                linha[col_logr] = logradouro_final
            if col_num is not None and col_num < len(linha):
                linha[col_num] = numero_final
            if col_comp is not None and col_comp < len(linha):
                linha[col_comp] = complemento_final
            if col_bairro is not None and col_bairro < len(linha):
                linha[col_bairro] = bairro_final
            if col_cidade is not None and col_cidade < len(linha):
                linha[col_cidade] = cidade_final
            if col_estado is not None and col_estado < len(linha):
                linha[col_estado] = estado_final
            if col_cep is not None and col_cep < len(linha):
                linha[col_cep] = cep_formatado

            # Formatações de CPF, Telefone e Nascimento
            if col_cpf is not None and col_cpf < len(linha):
                cpf_val = get_val(col_cpf).replace(".0", "")
                if cpf_val.isdigit() and len(cpf_val) <= 11:
                    linha[col_cpf] = cpf_val.zfill(11)

            if col_tel is not None and col_tel < len(linha):
                linha[col_tel] = get_val(col_tel).replace(".0", "")

            if col_nasc is not None and col_nasc < len(linha):
                nasc_val = linha[col_nasc]
                if isinstance(nasc_val, datetime):
                    linha[col_nasc] = nasc_val.strftime("%d/%m/%Y")
                elif isinstance(nasc_val, str) and "-" in nasc_val:
                    try:
                        dt = datetime.strptime(nasc_val.split()[0], "%Y-%m-%d")
                        linha[col_nasc] = dt.strftime("%d/%m/%Y")
                    except Exception:
                        pass

            linhas_processadas.append(linha)

            if not logradouro_final or not cidade_final or not estado_final:
                total_revisao += 1
            else:
                total_sucesso += 1

        wb_orig.close()

        # 3. Criar uma nova pasta de trabalho Excel limpa (sem conflitos de XML de tabelas externas)
        wb_novo = openpyxl.Workbook()
        ws_novo = wb_novo.active
        ws_novo.title = nome_aba

        for r_idx, row_data in enumerate(linhas_processadas, start=1):
            for c_idx, val in enumerate(row_data, start=1):
                ws_novo.cell(row=r_idx, column=c_idx, value=val)

        # 4. Aplicar Design Profissional
        self._aplicar_design_profissional(ws_novo)

        os.makedirs(os.path.dirname(os.path.abspath(caminho_arquivo_saida)), exist_ok=True)
        wb_novo.save(caminho_arquivo_saida)
        return total_sucesso, total_revisao

    def _aplicar_design_profissional(self, ws):
        """Aplica tipografia limpa, cores corporativas elegantes e ajuste perfeito de colunas."""
        cor_azul_ibm = "0F62FE"      # Azul IBM Carbon
        cor_fundo_par = "F4F7FB"     # Cinza suave
        cor_borda = "D9D9D9"

        fonte_cabecalho = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        fonte_dados = Font(name="Segoe UI", size=10, color="1F2328")

        fill_cabecalho = PatternFill(start_color=cor_azul_ibm, end_color=cor_azul_ibm, fill_type="solid")
        fill_linha_par = PatternFill(start_color=cor_fundo_par, end_color=cor_fundo_par, fill_type="solid")
        fill_linha_impar = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

        borda_suave = Border(
            left=Side(style='thin', color=cor_borda),
            right=Side(style='thin', color=cor_borda),
            top=Side(style='thin', color=cor_borda),
            bottom=Side(style='thin', color=cor_borda)
        )

        ws.row_dimensions[1].height = 28
        ws.freeze_panes = "A2"

        # Estilizar cabeçalho
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = fonte_cabecalho
            cell.fill = fill_cabecalho
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = borda_suave

        # Estilizar dados
        for row_idx in range(2, ws.max_row + 1):
            ws.row_dimensions[row_idx].height = 20
            fill_atual = fill_linha_par if row_idx % 2 == 0 else fill_linha_impar

            for col_idx in range(1, ws.max_column + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = fonte_dados
                cell.fill = fill_atual
                cell.border = borda_suave

                nome_col = str(ws.cell(row=1, column=col_idx).value or '').upper()
                if any(k in nome_col for k in ["CEP", "ESTADO", "UF", "NASCIMENTO", "VIA", "CPF", "TELEFONE", "ID"]):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif any(k in nome_col for k in ["VALOR", "LIMITE"]):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        # Ajuste de largura das colunas
        for col in ws.columns:
            max_len = 0
            for cell in col:
                val_str = str(cell.value or '')
                if val_str:
                    max_len = max(max_len, len(val_str))
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 4, 14), 48)
