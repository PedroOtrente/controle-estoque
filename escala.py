"""
Gerador de escala de trabalho.

Regras aplicadas:
  - cada funcionário tem 1 folga por semana (regime 6x1);
  - o domingo de folga se repete no máximo a cada N semanas (padrão 4 = uma vez por mês,
    referência do comércio — confirme a regra da convenção coletiva local);
  - as folgas são distribuídas para manter o mínimo de pessoas por setor
    em cada dia; dias abaixo do mínimo são sinalizados.
"""

import calendar
import io
from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

from models import db

bp = Blueprint("escala", __name__, url_prefix="/escala")

DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


# ---------------------------------------------------------------- modelos
class Funcionario(db.Model):
    __tablename__ = "funcionario"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    setor = db.Column(db.String(60), nullable=False, default="Salão")
    turno = db.Column(db.String(40), default="")
    folga_fixa = db.Column(db.Integer)  # 0=seg ... 6=dom; vazio = rotativa
    ativo = db.Column(db.Boolean, default=True)


class MinimoSetor(db.Model):
    """Mínimo de pessoas trabalhando por setor; pode diferir no fim de semana."""

    __tablename__ = "minimo_setor"

    id = db.Column(db.Integer, primary_key=True)
    setor = db.Column(db.String(60), unique=True, nullable=False)
    minimo_semana = db.Column(db.Integer, default=1)
    minimo_fds = db.Column(db.Integer, default=1)


# -------------------------------------------------------------- algoritmo
def gerar_escala(ano, mes, funcionarios, minimos, intervalo_domingo=4):
    """
    Devolve (dias, grade, cobertura, alertas).

    grade[func_id][data] = "T" (trabalha) ou "F" (folga)
    cobertura[data][setor] = pessoas trabalhando
    """
    primeiro = date(ano, mes, 1)
    ultimo = date(ano, mes, calendar.monthrange(ano, mes)[1])
    dias = [primeiro + timedelta(d) for d in range((ultimo - primeiro).days + 1)]

    # semanas de segunda a domingo que tocam o mês
    inicio = primeiro - timedelta(primeiro.weekday())
    semanas = []
    seg = inicio
    while seg <= ultimo:
        semanas.append([seg + timedelta(i) for i in range(7)])
        seg += timedelta(7)

    por_setor = {}
    for f in funcionarios:
        por_setor.setdefault(f.setor, []).append(f)

    def minimo(setor, d):
        m = minimos.get(setor)
        if not m:
            return 0
        return m.minimo_fds if d.weekday() >= 5 else m.minimo_semana

    # escalona quem começa devendo domingo, para não folgarem todos juntos
    semanas_sem_domingo = {}
    for setor, lista in por_setor.items():
        for i, f in enumerate(lista):
            semanas_sem_domingo[f.id] = i % intervalo_domingo

    MAX_DIAS_SEGUIDOS = 6
    # sem histórico anterior, considera que todos folgaram no domingo
    # imediatamente antes da primeira semana
    ultima_folga = {f.id: inicio - timedelta(1) for f in funcionarios}
    grade = {f.id: {} for f in funcionarios}
    folgas_extras = 0

    for w, semana in enumerate(semanas):
        folgas_no_dia = {(s, d): 0 for s in por_setor for d in semana}

        def sobra(setor, d):
            return len(por_setor[setor]) - folgas_no_dia[(setor, d)] - minimo(setor, d)

        def deve_domingo(f):
            return semanas_sem_domingo[f.id] >= intervalo_domingo - 1

        # ordem: folga fixa, quem deve domingo, depois o resto em rodízio
        ordem = sorted(
            funcionarios,
            key=lambda f: (
                0 if f.folga_fixa is not None else (1 if deve_domingo(f) else 2),
                (f.id + w) % 7,
            ),
        )

        for f in ordem:
            # dias que respeitam o limite de dias seguidos de trabalho
            validos = [
                d for d in semana
                if (d - ultima_folga[f.id]).days <= MAX_DIAS_SEGUIDOS + 1
            ]
            domingo = semana[6]
            escolhidos = []

            def melhor(candidatos):
                # maior sobra de cobertura; empate: o dia mais tarde,
                # para preservar margem na semana seguinte
                return max(candidatos, key=lambda d: (sobra(f.setor, d), d.weekday()))

            if f.folga_fixa is not None:
                escolhidos = [semana[f.folga_fixa]]
                if deve_domingo(f) and f.folga_fixa != 6:
                    escolhidos.append(domingo)
            elif deve_domingo(f):
                if domingo in validos:
                    escolhidos = [domingo]
                else:
                    # folga normal dentro do limite + domingo garantido
                    escolhidos = [melhor([d for d in validos if d != domingo]), domingo]
            else:
                uteis = [d for d in validos if d != domingo]
                escolhidos = [melhor(uteis or validos)]

            if len(escolhidos) > 1 and primeiro <= domingo <= ultimo:
                folgas_extras += 1

            for d in escolhidos:
                folgas_no_dia[(f.setor, d)] += 1
            ultima_folga[f.id] = max(escolhidos)
            semanas_sem_domingo[f.id] = 0 if domingo in escolhidos else semanas_sem_domingo[f.id] + 1

            for d in semana:
                if primeiro <= d <= ultimo:
                    grade[f.id][d] = "F" if d in escolhidos else "T"

    cobertura = {}
    alertas = []

    # confere o limite de dias seguidos (deve sempre passar; é uma garantia)
    for f in funcionarios:
        seguidos = 0
        for d in dias:
            seguidos = seguidos + 1 if grade[f.id].get(d) == "T" else 0
            if seguidos > MAX_DIAS_SEGUIDOS:
                alertas.append(f"{f.nome}: mais de {MAX_DIAS_SEGUIDOS} dias seguidos até {d.strftime('%d/%m')}")
                break
    for d in dias:
        cobertura[d] = {}
        for setor, lista in por_setor.items():
            trabalhando = sum(1 for f in lista if grade[f.id].get(d) == "T")
            cobertura[d][setor] = trabalhando
            if trabalhando < minimo(setor, d):
                alertas.append(
                    f"{d.strftime('%d/%m')} ({DIAS[d.weekday()]}) · {setor}: "
                    f"{trabalhando} de {minimo(setor, d)} necessários"
                )

    return dias, grade, cobertura, alertas


def exportar_xlsx(ano, mes, dias, grade, cobertura, funcionarios):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = f"Escala {mes:02d}-{ano}"

    fino = Side(style="thin", color="D0D4CC")
    borda = Border(left=fino, right=fino, top=fino, bottom=fino)
    centro = Alignment(horizontal="center", vertical="center")
    verde = PatternFill("solid", fgColor="E8F2EC")
    cinza = PatternFill("solid", fgColor="EFEFEC")
    folga_fill = PatternFill("solid", fgColor="FFE7A3")
    cab = PatternFill("solid", fgColor="1F6B4A")

    ws["A1"] = f"Escala de trabalho — {MESES[mes]} de {ano}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "T = trabalha   F = folga"
    ws["A2"].font = Font(italic=True, color="6B7065")

    linha = 4
    ws.cell(linha, 1, "Funcionário")
    ws.cell(linha, 2, "Setor")
    for j, d in enumerate(dias):
        c = ws.cell(linha, 3 + j, f"{d.day}\n{DIAS[d.weekday()]}")
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    for col in range(1, 3 + len(dias)):
        c = ws.cell(linha, col)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = cab
        c.border = borda
    ws.row_dimensions[linha].height = 30

    for f in sorted(funcionarios, key=lambda x: (x.setor, x.nome)):
        linha += 1
        ws.cell(linha, 1, f.nome).border = borda
        ws.cell(linha, 2, f.setor).border = borda
        for j, d in enumerate(dias):
            v = grade[f.id].get(d, "")
            c = ws.cell(linha, 3 + j, v)
            c.alignment = centro
            c.border = borda
            if v == "F":
                c.fill = folga_fill
                c.font = Font(bold=True)
            elif d.weekday() >= 5:
                c.fill = cinza

    linha += 2
    ws.cell(linha, 1, "Cobertura por setor").font = Font(bold=True)
    setores = sorted({f.setor for f in funcionarios})
    for s in setores:
        linha += 1
        ws.cell(linha, 1, s).border = borda
        for j, d in enumerate(dias):
            c = ws.cell(linha, 3 + j, cobertura[d].get(s, 0))
            c.alignment = centro
            c.border = borda
            c.fill = verde

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 14
    for j in range(len(dias)):
        ws.column_dimensions[get_column_letter(3 + j)].width = 5.2
    ws.freeze_panes = "C5"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ------------------------------------------------------------------ rotas
def _mes_ano():
    hoje = date.today()
    ano = request.values.get("ano", type=int) or hoje.year
    mes = request.values.get("mes", type=int) or hoje.month
    return ano, mes


@bp.route("/")
def painel():
    ano, mes = _mes_ano()
    funcionarios = Funcionario.query.filter_by(ativo=True).order_by(
        Funcionario.setor, Funcionario.nome
    ).all()
    minimos = {m.setor: m for m in MinimoSetor.query.all()}
    setores = sorted({f.setor for f in funcionarios} | set(minimos))
    intervalo = request.values.get("domingo", type=int) or 4

    resultado = None
    if funcionarios:
        resultado = gerar_escala(ano, mes, funcionarios, minimos, intervalo)

    return render_template(
        "escala.html",
        ano=ano, mes=mes, nome_mes=MESES[mes], dias_semana=DIAS,
        funcionarios=funcionarios, minimos=minimos, setores=setores,
        resultado=resultado, intervalo=intervalo,
    )


@bp.route("/funcionario", methods=["POST"])
def funcionario_novo():
    nome = request.form.get("nome", "").strip()
    setor = request.form.get("setor", "").strip() or "Salão"
    if not nome:
        flash("Informe o nome.", "erro")
        return redirect(url_for("escala.painel"))
    fixa = request.form.get("folga_fixa", "")
    db.session.add(Funcionario(
        nome=nome, setor=setor,
        turno=request.form.get("turno", "").strip(),
        folga_fixa=int(fixa) if fixa != "" else None,
    ))
    if not MinimoSetor.query.filter_by(setor=setor).first():
        db.session.add(MinimoSetor(setor=setor, minimo_semana=1, minimo_fds=1))
    db.session.commit()
    flash(f"{nome} adicionado.", "ok")
    return redirect(url_for("escala.painel"))


@bp.route("/funcionario/<int:fid>/remover", methods=["POST"])
def funcionario_remover(fid):
    f = db.session.get(Funcionario, fid)
    if f:
        f.ativo = False
        db.session.commit()
        flash(f"{f.nome} removido da escala.", "ok")
    return redirect(url_for("escala.painel"))


@bp.route("/minimos", methods=["POST"])
def minimos_salvar():
    for m in MinimoSetor.query.all():
        sem = request.form.get(f"sem_{m.id}", type=int)
        fds = request.form.get(f"fds_{m.id}", type=int)
        if sem is not None:
            m.minimo_semana = max(sem, 0)
        if fds is not None:
            m.minimo_fds = max(fds, 0)
    db.session.commit()
    flash("Mínimos atualizados.", "ok")
    return redirect(url_for("escala.painel"))


@bp.route("/exportar")
def exportar():
    ano, mes = _mes_ano()
    intervalo = request.values.get("domingo", type=int) or 4
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    if not funcionarios:
        flash("Cadastre a equipe antes de exportar.", "erro")
        return redirect(url_for("escala.painel"))
    minimos = {m.setor: m for m in MinimoSetor.query.all()}
    dias, grade, cobertura, _ = gerar_escala(ano, mes, funcionarios, minimos, intervalo)
    buf = exportar_xlsx(ano, mes, dias, grade, cobertura, funcionarios)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"escala_{ano}_{mes:02d}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
