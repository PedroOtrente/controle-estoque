"""
Gera a planilha base ControleEstoque.xlsx (sem macros).

Depois de gerada, importe ControleEstoque.bas no Excel (Alt+F11 > Arquivo >
Importar arquivo) e salve como .xlsm. Passo a passo na aba "Como usar".

Uso: python gerar_planilha.py [--vazia]
"""

import os
import sys

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

VERDE = PatternFill("solid", fgColor="1F6B4A")
VERMELHO = PatternFill("solid", fgColor="FDECEA")
AMARELO = PatternFill("solid", fgColor="FDF3E0")
BRANCO_NEGRITO = Font(bold=True, color="FFFFFF")

LINHAS_FORMULA = 300


def cabecalho(ws, colunas, larguras):
    ws.append(colunas)
    for i, largura in enumerate(larguras, start=1):
        c = ws.cell(1, i)
        c.fill = VERDE
        c.font = BRANCO_NEGRITO
        c.alignment = Alignment(vertical="center")
        ws.column_dimensions[c.column_letter].width = largura
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"


def montar(vazia=False):
    wb = Workbook()

    # ------------------------------------------------------------ Como usar
    ws = wb.active
    ws.title = "Como usar"
    ws.column_dimensions["A"].width = 100
    passos = [
        ("Controle de Estoque com baixa automática", True),
        ("", False),
        ("Ativar as macros (uma vez só)", True),
        ("1. Abra esta planilha no Excel e pressione Alt+F11.", False),
        ("2. Menu Arquivo > Importar arquivo… e escolha ControleEstoque.bas.", False),
        ("3. Feche o editor e salve como 'Pasta de Trabalho Habilitada para Macro (*.xlsm)'.", False),
        ("4. Opcional: Inserir > Formas, desenhe botões e use 'Atribuir macro'.", False),
        ("", False),
        ("Uso no dia a dia", True),
        ("Insumos: cadastre a matéria-prima, unidade, estoque atual, mínimo e custo. A coluna Situação é automática.", False),
        ("Fichas: uma linha por insumo de cada prato, com quanto o prato consome por unidade vendida.", False),
        ("Vendas: cole o relatório do PDV (código, produto, quantidade, data). Deixe Status em branco.", False),
        ("Alt+F8 > ProcessarVendas: dá baixa nos insumos de cada venda e preenche o Status.", False),
        ("Alt+F8 > GerarListaCompras: monta a aba Compras com o que está abaixo do mínimo.", False),
        ("Alt+F8 > RegistrarEntrada / RegistrarPerda: lança recebimento ou descarte.", False),
        ("Movimentacoes: histórico de tudo que alterou o estoque. Não edite à mão.", False),
    ]
    for texto, negrito in passos:
        ws.append([texto])
        ws.cell(ws.max_row, 1).font = Font(bold=negrito, size=14 if ws.max_row == 1 else 11)
        ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True)

    # --------------------------------------------------------------- Insumos
    wi = wb.create_sheet("Insumos")
    cabecalho(wi, ["Insumo", "Unidade", "Estoque atual", "Mínimo", "Custo (R$)", "Situação"],
              [28, 10, 15, 12, 13, 12])
    dv = DataValidation(type="list", formula1='"kg,g,L,ml,un"', allow_blank=True)
    wi.add_data_validation(dv)
    dv.add(f"B2:B{LINHAS_FORMULA}")
    for r in range(2, LINHAS_FORMULA + 1):
        wi.cell(r, 6).value = f'=IF(A{r}="","",IF(C{r}<=0,"ZERADO",IF(C{r}<D{r},"REPOR","OK")))'
        wi.cell(r, 5).number_format = '"R$" #,##0.00'
        wi.cell(r, 3).number_format = "0.000"
        wi.cell(r, 4).number_format = "0.000"
    wi.conditional_formatting.add(
        f"A2:F{LINHAS_FORMULA}",
        FormulaRule(formula=['OR($F2="REPOR",$F2="ZERADO")'], fill=VERMELHO),
    )

    # ---------------------------------------------------------------- Fichas
    wf = wb.create_sheet("Fichas")
    cabecalho(wf, ["Código PDV", "Produto", "Insumo", "Qtd por unidade"], [13, 28, 28, 16])

    # ---------------------------------------------------------------- Vendas
    wv = wb.create_sheet("Vendas")
    cabecalho(wv, ["Código PDV", "Produto", "Quantidade", "Data", "Status"], [13, 28, 12, 18, 44])
    wv.conditional_formatting.add(
        f"A2:E{LINHAS_FORMULA}",
        FormulaRule(formula=['LEFT($E2,4)="Sem "'], fill=VERMELHO),
    )
    wv.conditional_formatting.add(
        f"A2:E{LINHAS_FORMULA}",
        FormulaRule(formula=['LEFT($E2,7)="Baixado"'], fill=AMARELO),
    )

    # --------------------------------------------------------- Movimentações
    wm = wb.create_sheet("Movimentacoes")
    cabecalho(wm, ["Data/hora", "Insumo", "Tipo", "Quantidade", "Saldo após", "Observação"],
              [18, 28, 11, 13, 13, 50])

    # --------------------------------------------------------------- Compras
    wc = wb.create_sheet("Compras")
    wc.column_dimensions["A"].width = 28
    for col in "BCDEF":
        wc.column_dimensions[col].width = 15
    wc["A1"] = "Rode a macro GerarListaCompras para preencher."

    if not vazia:
        from seed import INSUMOS, PRODUTOS
        for i, (nome, _cat, un, inicial, minimo, custo) in enumerate(INSUMOS, start=2):
            wi.cell(i, 1, nome); wi.cell(i, 2, un); wi.cell(i, 3, inicial)
            wi.cell(i, 4, minimo); wi.cell(i, 5, custo)
        for codigo, nome, _cat, _preco, ficha in PRODUTOS:
            for insumo, qtd in ficha:
                wf.append([codigo, nome, insumo, qtd])
        for linha in [("1001", "Camarão Gratinado", 3, "10/11/2026 20:15"),
                      ("1003", "Moqueca de Tilápia", 4, "10/11/2026 21:05"),
                      ("2001", "Cerveja Long Neck", 18, "10/11/2026 21:30"),
                      ("9999", "Sobremesa Petit Gateau", 2, "10/11/2026 22:00")]:
            wv.append(list(linha))

    return wb


if __name__ == "__main__":
    vazia = "--vazia" in sys.argv
    nome = "ControleEstoque_vazia.xlsx" if vazia else "ControleEstoque.xlsx"
    montar(vazia).save(os.path.join(AQUI, nome))
    print("gerado:", nome)
