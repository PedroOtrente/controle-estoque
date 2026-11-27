"""
Sistema de Controle de Estoque — aplicação Flask.

Execução:
    python app.py
    (abre em http://localhost:5000)
"""

import csv
import io
import os
import uuid
from datetime import datetime, timedelta

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func

from models import (
    UNIDADES,
    Insumo,
    ItemFichaTecnica,
    LancamentoVenda,
    Movimentacao,
    Produto,
    baixar_venda,
    db,
    registrar_movimentacao,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-local")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'estoque.db')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    import escala  # noqa: F401  (registra os modelos da escala antes do create_all)

    with app.app_context():
        db.create_all()

    registrar_rotas(app)
    app.register_blueprint(escala.bp)
    registrar_filtros(app)
    return app


def registrar_filtros(app):
    @app.template_filter("num")
    def fmt_num(valor, casas=2):
        if valor is None:
            return "—"
        texto = f"{valor:,.{casas}f}"
        return texto.replace(",", "X").replace(".", ",").replace("X", ".")

    @app.template_filter("moeda")
    def fmt_moeda(valor):
        if valor is None:
            return "—"
        return "R$ " + fmt_num(valor, 2)

    @app.template_filter("datahora")
    def fmt_datahora(valor):
        if not valor:
            return "—"
        return valor.strftime("%d/%m/%Y %H:%M")


def registrar_rotas(app):
    # ------------------------------------------------------------------ painel
    @app.route("/")
    def painel():
        insumos = Insumo.query.filter_by(ativo=True).order_by(Insumo.nome).all()
        criticos = [i for i in insumos if i.situacao in ("critico", "zerado")]
        atencao = [i for i in insumos if i.situacao == "atencao"]

        desde = datetime.now() - timedelta(days=7)
        consumo = (
            db.session.query(
                Insumo.nome,
                Insumo.unidade,
                func.sum(Movimentacao.quantidade).label("total"),
            )
            .join(Movimentacao, Movimentacao.insumo_id == Insumo.id)
            .filter(Movimentacao.tipo == "VENDA", Movimentacao.criado_em >= desde)
            .group_by(Insumo.id)
            .order_by(func.sum(Movimentacao.quantidade))
            .limit(8)
            .all()
        )

        valor_estoque = sum(
            (i.estoque_atual or 0) * (i.custo_unitario or 0) for i in insumos
        )

        ultimas = (
            Movimentacao.query.order_by(Movimentacao.criado_em.desc()).limit(12).all()
        )

        return render_template(
            "painel.html",
            insumos=insumos,
            criticos=criticos,
            atencao=atencao,
            consumo=consumo,
            valor_estoque=valor_estoque,
            ultimas=ultimas,
        )

    # ----------------------------------------------------------------- insumos
    @app.route("/insumos")
    def insumos():
        busca = request.args.get("q", "").strip()
        query = Insumo.query
        if busca:
            query = query.filter(Insumo.nome.ilike(f"%{busca}%"))
        itens = query.order_by(Insumo.categoria, Insumo.nome).all()
        return render_template(
            "insumos.html", itens=itens, busca=busca, unidades=UNIDADES
        )

    @app.route("/insumos/novo", methods=["POST"])
    def insumo_novo():
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome do insumo.", "erro")
            return redirect(url_for("insumos"))

        if Insumo.query.filter(func.lower(Insumo.nome) == nome.lower()).first():
            flash(f"Já existe um insumo chamado {nome}.", "erro")
            return redirect(url_for("insumos"))

        insumo = Insumo(
            nome=nome,
            categoria=request.form.get("categoria", "Geral").strip() or "Geral",
            unidade=request.form.get("unidade", "kg"),
            estoque_minimo=_float(request.form.get("estoque_minimo")),
            custo_unitario=_float(request.form.get("custo_unitario")),
        )
        db.session.add(insumo)
        db.session.flush()

        inicial = _float(request.form.get("estoque_inicial"))
        if inicial:
            registrar_movimentacao(
                insumo, "ENTRADA", inicial, "Estoque inicial", usuario="cadastro"
            )

        db.session.commit()
        flash(f"{nome} cadastrado.", "ok")
        return redirect(url_for("insumos"))

    @app.route("/insumos/<int:insumo_id>/editar", methods=["POST"])
    def insumo_editar(insumo_id):
        insumo = db.session.get(Insumo, insumo_id)
        if insumo is None:
            flash("Insumo não encontrado.", "erro")
            return redirect(url_for("insumos"))

        insumo.estoque_minimo = _float(request.form.get("estoque_minimo"))
        insumo.custo_unitario = _float(request.form.get("custo_unitario"))
        db.session.commit()
        flash(f"{insumo.nome} atualizado.", "ok")
        return redirect(url_for("insumos"))

    @app.route("/insumos/<int:insumo_id>")
    def insumo_detalhe(insumo_id):
        insumo = db.session.get(Insumo, insumo_id)
        if insumo is None:
            flash("Insumo não encontrado.", "erro")
            return redirect(url_for("insumos"))

        movs = (
            Movimentacao.query.filter_by(insumo_id=insumo_id)
            .order_by(Movimentacao.criado_em.desc())
            .limit(60)
            .all()
        )
        return render_template("insumo_detalhe.html", insumo=insumo, movs=movs)

    # ------------------------------------------------------------ movimentação
    @app.route("/movimentar", methods=["GET", "POST"])
    def movimentar():
        """Tela otimizada para uso no celular, dentro do estoque."""
        if request.method == "POST":
            insumo = db.session.get(Insumo, _int(request.form.get("insumo_id")))
            tipo = request.form.get("tipo", "ENTRADA")
            quantidade = _float(request.form.get("quantidade"))

            if insumo is None:
                flash("Selecione um insumo.", "erro")
            elif quantidade <= 0:
                flash("Informe uma quantidade maior que zero.", "erro")
            else:
                sinal = 1 if tipo == "ENTRADA" else -1
                registrar_movimentacao(
                    insumo,
                    tipo,
                    sinal * quantidade,
                    request.form.get("observacao", "").strip() or None,
                    usuario=request.form.get("usuario", "estoque").strip() or "estoque",
                )
                db.session.commit()
                verbo = "Entrada" if tipo == "ENTRADA" else "Baixa"
                flash(
                    f"{verbo} de {quantidade:g} {insumo.unidade} em {insumo.nome}. "
                    f"Saldo: {insumo.estoque_atual:g} {insumo.unidade}.",
                    "ok",
                )
            return redirect(url_for("movimentar"))

        itens = Insumo.query.filter_by(ativo=True).order_by(Insumo.nome).all()
        recentes = (
            Movimentacao.query.filter(Movimentacao.tipo != "VENDA")
            .order_by(Movimentacao.criado_em.desc())
            .limit(8)
            .all()
        )
        return render_template("movimentar.html", itens=itens, recentes=recentes)

    @app.route("/contagem", methods=["GET", "POST"])
    def contagem():
        """Inventário: informa o contado, o sistema gera o ajuste da diferença."""
        if request.method == "POST":
            ajustes = 0
            for chave, valor in request.form.items():
                if not chave.startswith("contado_"):
                    continue
                if valor.strip() == "":
                    continue

                insumo = db.session.get(Insumo, int(chave.split("_", 1)[1]))
                if insumo is None:
                    continue

                contado = _float(valor)
                diferenca = round(contado - (insumo.estoque_atual or 0), 4)
                if abs(diferenca) < 0.0001:
                    continue

                registrar_movimentacao(
                    insumo,
                    "AJUSTE",
                    diferenca,
                    f"Contagem de inventário · sistema {insumo.estoque_atual:g}, "
                    f"contado {contado:g}",
                    usuario=request.form.get("usuario", "estoque") or "estoque",
                )
                ajustes += 1

            db.session.commit()
            if ajustes:
                flash(f"{ajustes} ajuste(s) registrado(s).", "ok")
            else:
                flash("Nenhuma divergência encontrada.", "ok")
            return redirect(url_for("contagem"))

        itens = Insumo.query.filter_by(ativo=True).order_by(
            Insumo.categoria, Insumo.nome
        ).all()
        return render_template("contagem.html", itens=itens)

    # ---------------------------------------------------------------- produtos
    @app.route("/produtos")
    def produtos():
        itens = Produto.query.order_by(Produto.categoria, Produto.nome).all()
        return render_template("produtos.html", itens=itens)

    @app.route("/produtos/novo", methods=["POST"])
    def produto_novo():
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome do produto.", "erro")
            return redirect(url_for("produtos"))

        produto = Produto(
            nome=nome,
            codigo_pdv=request.form.get("codigo_pdv", "").strip() or None,
            categoria=request.form.get("categoria", "Pratos").strip() or "Pratos",
            preco_venda=_float(request.form.get("preco_venda")),
        )
        db.session.add(produto)
        db.session.commit()
        flash(f"{nome} cadastrado. Monte a ficha técnica.", "ok")
        return redirect(url_for("ficha_tecnica", produto_id=produto.id))

    @app.route("/produtos/<int:produto_id>/ficha", methods=["GET", "POST"])
    def ficha_tecnica(produto_id):
        produto = db.session.get(Produto, produto_id)
        if produto is None:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("produtos"))

        if request.method == "POST":
            insumo_id = _int(request.form.get("insumo_id"))
            quantidade = _float(request.form.get("quantidade"))

            if not insumo_id or quantidade <= 0:
                flash("Selecione o insumo e informe a quantidade.", "erro")
            else:
                existente = ItemFichaTecnica.query.filter_by(
                    produto_id=produto_id, insumo_id=insumo_id
                ).first()
                if existente:
                    existente.quantidade = quantidade
                else:
                    db.session.add(
                        ItemFichaTecnica(
                            produto_id=produto_id,
                            insumo_id=insumo_id,
                            quantidade=quantidade,
                        )
                    )
                db.session.commit()
                flash("Ficha técnica atualizada.", "ok")
            return redirect(url_for("ficha_tecnica", produto_id=produto_id))

        insumos_disp = Insumo.query.filter_by(ativo=True).order_by(Insumo.nome).all()
        return render_template(
            "ficha.html", produto=produto, insumos=insumos_disp
        )

    @app.route("/ficha/item/<int:item_id>/remover", methods=["POST"])
    def ficha_remover(item_id):
        item = db.session.get(ItemFichaTecnica, item_id)
        if item is None:
            flash("Item não encontrado.", "erro")
            return redirect(url_for("produtos"))
        produto_id = item.produto_id
        db.session.delete(item)
        db.session.commit()
        flash("Insumo removido da ficha.", "ok")
        return redirect(url_for("ficha_tecnica", produto_id=produto_id))

    # ----------------------------------------------------------------- vendas
    @app.route("/vendas", methods=["GET", "POST"])
    def vendas():
        """
        Importa o relatório de vendas do PDV (CSV) e dá baixa automática
        nos insumos, via ficha técnica de cada produto.

        Colunas aceitas: codigo | produto | quantidade | valor | data
        """
        if request.method == "POST":
            arquivo = request.files.get("arquivo")
            if not arquivo or not arquivo.filename:
                flash("Selecione o arquivo CSV exportado do PDV.", "erro")
                return redirect(url_for("vendas"))

            try:
                conteudo = arquivo.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                arquivo.seek(0)
                conteudo = arquivo.read().decode("latin-1")

            resultado = importar_vendas_csv(conteudo)
            db.session.commit()

            flash(
                f"{resultado['processados']} venda(s) baixada(s), "
                f"{resultado['falhas']} sem ficha técnica ou produto não encontrado.",
                "ok" if resultado["processados"] else "erro",
            )
            return redirect(url_for("vendas"))

        lancamentos = (
            LancamentoVenda.query.order_by(LancamentoVenda.id.desc()).limit(80).all()
        )
        pendentes = LancamentoVenda.query.filter_by(processado=False).count()
        return render_template(
            "vendas.html", lancamentos=lancamentos, pendentes=pendentes
        )

    @app.route("/vendas/lancar", methods=["POST"])
    def venda_manual():
        """Lançamento avulso de venda, sem CSV."""
        produto = db.session.get(Produto, _int(request.form.get("produto_id")))
        quantidade = _float(request.form.get("quantidade")) or 1

        if produto is None:
            flash("Selecione um produto.", "erro")
            return redirect(url_for("vendas"))

        lanc = LancamentoVenda(
            produto=produto,
            produto_descricao=produto.nome,
            quantidade=quantidade,
            valor_total=(produto.preco_venda or 0) * quantidade,
            data_venda=datetime.now(),
            lote_importacao="manual",
        )
        db.session.add(lanc)
        db.session.flush()

        movs = baixar_venda(lanc, usuario="manual")
        db.session.commit()

        if movs:
            flash(f"{produto.nome} ×{quantidade:g} baixado do estoque.", "ok")
        else:
            flash(lanc.erro or "Não foi possível baixar.", "erro")
        return redirect(url_for("vendas"))

    # -------------------------------------------------------------- relatórios
    @app.route("/relatorios")
    def relatorios():
        dias = _int(request.args.get("dias")) or 30
        desde = datetime.now() - timedelta(days=dias)

        consumo = (
            db.session.query(
                Insumo.nome,
                Insumo.unidade,
                Insumo.custo_unitario,
                func.abs(func.sum(Movimentacao.quantidade)).label("total"),
            )
            .join(Movimentacao, Movimentacao.insumo_id == Insumo.id)
            .filter(Movimentacao.tipo == "VENDA", Movimentacao.criado_em >= desde)
            .group_by(Insumo.id)
            .order_by(func.abs(func.sum(Movimentacao.quantidade)).desc())
            .all()
        )

        perdas = (
            db.session.query(
                Insumo.nome,
                Insumo.unidade,
                func.abs(func.sum(Movimentacao.quantidade)).label("total"),
            )
            .join(Movimentacao, Movimentacao.insumo_id == Insumo.id)
            .filter(Movimentacao.tipo == "PERDA", Movimentacao.criado_em >= desde)
            .group_by(Insumo.id)
            .order_by(func.abs(func.sum(Movimentacao.quantidade)).desc())
            .all()
        )

        mais_vendidos = (
            db.session.query(
                Produto.nome,
                func.sum(LancamentoVenda.quantidade).label("qtd"),
                func.sum(LancamentoVenda.valor_total).label("valor"),
            )
            .join(LancamentoVenda, LancamentoVenda.produto_id == Produto.id)
            .filter(LancamentoVenda.data_venda >= desde)
            .group_by(Produto.id)
            .order_by(func.sum(LancamentoVenda.quantidade).desc())
            .limit(15)
            .all()
        )

        return render_template(
            "relatorios.html",
            dias=dias,
            consumo=consumo,
            perdas=perdas,
            mais_vendidos=mais_vendidos,
        )

    @app.route("/relatorios/reposicao.csv")
    def exportar_reposicao():
        """Lista de compras: tudo que está abaixo do mínimo."""
        itens = [
            i
            for i in Insumo.query.filter_by(ativo=True).order_by(Insumo.nome).all()
            if i.abaixo_minimo
        ]

        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(
            ["Insumo", "Unidade", "Estoque atual", "Mínimo", "Comprar", "Custo estimado"]
        )
        for i in itens:
            comprar = round(max(i.estoque_minimo * 1.5 - i.estoque_atual, 0), 3)
            writer.writerow(
                [
                    i.nome,
                    i.unidade,
                    f"{i.estoque_atual:g}",
                    f"{i.estoque_minimo:g}",
                    f"{comprar:g}",
                    f"{comprar * (i.custo_unitario or 0):.2f}",
                ]
            )

        return (
            buffer.getvalue(),
            200,
            {
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": "attachment; filename=reposicao.csv",
            },
        )


# --------------------------------------------------------------------- helpers
def importar_vendas_csv(conteudo):
    """
    Lê o CSV de vendas e processa cada linha.

    Reconhece ; ou , como separador e tolera variação nos nomes das colunas.
    """
    amostra = conteudo[:2048]
    try:
        dialeto = csv.Sniffer().sniff(amostra, delimiters=";,\t")
        delim = dialeto.delimiter
    except csv.Error:
        delim = ";"

    leitor = csv.DictReader(io.StringIO(conteudo), delimiter=delim)
    lote = uuid.uuid4().hex[:10]

    processados = 0
    falhas = 0

    for linha in leitor:
        chaves = {(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()}

        codigo = _primeiro(chaves, "codigo", "código", "cod", "codigo_pdv")
        nome = _primeiro(chaves, "produto", "descricao", "descrição", "item", "nome")
        qtd = _float(_primeiro(chaves, "quantidade", "qtd", "qtde")) or 1
        valor = _float(_primeiro(chaves, "valor", "total", "valor_total"))
        data = _data(_primeiro(chaves, "data", "data_venda", "dt"))

        produto = None
        if codigo:
            produto = Produto.query.filter_by(codigo_pdv=codigo).first()
        if produto is None and nome:
            produto = Produto.query.filter(func.lower(Produto.nome) == nome.lower()).first()
        if produto is None and nome:
            produto = Produto.query.filter(Produto.nome.ilike(f"%{nome}%")).first()

        lanc = LancamentoVenda(
            produto=produto,
            produto_descricao=nome or codigo or "(sem descrição)",
            quantidade=qtd,
            valor_total=valor,
            data_venda=data or datetime.now(),
            lote_importacao=lote,
        )
        db.session.add(lanc)
        db.session.flush()

        movs = baixar_venda(lanc)
        if movs:
            processados += 1
        else:
            falhas += 1

    return {"processados": processados, "falhas": falhas, "lote": lote}


def _primeiro(dicionario, *chaves):
    for chave in chaves:
        if dicionario.get(chave):
            return dicionario[chave]
    return ""


def _float(valor):
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").strip()
    # aceita 1.234,56 e 1234.56
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _data(texto):
    if not texto:
        return None
    for formato in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip(), formato)
        except ValueError:
            continue
    return None


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
