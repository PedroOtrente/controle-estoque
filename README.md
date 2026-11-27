# Controle de Estoque com Baixa Automática

Sistema web para controle de estoque de restaurante. A venda de cada prato
dá baixa automática nos insumos, a partir da ficha técnica.

## Como rodar

    pip install -r requirements.txt
    python seed.py      # opcional: carrega dados de exemplo
    python app.py

Abra http://localhost:5000. No celular do estoque, na mesma rede Wi-Fi,
use http://IP-DO-COMPUTADOR:5000.

## Fluxo

1. **Insumos** — cadastre a matéria-prima, com unidade, estoque mínimo e custo.
2. **Fichas** — cadastre cada prato com o código do PDV e monte a ficha
   técnica: quanto de cada insumo uma unidade consome.
3. **Vendas** — importe o CSV exportado do PDV. Cada linha é cruzada com a
   ficha técnica e os insumos são descontados.
4. **Movimentar** — entrada de mercadoria e registro de perdas, pelo celular.
5. **Contagem** — informe o que foi contado; a diferença vira ajuste.
6. **Relatórios** — pratos mais vendidos, consumo, perdas e lista de compras.
7. **Escala** — cadastre a equipe por setor, defina o mínimo de pessoas por
   setor (dia útil e fim de semana) e gere a escala do mês, com download em Excel.

## Regras da escala

- Uma folga por semana (6x1), nunca mais de 6 dias de trabalho seguidos.
- Domingo de folga a cada N semanas (padrão 4, uma vez por mês). Quando a troca para o
  domingo exigiria mais de 6 dias seguidos, a semana recebe a folga normal
  e o domingo — por isso algumas semanas têm duas folgas.
- Folga fixa por funcionário é opcional; sem ela, o sistema distribui as
  folgas para manter o mínimo de cada setor.
- Dias abaixo do mínimo aparecem em destaque: indicam falta de gente, não erro.
- Confirme as regras na convenção coletiva do sindicato local antes de usar.
- Limitação atual: cada mês é gerado assumindo folga no domingo anterior;
  confira a virada de mês contra a escala do mês anterior.

## CSV de vendas

Separador `;` ou `,`. Colunas reconhecidas:
`codigo`, `produto`, `quantidade`, `valor`, `data` (dd/mm/aaaa hh:mm).
O produto é localizado primeiro pelo código do PDV, depois pelo nome.
Vendas sem produto ou sem ficha técnica ficam marcadas como pendentes.
Veja `vendas_exemplo.csv`.

## Banco de dados

SQLite por padrão (`estoque.db`). Para PostgreSQL:

    export DATABASE_URL=postgresql://usuario:senha@host/banco

## Versão em Excel (planilha/)

Para quem prefere trabalhar no Excel, `planilha/` traz a mesma lógica de baixa
por ficha técnica em VBA:

- `ControleEstoque.xlsx` — planilha com dados de exemplo
- `ControleEstoque_vazia.xlsx` — planilha em branco para uso real
- `ControleEstoque.bas` — macros (ProcessarVendas, GerarListaCompras,
  RegistrarEntrada, RegistrarPerda)

Para ativar: abra a planilha, Alt+F11, Arquivo > Importar arquivo, escolha o
`.bas` e salve como `.xlsm`. Instruções completas na aba "Como usar".

## Próximos passos sugeridos

- Autenticação de usuários
- Evitar reimportação do mesmo CSV (hash do arquivo)
- Controle de validade por lote
- Integração direta com a API do PDV em vez de CSV
