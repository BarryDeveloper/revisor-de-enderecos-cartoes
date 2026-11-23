import os
import sys
import subprocess

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
    """Abre uma janela nativa do Windows para selecionar a planilha de entrada."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    arquivo_selecionado = filedialog.askopenfilename(
        title="Selecione a Planilha de Chamados de Cartão Corporativo",
        filetypes=[("Planilhas Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")]
    )
    root.destroy()
    return arquivo_selecionado

def main():
    print("=" * 60)
    print("   AUTOMAÇÃO - EMISSÃO DE CARTÕES CORPORATIVOS (TIME VIAGENS)")
    print("=" * 60)

    # 1. Definir arquivo de entrada (via argumento CLI ou via Seletor de Arquivos)
    if len(sys.argv) > 1:
        arquivo_entrada = sys.argv[1]
    else:
        print("\n[+] Abrindo seletor de arquivo...")
        arquivo_entrada = selecionar_arquivo_interface()

    if not arquivo_entrada:
        print("[!] Nenhum arquivo foi selecionado. Operação cancelada.")
        return

    if not os.path.exists(arquivo_entrada):
        print(f"[X] Erro: Arquivo não encontrado: {arquivo_entrada}")
        return

    # 2. Salva o arquivo REVISADO na mesma pasta de onde veio o arquivo original
    dir_origem = os.path.dirname(os.path.abspath(arquivo_entrada))
    nome_base = os.path.splitext(os.path.basename(arquivo_entrada))[0]
    arquivo_saida = os.path.join(dir_origem, f"{nome_base}_REVISADO.xlsx")

    print(f"\n[+] Arquivo selecionado: {arquivo_entrada}")
    print("[+] Processando base de chamados e revisando endereços...")

    try:
        processor = ExcelProcessor()
        total_sucesso, total_revisao = processor.processar_planilha(arquivo_entrada, arquivo_saida)

        print("\n" + "=" * 60)
        print("   RESULTADO DO PROCESSAMENTO")
        print("=" * 60)
        print(f"   [OK] Prontos para Emissão: {total_sucesso} registros")
        print(f"   [!]  Para Revisão Manual : {total_revisao} registros")
        print(f"\n[>] Planilha gerada em:\n    {arquivo_saida}")
        print("=" * 60 + "\n")

        # Exibir pop-up nativo de sucesso para facilitar o uso visual
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

    except Exception as e:
        print(f"\n[X] Ocorreu um erro durante o processamento: {e}")
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror("Erro no Processamento", f"Não foi possível processar a planilha:\n{e}")
        root.destroy()

if __name__ == "__main__":
    main()
