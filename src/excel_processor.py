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

    @staticmethod
    def _sanitizar_valor_excel(val):
        """Evita injeção de fórmulas no Excel se o texto começar com =, +, -, @"""
        if val is None:
            return ""
        s = str(val).strip()
        if s and s[0] in ("=", "+", "-", "@") and not (s[0] == "-" and s[1:].replace(".", "", 1).isdigit()):
            return "'" + s
        return val

    def _localizar_colunas_cabecalho(self, cabecalhos):
        """
        Mapeamento de colunas robusto com correspondência exata priorizada
        e exclusão de falsos positivos (ex: NUMERO_CHAMADO, ESTADO_CIVIL).
        """
        mapa_colunas = {}
        for idx, val in enumerate(cabecalhos):
            if val is not None:
                nome_limpo = self._limpar_nome_cabecalho(val).upper()
                mapa_colunas[nome_limpo] = idx

        def achar_indice(padroes_positivos, palavras_negativas=None):
            palavras_negativas = palavras_negativas or []
            
            # 1. Tentativa de correspondência exata
            for padrao in padroes_positivos:
                for nome, idx in mapa_colunas.items():
                    if nome == padrao.upper():
                        return idx

            # 2. Tentativa por substring com filtro negativo rigoroso
            for padrao in padroes_positivos:
                for nome, idx in mapa_colunas.items():
                    if padrao.upper() in nome:
                        # Se contiver qualquer termo negativo proibido, rejeita
                        if any(neg.upper() in nome for neg in palavras_negativas):
                            continue
                        return idx
            return None

        return {
            "cep": achar_indice(["END_CEP", "CEP_ENDERECO", "CEP"]),
            "num": achar_indice(
                ["END_NUMERO", "NUMERO_END", "NUM_RESIDENCIA", "NUMERO_RESIDENCIAL", "END_NUM", "NUMERO"],
                palavras_negativas=["CHAMADO", "CONTRATO", "TELEFONE", "CPF", "ID", "CARTAO", "DOC", "CIVIL", "PROCESSO"]
            ),
            "comp": achar_indice(
                ["END_COMPLEMENTO", "COMPLEMENTO_END", "COMPLEMENTO"],
                palavras_negativas=["CHAMADO", "PROCESSO"]
            ),
            "logr": achar_indice(
                ["END_LOGRADOURO", "LOGRADOURO", "RUA_ENDERECO", "ENDERECO", "RUA", "AVENIDA"],
                palavras_negativas=["CIVIL", "CHAMADO", "EMPRESA", "CARGO", "NASCIMENTO"]
            ),
            "bairro": achar_indice(
                ["END_BAIRRO", "BAIRRO"],
                palavras_negativas=["CHAMADO", "EMPRESA"]
            ),
            "cidade": achar_indice(
                ["END_CIDADE", "CIDADE", "MUNICIPIO", "LOCALIDADE"],
                palavras_negativas=["NATURALIDADE", "CHAMADO", "EMPRESA"]
            ),
            "estado": achar_indice(
                ["END_ESTADO", "ESTADO", "UF"],
                palavras_negativas=["CIVIL", "NATURALIDADE", "CHAMADO", "EMPRESA"]
            ),
            "nasc": achar_indice(["BENEFICIARIO_NASCIMENTO", "DATA_NASCIMENTO", "NASCIMENTO"]),
            "cpf": achar_indice(["BENEFICIARIO_CPF", "CPF"]),
            "tel": achar_indice(["BENEFICIARIO_TELEFONE", "TELEFONE", "CELULAR"])
        }

    def processar_planilha(self, caminho_arquivo_entrada, caminho_arquivo_saida):
        if not os.path.exists(caminho_arquivo_entrada):
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho_arquivo_entrada}")

        wb_orig = openpyxl.load_workbook(caminho_arquivo_entrada, data_only=True)
        ws_orig = wb_orig.active
        nome_aba = ws_orig.title or "CartaoCorporativo"

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

        # Adicionar coluna de auditoria para o time conferir
        cabecalho_com_auditoria = cabecalho_bruto + ["REVISADO_PELO_SCRIPT"]
        linhas_processadas = [cabecalho_com_auditoria]

        for row in todas_linhas[1:]:
            if not row:
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

            # Se a linha for totalmente vazia, mantém no arquivo e marca como não alterado
            if not any([cep_orig, comp_orig, logr_orig, cidade_orig]):
                linha.append("NÃO")
                linhas_processadas.append(linha)
                continue

            deve_extrair = AddressParser.eh_endereco_completo(comp_orig, logr_orig, cep_orig)
            foi_alterado = False

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

                # Validação ativa de CEP via API (ViaCEP + BrasilAPI) quando extraído do complemento
                if dados_ext["cep"]:
                    dados_api = self.cep_service.consultar_cep(dados_ext["cep"])
                    if dados_api:
                        if not bairro_final and dados_api.get("bairro"):
                            bairro_final = dados_api["bairro"]
                        if not logradouro_final and dados_api.get("logradouro"):
                            logradouro_final = dados_api["logradouro"]
                        if dados_api.get("cidade"):
                            cidade_final = dados_api["cidade"]
                        if dados_api.get("uf"):
                            estado_final = dados_api["uf"]

                # Proteção de CEP: só troca CEP se era o CEP da sede de Nova Lima ou se a cidade mudou para cidade de CEP único
                cep_limpo_orig = cep_orig.replace("-", "").strip()
                cep_cidade = self.cep_service.obter_cep_por_cidade(cidade_final, estado_final)
                if cep_cidade and (cep_limpo_orig == "34006049" or cidade_final.upper() != cidade_orig.upper()):
                    cep_final = cep_cidade

                foi_alterado = True
            else:
                logradouro_final = logr_orig
                numero_final = num_orig
                bairro_final = bairro_orig
                cidade_final = cidade_orig
                estado_final = estado_orig
                cep_final = cep_orig
                complemento_final = comp_orig

            cep_formatado = self.cep_service.formatar_cep(cep_final)

            # Atualizar colunas de endereço no layout original
            if col_logr is not None and col_logr < len(linha):
                linha[col_logr] = self._sanitizar_valor_excel(logradouro_final)
            if col_num is not None and col_num < len(linha):
                linha[col_num] = self._sanitizar_valor_excel(numero_final)
            if col_comp is not None and col_comp < len(linha):
                linha[col_comp] = self._sanitizar_valor_excel(complemento_final)
            if col_bairro is not None and col_bairro < len(linha):
                linha[col_bairro] = self._sanitizar_valor_excel(bairro_final)
            if col_cidade is not None and col_cidade < len(linha):
                linha[col_cidade] = self._sanitizar_valor_excel(cidade_final)
            if col_estado is not None and col_estado < len(linha):
                linha[col_estado] = self._sanitizar_valor_excel(estado_final)
            if col_cep is not None and col_cep < len(linha):
                linha[col_cep] = self._sanitizar_valor_excel(cep_formatado)

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

            linha.append("SIM" if foi_alterado else "NÃO")
            linhas_processadas.append(linha)

            if not logradouro_final or not cidade_final or not estado_final:
                total_revisao += 1
            else:
                total_sucesso += 1

        wb_orig.close()

        # Criar nova pasta de trabalho limpa
        wb_novo = openpyxl.Workbook()
        ws_novo = wb_novo.active
        ws_novo.title = nome_aba

        for r_idx, row_data in enumerate(linhas_processadas, start=1):
            for c_idx, val in enumerate(row_data, start=1):
                ws_novo.cell(row=r_idx, column=c_idx, value=val)

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
                if any(k in nome_col for k in ["CEP", "ESTADO", "UF", "NASCIMENTO", "VIA", "CPF", "TELEFONE", "ID", "REVISADO"]):
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
