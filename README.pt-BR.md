# Tuxedo Finance

Aplicação de finanças pessoais auto-hospedada, para uma pessoa que lança os
dados à mão. Sem conexão com banco. Um lançamento leva poucos segundos, e o
Início responde às perguntas do mês: quanto sobra, para onde foi o dinheiro,
o que vence em breve.

[English](README.md)

![Início: quanto resta para gastar, para onde foi o dinheiro, o que vence, patrimônio e metas](docs/images/pt-br/home.png)

| Planejar | Uma janela |
|---|---|
| ![Planejar: o limite do mês, orçamentos por categoria e metas](docs/images/pt-br/plan.png) | ![A janela do mês, aberta a partir do Início](docs/images/pt-br/window.png) |

As imagens mostram os dados de demonstração da [página pública](site/README.md).

## O que ela faz

- **Lançamentos** em poucos segundos, com parcelas e lançamentos
  recorrentes. Um extrato do banco (OFX ou CSV) pode ser importado e revisado
  linha a linha.
- **Carteira**: contas, cartões e faturas, transferências, investimentos,
  pontos e milhas, e contas em outras moedas.
- **Início**: blocos que você escolhe. Quanto resta para gastar, para onde
  foi o dinheiro, o que vence, patrimônio, metas.
- **Planejar**: um limite para o mês, orçamentos por categoria, metas que
  reservam saldos reais, os próximos meses com uma planilha para simular, e
  um fechamento curto de cada mês.
- Cada objeto abre em uma janela sobre a página, e a página mantém a posição.
- Inglês e português do Brasil.

## Estado

A versão 2.0 é uma aplicação nova sobre as regras financeiras da 1.x: uma
API Django e um cliente React. Ainda não foi lançada. Ela tem um banco de
dados novo, e não há atualização a partir da 1.x. A última versão 1.x é a
tag [`v1.0.0`](https://github.com/HenriqueMayer/TuxedoFinance/tree/v1.0.0).

## Como rodar

Requisitos: Python 3.12 com [uv](https://docs.astral.sh/uv/) e Node.js 22.

```bash
cd web && npm ci && npx vite build
cd ../backend && cp .env.example .env    # defina SECRET_KEY no .env
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Abra http://127.0.0.1:8000.

Com Docker: veja [Operations](docs/operations.md#docker).

## Documentação

A documentação técnica está em inglês:
[Product](docs/product.md) · [Architecture](docs/architecture.md) ·
[Data model](docs/data-model.md) · [Development](docs/development.md) ·
[Operations](docs/operations.md)

## Licença

[PolyForm Noncommercial 1.0.0](LICENSE).
