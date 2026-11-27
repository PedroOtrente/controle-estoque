"""
Popula o banco com dados de exemplo para demonstração e teste.

Uso:
    python seed.py
"""

from app import app
from escala import Funcionario, MinimoSetor
from models import Insumo, ItemFichaTecnica, Produto, db, registrar_movimentacao

INSUMOS = [
    # nome, categoria, unidade, inicial, minimo, custo
    ("Camarão rosa G", "Proteínas", "kg", 42.0, 25.0, 78.00),
    ("Camarão sete barbas", "Proteínas", "kg", 18.5, 20.0, 46.00),
    ("Filé de tilápia", "Proteínas", "kg", 30.0, 15.0, 32.00),
    ("Salmão fresco", "Proteínas", "kg", 12.0, 14.0, 92.00),
    ("Polvo limpo", "Proteínas", "kg", 8.0, 6.0, 110.00),
    ("Arroz branco", "Mercearia", "kg", 80.0, 40.0, 6.20),
    ("Farinha de mandioca", "Mercearia", "kg", 22.0, 15.0, 8.40),
    ("Leite de coco", "Mercearia", "L", 34.0, 20.0, 12.50),
    ("Azeite de dendê", "Mercearia", "L", 9.0, 8.0, 38.00),
    ("Creme de leite", "Laticínios", "L", 26.0, 18.0, 11.00),
    ("Queijo parmesão", "Laticínios", "kg", 6.5, 5.0, 64.00),
    ("Manteiga", "Laticínios", "kg", 11.0, 8.0, 42.00),
    ("Tomate", "Hortifrúti", "kg", 24.0, 20.0, 7.50),
    ("Cebola", "Hortifrúti", "kg", 31.0, 20.0, 5.80),
    ("Pimentão colorido", "Hortifrúti", "kg", 9.0, 10.0, 9.20),
    ("Limão taiti", "Hortifrúti", "kg", 14.0, 10.0, 6.00),
    ("Coentro", "Hortifrúti", "kg", 2.4, 3.0, 18.00),
    ("Cerveja long neck", "Bebidas", "un", 480.0, 240.0, 4.20),
    ("Refrigerante lata", "Bebidas", "un", 360.0, 200.0, 2.80),
    ("Água mineral 500ml", "Bebidas", "un", 290.0, 150.0, 1.60),
    ("Guardanapo", "Descartáveis", "un", 4200.0, 2000.0, 0.03),
    ("Embalagem delivery", "Descartáveis", "un", 320.0, 400.0, 1.15),
]

PRODUTOS = [
    # codigo, nome, categoria, preco, ficha [(insumo, qtd)]
    ("1001", "Camarão Gratinado", "Pratos", 149.90, [
        ("Camarão rosa G", 0.900), ("Arroz branco", 0.450),
        ("Creme de leite", 0.200), ("Queijo parmesão", 0.080),
        ("Manteiga", 0.060), ("Cebola", 0.120), ("Tomate", 0.100),
    ]),
    ("1002", "Camarão ao Leite de Coco", "Pratos", 159.90, [
        ("Camarão rosa G", 1.000), ("Leite de coco", 0.300),
        ("Arroz branco", 0.450), ("Pimentão colorido", 0.150),
        ("Cebola", 0.120), ("Coentro", 0.020),
    ]),
    ("1003", "Moqueca de Tilápia", "Pratos", 129.90, [
        ("Filé de tilápia", 0.700), ("Leite de coco", 0.250),
        ("Azeite de dendê", 0.060), ("Tomate", 0.200),
        ("Pimentão colorido", 0.150), ("Cebola", 0.150),
        ("Coentro", 0.025), ("Arroz branco", 0.400),
        ("Farinha de mandioca", 0.100),
    ]),
    ("1004", "Salmão Grelhado", "Pratos", 99.90, [
        ("Salmão fresco", 0.380), ("Manteiga", 0.040),
        ("Limão taiti", 0.060), ("Arroz branco", 0.350),
    ]),
    ("1005", "Polvo Grelhado", "Pratos", 169.90, [
        ("Polvo limpo", 0.600), ("Azeite de dendê", 0.050),
        ("Cebola", 0.100), ("Limão taiti", 0.050),
    ]),
    ("2001", "Cerveja Long Neck", "Bebidas", 16.90, [
        ("Cerveja long neck", 1.0),
    ]),
    ("2002", "Refrigerante Lata", "Bebidas", 12.90, [
        ("Refrigerante lata", 1.0),
    ]),
    ("2003", "Água Mineral", "Bebidas", 8.90, [
        ("Água mineral 500ml", 1.0),
    ]),
]


# equipe fictícia, apenas para demonstração
EQUIPE = [
    ("Funcionário 01", "Salão"), ("Funcionário 02", "Salão"), ("Funcionário 03", "Salão"),
    ("Funcionário 04", "Salão"), ("Funcionário 05", "Salão"), ("Funcionário 06", "Salão"),
    ("Funcionário 07", "Salão"), ("Funcionário 08", "Cozinha"), ("Funcionário 09", "Cozinha"),
    ("Funcionário 10", "Cozinha"), ("Funcionário 11", "Cozinha"), ("Funcionário 12", "Bar"),
    ("Funcionário 13", "Bar"), ("Funcionário 14", "Caixa"), ("Funcionário 15", "Caixa"),
]
MINIMOS = {"Salão": (4, 5), "Cozinha": (3, 3), "Bar": (1, 1), "Caixa": (1, 1)}


def popular():
    with app.app_context():
        if Insumo.query.count():
            print("Banco já contém dados. Apague estoque.db para recriar.")
            return

        mapa = {}
        for nome, cat, un, inicial, minimo, custo in INSUMOS:
            insumo = Insumo(
                nome=nome, categoria=cat, unidade=un,
                estoque_minimo=minimo, custo_unitario=custo,
            )
            db.session.add(insumo)
            db.session.flush()
            registrar_movimentacao(
                insumo, "ENTRADA", inicial, "Carga inicial", usuario="seed"
            )
            mapa[nome] = insumo

        for codigo, nome, cat, preco, ficha in PRODUTOS:
            produto = Produto(
                codigo_pdv=codigo, nome=nome, categoria=cat, preco_venda=preco
            )
            db.session.add(produto)
            db.session.flush()
            for insumo_nome, qtd in ficha:
                db.session.add(
                    ItemFichaTecnica(
                        produto_id=produto.id,
                        insumo_id=mapa[insumo_nome].id,
                        quantidade=qtd,
                    )
                )

        for nome, setor in EQUIPE:
            db.session.add(Funcionario(nome=nome, setor=setor))
        for setor, (sem, fds) in MINIMOS.items():
            db.session.add(MinimoSetor(setor=setor, minimo_semana=sem, minimo_fds=fds))

        db.session.commit()
        print(f"{len(INSUMOS)} insumos, {len(PRODUTOS)} produtos e {len(EQUIPE)} funcionários cadastrados.")


if __name__ == "__main__":
    popular()
