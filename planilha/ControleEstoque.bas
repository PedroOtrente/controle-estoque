Attribute VB_Name = "ControleEstoque"
'==============================================================================
' Controle de Estoque em Excel - baixa automatica por ficha tecnica
'
' Abas usadas:
'   Insumos        A Insumo | B Unidade | C Estoque atual | D Minimo | E Custo | F Situacao
'   Fichas         A Codigo PDV | B Produto | C Insumo | D Quantidade por unidade
'   Vendas         A Codigo PDV | B Produto | C Quantidade | D Data | E Status
'   Movimentacoes  A Data/hora | B Insumo | C Tipo | D Quantidade | E Saldo apos | F Observacao
'   Compras        gerada pela macro GerarListaCompras
'
' Macros:
'   ProcessarVendas    - da baixa nos insumos de cada venda ainda nao processada
'   GerarListaCompras  - lista o que esta abaixo do minimo e quanto comprar
'   RegistrarEntrada   - lanca recebimento de mercadoria
'   RegistrarPerda     - lanca quebra, descarte ou validade vencida
'==============================================================================
Option Explicit

Private Const ABA_INSUMOS As String = "Insumos"
Private Const ABA_FICHAS As String = "Fichas"
Private Const ABA_VENDAS As String = "Vendas"
Private Const ABA_MOV As String = "Movimentacoes"
Private Const ABA_COMPRAS As String = "Compras"

' Ultima linha preenchida da coluna (dados continuos a partir da linha 2)
Private Function UltimaLinha(ws As Worksheet, coluna As Long) As Long
    Dim r As Long
    r = 1
    Do While Trim(CStr(ws.Cells(r + 1, coluna).Value)) <> ""
        r = r + 1
    Loop
    UltimaLinha = r
End Function

Private Function Normalizar(ByVal texto As Variant) As String
    Normalizar = LCase(Trim(CStr(texto)))
End Function

' Devolve a linha do insumo na aba Insumos, ou 0 se nao existir
Private Function LinhaDoInsumo(nome As String) As Long
    Dim ws As Worksheet, r As Long, alvo As String
    Set ws = ThisWorkbook.Worksheets(ABA_INSUMOS)
    alvo = Normalizar(nome)
    LinhaDoInsumo = 0
    For r = 2 To UltimaLinha(ws, 1)
        If Normalizar(ws.Cells(r, 1).Value) = alvo Then
            LinhaDoInsumo = r
            Exit Function
        End If
    Next r
End Function

' Aplica uma movimentacao ao saldo e registra no historico
Private Sub Movimentar(linhaInsumo As Long, tipo As String, quantidade As Double, obs As String)
    Dim wsI As Worksheet, wsM As Worksheet, novo As Double, r As Long
    Set wsI = ThisWorkbook.Worksheets(ABA_INSUMOS)
    Set wsM = ThisWorkbook.Worksheets(ABA_MOV)

    novo = Round(CDbl(wsI.Cells(linhaInsumo, 3).Value) + quantidade, 4)
    wsI.Cells(linhaInsumo, 3).Value = novo

    r = UltimaLinha(wsM, 1) + 1
    wsM.Cells(r, 1).Value = Now
    wsM.Cells(r, 1).NumberFormat = "dd/mm/yyyy hh:mm"
    wsM.Cells(r, 2).Value = wsI.Cells(linhaInsumo, 1).Value
    wsM.Cells(r, 3).Value = tipo
    wsM.Cells(r, 4).Value = quantidade
    wsM.Cells(r, 5).Value = novo
    wsM.Cells(r, 6).Value = obs
End Sub

'------------------------------------------------------------------------------
' Baixa automatica: cruza cada venda com a ficha tecnica do produto
'------------------------------------------------------------------------------
Public Sub ProcessarVendas()
    Dim wsV As Worksheet, wsF As Worksheet
    Dim rv As Long, rf As Long, li As Long
    Dim codigo As String, produto As String, qtdVenda As Double
    Dim achouFicha As Boolean, faltando As String
    Dim baixadas As Long, pendentes As Long

    Set wsV = ThisWorkbook.Worksheets(ABA_VENDAS)
    Set wsF = ThisWorkbook.Worksheets(ABA_FICHAS)

    For rv = 2 To UltimaLinha(wsV, 3)
        If Trim(CStr(wsV.Cells(rv, 5).Value)) = "" And Trim(CStr(wsV.Cells(rv, 3).Value)) <> "" Then
            codigo = Normalizar(wsV.Cells(rv, 1).Value)
            produto = Normalizar(wsV.Cells(rv, 2).Value)
            qtdVenda = CDbl(wsV.Cells(rv, 3).Value)
            achouFicha = False
            faltando = ""

            For rf = 2 To UltimaLinha(wsF, 3)
                If (codigo <> "" And Normalizar(wsF.Cells(rf, 1).Value) = codigo) Or _
                   (codigo = "" And Normalizar(wsF.Cells(rf, 2).Value) = produto) Then
                    achouFicha = True
                    li = LinhaDoInsumo(CStr(wsF.Cells(rf, 3).Value))
                    If li > 0 Then
                        Movimentar li, "VENDA", -CDbl(wsF.Cells(rf, 4).Value) * qtdVenda, _
                            "Baixa automatica - " & wsV.Cells(rv, 2).Value & " x" & qtdVenda
                    Else
                        faltando = faltando & wsF.Cells(rf, 3).Value & "; "
                    End If
                End If
            Next rf

            If Not achouFicha Then
                wsV.Cells(rv, 5).Value = "Sem ficha tecnica"
                pendentes = pendentes + 1
            ElseIf faltando <> "" Then
                wsV.Cells(rv, 5).Value = "Baixado parcial - insumo nao cadastrado: " & faltando
                baixadas = baixadas + 1
            Else
                wsV.Cells(rv, 5).Value = "Baixado"
                baixadas = baixadas + 1
            End If
        End If
    Next rv

    MsgBox baixadas & " venda(s) baixada(s)." & vbCrLf & _
           pendentes & " sem ficha tecnica (cadastre na aba Fichas e rode de novo).", _
           vbInformation, "Processar vendas"
End Sub

'------------------------------------------------------------------------------
' Lista de compras: tudo abaixo do minimo, repondo ate 1,5x o minimo
'------------------------------------------------------------------------------
Public Sub GerarListaCompras()
    Dim wsI As Worksheet, wsC As Worksheet
    Dim r As Long, saida As Long, comprar As Double, total As Double

    Set wsI = ThisWorkbook.Worksheets(ABA_INSUMOS)
    Set wsC = ThisWorkbook.Worksheets(ABA_COMPRAS)

    wsC.Cells.ClearContents
    wsC.Range("A1").Value = "Lista de compras gerada em " & Format(Now, "dd/mm/yyyy hh:mm")
    wsC.Range("A3:F3").Value = Array("Insumo", "Unidade", "Estoque atual", "Minimo", "Comprar", "Custo estimado")
    wsC.Range("A3:F3").Font.Bold = True

    saida = 4
    For r = 2 To UltimaLinha(wsI, 1)
        If CDbl(wsI.Cells(r, 3).Value) < CDbl(wsI.Cells(r, 4).Value) Then
            comprar = Round(CDbl(wsI.Cells(r, 4).Value) * 1.5 - CDbl(wsI.Cells(r, 3).Value), 3)
            wsC.Cells(saida, 1).Value = wsI.Cells(r, 1).Value
            wsC.Cells(saida, 2).Value = wsI.Cells(r, 2).Value
            wsC.Cells(saida, 3).Value = wsI.Cells(r, 3).Value
            wsC.Cells(saida, 4).Value = wsI.Cells(r, 4).Value
            wsC.Cells(saida, 5).Value = comprar
            wsC.Cells(saida, 6).Value = Round(comprar * CDbl(wsI.Cells(r, 5).Value), 2)
            wsC.Cells(saida, 6).NumberFormat = "R$ #,##0.00"
            total = total + wsC.Cells(saida, 6).Value
            saida = saida + 1
        End If
    Next r

    If saida = 4 Then
        wsC.Cells(4, 1).Value = "Nenhum insumo abaixo do minimo."
    Else
        wsC.Cells(saida + 1, 5).Value = "Total"
        wsC.Cells(saida + 1, 5).Font.Bold = True
        wsC.Cells(saida + 1, 6).Value = total
        wsC.Cells(saida + 1, 6).NumberFormat = "R$ #,##0.00"
        wsC.Cells(saida + 1, 6).Font.Bold = True
    End If

    wsC.Activate
End Sub

'------------------------------------------------------------------------------
' Lancamentos manuais
'------------------------------------------------------------------------------
Public Sub RegistrarEntrada()
    LancamentoManual "ENTRADA", 1
End Sub

Public Sub RegistrarPerda()
    LancamentoManual "PERDA", -1
End Sub

Private Sub LancamentoManual(tipo As String, sinal As Long)
    Dim nome As String, qtdTexto As String, obs As String, li As Long

    nome = InputBox("Nome do insumo (igual a aba Insumos):", tipo)
    If nome = "" Then Exit Sub
    li = LinhaDoInsumo(nome)
    If li = 0 Then
        MsgBox "Insumo nao encontrado: " & nome, vbExclamation, tipo
        Exit Sub
    End If

    qtdTexto = Replace(InputBox("Quantidade em " & ThisWorkbook.Worksheets(ABA_INSUMOS).Cells(li, 2).Value & ":", tipo), ",", ".")
    If qtdTexto = "" Or Not IsNumeric(Val(qtdTexto)) Or Val(qtdTexto) <= 0 Then
        MsgBox "Quantidade invalida.", vbExclamation, tipo
        Exit Sub
    End If

    obs = InputBox("Observacao (nota fiscal, motivo da perda...):", tipo)
    Movimentar li, tipo, sinal * Val(qtdTexto), obs
    MsgBox tipo & " registrada. Saldo de " & ThisWorkbook.Worksheets(ABA_INSUMOS).Cells(li, 1).Value & _
           ": " & ThisWorkbook.Worksheets(ABA_INSUMOS).Cells(li, 3).Value, vbInformation, tipo
End Sub
