import os
import sys
import subprocess
import logging

# Configuração de logging estruturado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AppCartoes")

# Garante que o diretório do script esteja no sys.path mesmo em duplo clique
dir_raiz = os.path.dirname(os.path.abspath(__file__))
if dir_raiz not in sys.path:
    sys.path.insert(0, dir_raiz)

# Auto-instala dependências caso seja a primeira vez no computador do usuário
try:
    import pandas
    import openpyxl
    import requests
except ImportError:
    logger.info("Primeira execução detectada. Instalando dependências...")
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "pandas", "openpyxl", "requests",
        "--quiet", "--no-warn-script-location"
    ])
    import pandas
    import openpyxl
    import requests

import tkinter as tk
from tkinter import filedialog, messagebox

from src.excel_processor import ExcelProcessor

def selecionar_arquivo_interface():
    """Abre uma janela nativa do Windows para selecionar a planilha de entrada.

    Returns:
        str: Caminho absoluto do arquivo selecionado ou string vazia se cancelado.
    """
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    arquivo_selecionado = filedialog.askopenfilename(
        title="Selecione a Planilha de Chamados de Cartão Corporativo",
        filetypes=[("Planilhas Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")]
    )
    root.destroy()
    return arquivo_selecionado

def executar_processamento(arquivo_entrada, arquivo_saida=None):
    """Executa o processamento do Excel e retorna os totais.

    Args:
        arquivo_entrada (str): Caminho da planilha original.
        arquivo_saida (str, opcional): Caminho da planilha de saída.

    Returns:
        tuple[int, int, str]: (sucessos, revisoes, caminho_saida_final)
    """
    if not arquivo_saida:
        dir_origem = os.path.dirname(os.path.abspath(arquivo_entrada))
        nome_base = os.path.splitext(os.path.basename(arquivo_entrada))[0]
        arquivo_saida = os.path.join(dir_origem, f"{nome_base}_REVISADO.xlsx")

    processor = ExcelProcessor()
    total_sucesso, total_revisao = processor.processar_planilha(arquivo_entrada, arquivo_saida)
    return total_sucesso, total_revisao, arquivo_saida

def main():
    """Ponto de entrada interativo da automação com interface do Windows."""
    print("=" * 60)
    print("   AUTOMAÇÃO - EMISSÃO DE CARTÕES CORPORATIVOS (TIME VIAGENS)")
    print("=" * 60)

    # 1. Obter arquivo de entrada
    if len(sys.argv) > 1:
        arquivo_entrada = sys.argv[1]
    else:
        logger.info("Abrindo seletor visual de arquivos...")
        arquivo_entrada = selecionar_arquivo_interface()

    if not arquivo_entrada:
        logger.info("Nenhum arquivo foi selecionado. Operação cancelada.")
        return

    if not os.path.exists(arquivo_entrada):
        msg = f"Arquivo não encontrado: {arquivo_entrada}"
        logger.error(msg)
        return

    logger.info(f"Arquivo selecionado: {os.path.basename(arquivo_entrada)}")
    logger.info("Processando base de chamados e revisando endereços...")

    try:
        total_sucesso, total_revisao, arquivo_saida = executar_processamento(arquivo_entrada)

        print("\n" + "=" * 60)
        print("   RESULTADO DO PROCESSAMENTO")
        print("=" * 60)
        print(f"   [OK] Prontos para Emissão: {total_sucesso} registros")
        print(f"   [!]  Para Revisão Manual : {total_revisao} registros")
        print(f"\n[>] Planilha gerada em:\n    {arquivo_saida}")
        print("=" * 60 + "\n")

        # Pop-up de sucesso
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        mensagem = (
            f"Processamento concluído com sucesso!\n\n"
            f"• Prontos para Emissão: {total_sucesso}\n"
            f"• Para Revisão Manual: {total_revisao}\n\n"
            f"O arquivo revisado foi salvo na mesma pasta:\n{arquivo_saida}"
        )
        messagebox.showinfo("Automação Time Viagens", mensagem)
        root.destroy()

    except PermissionError as e:
        msg_erro = (
            "Não foi possível salvar a planilha revisada porque o arquivo já está aberto no Microsoft Excel.\n\n"
            "👉 Por favor, feche a planilha no Excel e execute a automação novamente."
        )
        logger.error(f"Erro de permissão: {e}")
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showwarning("Arquivo Aberto no Excel", msg_erro)
        root.destroy()

    except FileNotFoundError as e:
        msg_erro = f"Arquivo não encontrado durante o processamento:\n{e}"
        logger.error(msg_erro)
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror("Arquivo Não Encontrado", msg_erro)
        root.destroy()

    except Exception as e:
        msg_erro = f"Ocorreu um erro inesperado durante o processamento:\n{e}"
        logger.exception("Falha durante o processamento da planilha:")
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror("Erro no Processamento", msg_erro)
        root.destroy()

if __name__ == "__main__":
    main()
