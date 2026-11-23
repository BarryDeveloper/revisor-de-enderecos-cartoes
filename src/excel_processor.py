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
    def _remover_acentos_str(texto):
        if not texto:
            return ""
        import unicodedata
        nfkd = unicodedata.normalize('NFKD', str(texto))
        return "".join([c for c in nfkd if not unicodedata.combining(c)])

    @classmethod
    def _limpar_nome_cabecalho(cls, texto):
        if not texto:
            return ""
        s = str(texto).strip()
        match = re.search(r"\[(.*?)\]", s)
        if match:
            s = match.group(1).strip()
        # Remove sufixos automáticos do Excel como .1, .2
        s = re.sub(r"\.\d+$", "", s)
        return cls._remover_acentos_str(s).upper()

    @staticmethod
    def _sanitizar_valor_excel(val):
        """Evita injeção de fórmulas no Excel (células começando com =)"""
        if val is None:
            return ""
        s = str(val).strip()
        if s and s.startswith("="):
            return "'" + s
        return val

    def _localizar_colunas_cabecalho(self, cabecalhos):
        """
        Mapeamento de colunas robusto, flexível e imune a formatações do Excel
        (ex: Tabela[END_LOGRADOURO.1], Tabela[BAIRRO], [CIDADE], [ESTADO]).
        """
        mapa_colunas = {}
        for idx, val in enumerate(cabecalhos):
            if val is not None:
                nome_limpo = self._limpar_nome_cabecalho(val)
                nome_norm = re.sub(r"[\s\.\-\/]+", "_", nome_limpo).strip("_")
                mapa_colunas[nome_norm] = idx
                mapa_colunas[nome_limpo] = idx

        def achar_indice(padroes_positivos, palavras_negativas=None):
            palavras_negativas = [self._limpar_nome_cabecalho(p) for p in (palavras_negativas or [])]
            padroes_norm = [self._limpar_nome_cabecalho(p) for p in padroes_positivos]

            # 1. Tentativa de correspondência exata
            for padrao in padroes_norm:
                for nome, idx in mapa_colunas.items():
                    if nome == padrao:
                        return idx

            # 2. Tentativa por token/limite de palavra
            for padrao in padroes_norm:
                for nome, idx in mapa_colunas.items():
                    if any(re.search(rf"(?:^|_){re.escape(neg)}(?:_|$)", nome) for neg in palavras_negativas):
                        continue
                    if re.search(rf"(?:^|_){re.escape(padrao)}(?:_|$)", nome):
                        return idx
            return None

        return {
            "cep": achar_indice(["END_CEP", "CEP_ENDERECO", "CEP_RESIDENCIAL", "CEP", "ENDERECO_CEP"], palavras_negativas=["RECEPCAO", "PROTOCOLO"]),
            "num": achar_indice(
                ["END_NUMERO", "NUMERO_END", "NUM_RESIDENCIA", "NUMERO_RESIDENCIAL", "END_NUM", "NUMERO", "NUM"],
                palavras_negativas=["CHAMADO", "CONTRATO", "TELEFONE", "CPF", "ID", "CARTAO", "DOC", "CIVIL", "PROCESSO"]
            ),
            "comp": achar_indice(
                ["END_COMPLEMENTO", "COMPLEMENTO_END", "COMPLEMENTO", "END_COMPL", "COMPL"],
                palavras_negativas=["CHAMADO", "PROCESSO"]
            ),
            "logr": achar_indice(
                ["END_LOGRADOURO", "LOGRADOURO", "RUA_ENDERECO", "ENDERECO", "RUA", "AVENIDA", "END_RUA"],
                palavras_negativas=["CIVIL", "CHAMADO", "EMPRESA", "CARGO", "NASCIMENTO"]
            ),
            "bairro": achar_indice(
                ["END_BAIRRO", "BAIRRO", "ENDERECO_BAIRRO"],
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

        # Localizar a aba correta que contenha os dados de cartões
        ws_orig = None
        cols = None
        todas_linhas = []
        cabecalho_bruto = []

        for sheet in wb_orig.worksheets:
            linhas = list(sheet.iter_rows(values_only=True))
            if linhas and len(linhas) > 1:
                cab = [self._limpar_nome_cabecalho(c) for c in linhas[0]]
                c_map = self._localizar_colunas_cabecalho(cab)
                colunas_obrigatorias = ["cep", "logr", "num", "comp", "bairro", "cidade", "estado"]
                if all(c_map.get(k) is not None for k in colunas_obrigatorias):
                    ws_orig = sheet
                    cols = c_map
                    todas_linhas = linhas
                    cabecalho_bruto = list(linhas[0])
                    break

        if ws_orig is None or not todas_linhas:
            wb_orig.close()
            raise ValueError("Não foi encontrada nenhuma aba válida contendo todas as 7 colunas obrigatórias de endereço (END_CEP, END_LOGRADOURO, END_NUMERO, END_COMPLEMENTO, END_BAIRRO, END_CIDADE, END_ESTADO).")

        nome_aba = ws_orig.title or "CartaoCorporativo"

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

        # Tratar colunas de backup e auditoria (evita duplicação se reprocessado)
        cab_upper = [str(c).upper() for c in cabecalho_bruto]
        colunas_adicionar = []
        if "LOGRADOURO_ORIGINAL" not in cab_upper:
            colunas_adicionar.append("LOGRADOURO_ORIGINAL")
        if "COMPLEMENTO_ORIGINAL" not in cab_upper:
            colunas_adicionar.append("COMPLEMENTO_ORIGINAL")
        if "REVISADO_PELO_SCRIPT" not in cab_upper:
            colunas_adicionar.append("REVISADO_PELO_SCRIPT")

        cabecalho_com_auditoria = list(cabecalho_bruto) + colunas_adicionar
        idx_auditoria = cabecalho_com_auditoria.index("REVISADO_PELO_SCRIPT")

        linhas_processadas = [cabecalho_com_auditoria]

        for row in todas_linhas[1:]:
            if not row:
                continue

            linha = list(row)
            while len(linha) < len(cabecalho_com_auditoria):
                linha.append("")

            def get_val(idx):
                if idx is None or idx >= len(linha) or linha[idx] is None:
                    return ""
                v = str(linha[idx]).strip()
                return re.sub(r"\.0$", "", v)

            cep_orig = get_val(col_cep)
            num_orig = get_val(col_num)
            comp_orig = get_val(col_comp)
            logr_orig = get_val(col_logr)
            bairro_orig = get_val(col_bairro)
            cidade_orig = get_val(col_cidade)
            estado_orig = get_val(col_estado)

            # Se a linha for totalmente vazia, mantém intacta
            if not any([cep_orig, comp_orig, logr_orig, cidade_orig]):
                linha[idx_auditoria] = "NÃO"
                linhas_processadas.append(linha)
                continue

            deve_extrair = AddressParser.eh_endereco_completo(comp_orig, logr_orig, cep_orig)
            logradouro_final = logr_orig
            numero_final = num_orig
            bairro_final = bairro_orig
            cidade_final = cidade_orig
            estado_final = estado_orig
            cep_final = cep_orig
            complemento_final = comp_orig

            if deve_extrair:
                dados_ext = AddressParser.extrair(
                    texto_bruto=comp_orig,
                    cidade_padrao=cidade_orig,
                    estado_padrao=estado_orig,
                    numero_padrao=num_orig
                )

                logradouro_final = dados_ext["logradouro"] or logr_orig
                cidade_final = dados_ext["cidade"] or cidade_orig
                estado_final = dados_ext["estado"] or estado_orig
                bairro_final = dados_ext["bairro"] or bairro_orig
                cep_final = dados_ext["cep"] or cep_orig
                complemento_final = dados_ext["complemento_real"]

                # Tratamento de número com proteção da sede:
                # Se o número não foi encontrado no texto, só herda o número de cadastro se NÃO for da sede
                cep_limpo_orig = re.sub(r"\D", "", cep_orig)
                if dados_ext["numero"]:
                    numero_final = dados_ext["numero"]
                else:
                    if cep_limpo_orig == "34006049":
                        numero_final = ""
                    else:
                        numero_final = num_orig

                # Validação de CEP via API quando extraído do complemento
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

                # Proteção de CEP: só busca CEP único da cidade se NÃO havia CEP explícito no complemento
                cep_limpo_orig = re.sub(r"\D", "", cep_orig)
                if not dados_ext["cep"]:
                    cep_cidade = self.cep_service.obter_cep_por_cidade(cidade_final, estado_final)
                    if cep_cidade and (cep_limpo_orig == "34006049" or cidade_final.upper() != cidade_orig.upper()):
                        cep_final = cep_cidade
                    elif cep_limpo_orig == "34006049" or cidade_final.upper() != cidade_orig.upper():
                        # Busca reversa nos Correios por Logradouro + Cidade + UF
                        cep_logr = self.cep_service.buscar_cep_por_logradouro(estado_final, cidade_final, logradouro_final, bairro_final)
                        if cep_logr:
                            cep_final = cep_logr

            cep_formatado = self.cep_service.formatar_cep(cep_final)

            # Atualizar colunas de endereço no layout original
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
                cpf_val = get_val(col_cpf)
                cpf_digits = re.sub(r"\D", "", cpf_val)
                if cpf_digits and len(cpf_digits) <= 11:
                    linha[col_cpf] = cpf_digits.zfill(11)

            if col_tel is not None and col_tel < len(linha):
                linha[col_tel] = get_val(col_tel)

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

            # Auditoria precisa: verifica se algum campo de endereço de fato mudou
            mudou_endereco = (
                logradouro_final != logr_orig or
                numero_final != num_orig or
                complemento_final != comp_orig or
                bairro_final != bairro_orig or
                cidade_final != cidade_orig or
                estado_final != estado_orig or
                cep_formatado != self.cep_service.formatar_cep(cep_orig)
            )

            if "LOGRADOURO_ORIGINAL" in colunas_adicionar:
                idx_logr_orig = cabecalho_com_auditoria.index("LOGRADOURO_ORIGINAL")
                linha[idx_logr_orig] = logr_orig
            if "COMPLEMENTO_ORIGINAL" in colunas_adicionar:
                idx_comp_orig = cabecalho_com_auditoria.index("COMPLEMENTO_ORIGINAL")
                linha[idx_comp_orig] = comp_orig

            linha[idx_auditoria] = "SIM" if mudou_endereco else "NÃO"
            linhas_processadas.append(linha)

            # Critério rigoroso de 'Pronto para Emissão':
            # 1. Precisa de CEP formatado com 8 dígitos (00000-000)
            tem_cep_valido = bool(re.match(r"^\d{5}-\d{3}$", str(cep_formatado)))
            # 2. Número presente
            tem_numero = bool(str(numero_final).strip())
            # 3. Logradouro válido (não genérico)
            tem_logradouro = bool(str(logradouro_final).strip() and not re.match(r"^(?:rua|r\.|avenida|av\.|sala|apto)$", str(logradouro_final).strip(), re.IGNORECASE))
            # 4. Cidade e UF válidos
            tem_cidade = bool(str(cidade_final).strip())
            tem_uf = bool(str(estado_final).strip() and len(str(estado_final).strip()) == 2)

            # 5. Trava da Sede: Se o CEP for da Sede (34006-049) e a cidade não for Nova Lima, vai para revisão!
            cep_limpo_check = re.sub(r"\D", "", str(cep_formatado))
            cidade_norm_check = re.sub(r"\s+", " ", str(cidade_final)).strip().upper()
            sede_invalida = (cep_limpo_check == "34006049" and cidade_norm_check not in ("NOVA LIMA", ""))

            # 6. Se o número da sede (359) permaneceu mas a cidade foi alterada para outra sem número extraído do texto
            num_sede_suspeito = (str(num_orig).strip() == "359" and str(numero_final).strip() == "359" and cidade_norm_check not in ("NOVA LIMA", ""))

            if tem_cep_valido and tem_numero and tem_logradouro and tem_cidade and tem_uf and not sede_invalida and not num_sede_suspeito:
                total_sucesso += 1
            else:
                total_revisao += 1

        wb_orig.close()

        # Criar nova pasta de trabalho limpa e sanitizada
        wb_novo = openpyxl.Workbook()
        ws_novo = wb_novo.active
        ws_novo.title = nome_aba

        for r_idx, row_data in enumerate(linhas_processadas, start=1):
            for c_idx, val in enumerate(row_data, start=1):
                # Sanitização anti-fórmula em todas as células gravadas
                val_sanitizado = self._sanitizar_valor_excel(val)
                ws_novo.cell(row=r_idx, column=c_idx, value=val_sanitizado)

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
