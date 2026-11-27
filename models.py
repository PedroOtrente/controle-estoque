"""
Modelos de dados do sistema de controle de estoque.

A lógica central é a FICHA TÉCNICA: cada produto (prato/bebida vendida)
consome quantidades definidas de insumos. Quando uma venda é lançada,
o sistema "explode" o produto em seus insumos e dá baixa automática.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# Unidades de medida aceitas e seus fatores para a unidade base
UNIDADES = {
    "kg": ("kg", 1.0),
    "g": ("kg", 0.001),
    "L": ("L", 1.0),
    "ml": ("L", 0.001),
    "un": ("un", 1.0),
}


class Insumo(db.Model):
    """Matéria-prima controlada em estoque (camarão, cerveja, guardanapo...)."""

    __tablename__ = "insumo"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    categoria = db.Column(db.String(60), default="Geral")
    unidade = db.Column(db.String(10), nullable=False, default="kg")
    estoque_atual = db.Column(db.Float, nullable=False, default=0.0)
    estoque_minimo = db.Column(db.Float, nullable=False, default=0.0)
    custo_unitario = db.Column(db.Float, default=0.0)
    ativo = db.Column(db.Boolean, default=True)

    movimentacoes = db.relationship(
        "Movimentacao", back_populates="insumo", cascade="all, delete-orphan"
    )
    itens_ficha = db.relationship(
        "ItemFichaTecnica", back_populates="insumo", cascade="all, delete-orphan"
    )

    @property
    def abaixo_minimo(self):
        return self.estoque_atual < self.estoque_minimo

    @property
    def situacao(self):
        if self.estoque_atual <= 0:
            return "zerado"
        if self.abaixo_minimo:
            return "critico"
        if self.estoque_minimo and self.estoque_atual < self.estoque_minimo * 1.3:
            return "atencao"
        return "ok"

    def __repr__(self):
        return f"<Insumo {self.nome}>"


class Produto(db.Model):
    """Item vendido ao cliente. Liga-se aos insumos pela ficha técnica."""

    __tablename__ = "produto"

    id = db.Column(db.Integer, primary_key=True)
    codigo_pdv = db.Column(db.String(40), unique=True)
    nome = db.Column(db.String(140), nullable=False)
    categoria = db.Column(db.String(60), default="Pratos")
    preco_venda = db.Column(db.Float, default=0.0)
    ativo = db.Column(db.Boolean, default=True)

    ficha = db.relationship(
        "ItemFichaTecnica", back_populates="produto", cascade="all, delete-orphan"
    )

    @property
    def custo_ficha(self):
        """Custo somado dos insumos da ficha técnica."""
        return sum(
            (item.quantidade or 0) * (item.insumo.custo_unitario or 0)
            for item in self.ficha
        )

    @property
    def margem(self):
        if not self.preco_venda:
            return None
        return (self.preco_venda - self.custo_ficha) / self.preco_venda * 100

    def __repr__(self):
        return f"<Produto {self.nome}>"


class ItemFichaTecnica(db.Model):
    """Quanto de cada insumo um produto consome."""

    __tablename__ = "item_ficha_tecnica"

    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produto.id"), nullable=False)
    insumo_id = db.Column(db.Integer, db.ForeignKey("insumo.id"), nullable=False)
    quantidade = db.Column(db.Float, nullable=False, default=0.0)

    produto = db.relationship("Produto", back_populates="ficha")
    insumo = db.relationship("Insumo", back_populates="itens_ficha")

    __table_args__ = (
        db.UniqueConstraint("produto_id", "insumo_id", name="uq_ficha_produto_insumo"),
    )


class Movimentacao(db.Model):
    """
    Registro de toda alteração de estoque.

    Tipos:
      ENTRADA  - recebimento de fornecedor
      VENDA    - baixa automática gerada pela importação de vendas
      PERDA    - quebra, validade vencida, descarte
      AJUSTE   - correção após contagem de inventário
    """

    __tablename__ = "movimentacao"

    TIPOS = ("ENTRADA", "VENDA", "PERDA", "AJUSTE")

    id = db.Column(db.Integer, primary_key=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey("insumo.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    quantidade = db.Column(db.Float, nullable=False)  # positivo entra, negativo sai
    saldo_apos = db.Column(db.Float)
    observacao = db.Column(db.String(240))
    usuario = db.Column(db.String(80), default="sistema")
    criado_em = db.Column(db.DateTime, default=datetime.now, index=True)

    insumo = db.relationship("Insumo", back_populates="movimentacoes")

    def __repr__(self):
        return f"<Mov {self.tipo} {self.quantidade} {self.insumo_id}>"


class LancamentoVenda(db.Model):
    """Venda importada do PDV, antes de virar baixa de insumos."""

    __tablename__ = "lancamento_venda"

    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produto.id"))
    produto_descricao = db.Column(db.String(140))
    quantidade = db.Column(db.Float, nullable=False, default=1.0)
    valor_total = db.Column(db.Float, default=0.0)
    data_venda = db.Column(db.DateTime, default=datetime.now, index=True)
    processado = db.Column(db.Boolean, default=False)
    erro = db.Column(db.String(200))
    lote_importacao = db.Column(db.String(60), index=True)

    produto = db.relationship("Produto")


def registrar_movimentacao(insumo, tipo, quantidade, observacao=None, usuario="sistema"):
    """
    Aplica uma movimentação ao estoque e devolve o registro criado.

    `quantidade` deve vir com sinal: positiva para entrada, negativa para saída.
    O saldo do insumo é atualizado na mesma transação.
    """
    if tipo not in Movimentacao.TIPOS:
        raise ValueError(f"Tipo de movimentação inválido: {tipo}")

    insumo.estoque_atual = round((insumo.estoque_atual or 0) + quantidade, 4)

    mov = Movimentacao(
        insumo=insumo,
        tipo=tipo,
        quantidade=quantidade,
        saldo_apos=insumo.estoque_atual,
        observacao=observacao,
        usuario=usuario,
    )
    db.session.add(mov)
    return mov


def baixar_venda(lancamento, usuario="importacao"):
    """
    Explode um lançamento de venda na ficha técnica do produto e dá baixa
    em cada insumo consumido. Devolve a lista de movimentações criadas.
    """
    produto = lancamento.produto
    if produto is None:
        lancamento.erro = "Produto não encontrado no cadastro"
        return []

    if not produto.ficha:
        lancamento.erro = "Produto sem ficha técnica cadastrada"
        return []

    movimentacoes = []
    for item in produto.ficha:
        consumo = item.quantidade * lancamento.quantidade
        if consumo <= 0:
            continue
        mov = registrar_movimentacao(
            insumo=item.insumo,
            tipo="VENDA",
            quantidade=-consumo,
            observacao=f"Baixa automática · {produto.nome} ×{lancamento.quantidade:g}",
            usuario=usuario,
        )
        movimentacoes.append(mov)

    lancamento.processado = True
    lancamento.erro = None
    return movimentacoes
