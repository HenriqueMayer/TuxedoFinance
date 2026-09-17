<p align="center">
  <img src="static/brand/tuxedo-mark-256.png" width="144" alt="Logo do Tuxedo Finance">
</p>

<h1 align="center">Tuxedo Finance</h1>

<p align="center">
  <strong>Finanças pessoais, simplificadas.</strong><br>
  Uma aplicação Django de uso local para entender o fluxo de caixa, despesas
  recorrentes, faturas, investimentos e o destino do dinheiro a cada mês.
</p>

<p align="center">
  <a href="https://github.com/HenriqueMayer/TuxedoFinance/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/HenriqueMayer/TuxedoFinance/ci.yml?branch=main&amp;style=for-the-badge&amp;label=CI&amp;labelColor=101E18&amp;color=176B52" alt="Status da CI"></a>
  <img src="https://img.shields.io/badge/version-0.2.0-B88A59?style=for-the-badge&amp;labelColor=101E18" alt="Version 0.2.0">
  <img src="https://img.shields.io/badge/Python-3.12-176B52?style=for-the-badge&amp;labelColor=101E18" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Django-6.0-1A2E26?style=for-the-badge&amp;labelColor=101E18" alt="Django 6.0">
  <img src="https://img.shields.io/badge/UI-EN%20%7C%20PT--BR-B88A59?style=for-the-badge&amp;labelColor=101E18" alt="Interface em inglês e português brasileiro">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-PolyForm%20Noncommercial-7C5C13?style=for-the-badge&amp;labelColor=101E18" alt="Licença PolyForm Noncommercial"></a>
</p>

O Tuxedo Finance substitui uma planilha improvisada por registros financeiros
normalizados e categorizados. Foi desenvolvido para uso pessoal e operação
local simples, mantendo o banco de dados sob controle de quem administra a
instalação. Não é uma plataforma SaaS.

## Prévia da interface

<table>
  <tr>
    <td width="96" align="center">
      <a href="https://henriquemayer.github.io/TuxedoFinance/">
        <img src="static/brand/tuxedo-mark-256.png" width="72" alt="Abrir a prévia da interface do Tuxedo Finance">
      </a>
    </td>
    <td>
      <strong>Conheça o Tuxedo Finance antes de instalar.</strong><br>
      Explore o tour bilíngue pelo Painel, Relatórios, Transações,
      Bancos e Investimentos, com o Painel nos temas claro e escuro.<br><br>
      <a href="https://henriquemayer.github.io/TuxedoFinance/"><strong>Abrir a prévia da interface →</strong></a>
    </td>
  </tr>
</table>

> A prévia usa dados sintéticos e funciona como um tour estático. Não há login,
> servidor público ou persistência; nenhuma informação é salva.

[English](README.md) · [Português brasileiro](README.pt-BR.md)

## 🚀 Início rápido

### Docker

O suporte a Docker está em `Unreleased`; a versão v0.2.0 existente não tem
imagem publicada. Em um checkout que contenha estes arquivos:

```bash
docker build -t tuxedo-finance:local .
image=tuxedo-finance:local
(
  umask 077
  set -o noclobber
  docker run --rm --entrypoint python -e TUXEDO_IMAGE="$image" "$image" -c \
    'import os,secrets; print("TUXEDO_IMAGE="+os.environ["TUXEDO_IMAGE"]); print("SECRET_KEY="+secrets.token_urlsafe(64))' > .env.docker
)
docker compose --env-file .env.docker up -d --wait
```

Abra o [Tuxedo Finance](http://127.0.0.1:8000/). O Docker mantém o SQLite em um
volume nomeado e usa uma chave de assinatura persistente. O comando de
configuração recusa substituir um `.env.docker` existente. Consulte o
[guia de Docker](docs/docker.md), em inglês, para usar imagens publicadas sem
clone, configurar, atualizar e fazer backup/restauração. A instalação sem clone
fica disponível nas releases que incluam os arquivos de instalação Docker.

### Python e uv

Requer Python 3.12 e [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/HenriqueMayer/TuxedoFinance.git
cd TuxedoFinance
uv sync --locked
printf 'SECRET_KEY=%s\n' "$(uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')" > .env
uv run python manage.py migrate
uv run python manage.py runserver
```

Abra <http://127.0.0.1:8000/>, crie uma conta de usuário e cadastre um banco e
uma conta bancária antes de registrar a primeira transação.

Os arquivos gerados `.env` e `db.sqlite3` são ignorados pelo Git. Mantenha-os
privados e inclua o banco em uma rotina de backup protegida. Para iniciar a
aplicação novamente, execute apenas:

```bash
uv run python manage.py runserver
```

## 🎥 Tutoriais

Tutoriais atualizados serão disponibilizados nos dois idiomas:

| Idioma | Tutorial |
|---|---|
| 🇧🇷 Português (Brasil) | _link_TODO_ |
| 🇺🇸 Inglês | _link_TODO_ |

## ✨ Funcionalidades

| | O que faz |
|---|---|
| 📊 **Painel e projeções** | Separa saldo atual, receitas, despesas, investimentos, faturas abertas e saldo projetado para o fim do mês. |
| 🧾 **Transações** | Registra receitas e despesas com categorias, meios de pagamento, recorrências, parcelamentos, busca, ordenação e exportação CSV. |
| 🏦 **Bancos** | Organiza bancos, contas por moeda, PIX, cartões de débito e crédito, ciclos de fatura, transferências próprias, programas de pontos e câmbio. |
| 📈 **Relatórios** | Usa gráficos SVG responsivos calculados no servidor, com resumos acessíveis e atualizações HTMX, sem biblioteca de gráficos no navegador. |
| 💼 **Investimentos** | Registra aportes, resgates, rendimentos, produtos, ativos, quantidades, preços, taxas e evidências de conversão histórica. |
| 🧮 **Simulador salarial** | Estima o salário líquido CLT ou manual e prepara um orçamento mensal sem guardar os cenários. |
| 🌍 **Localização** | Oferece inglês e português brasileiro independentemente da moeda de apresentação: BRL, USD, EUR, GBP, JPY ou CHF. |
| 🌗 **Temas acessíveis** | Usa tipografia Inter e temas claro/escuro com cores distintas para receitas, despesas, investimentos, parcelamentos, recorrências e lançamentos avulsos. |
| 🧭 **Fluxos direcionados** | Revela campos e filtros conforme a opção ou categoria escolhida, mantendo validação no servidor e funcionamento sem JavaScript. |

> **O significado financeiro importa:** o saldo atual representa o dinheiro
> realizado nas contas até hoje. A projeção considera o fechamento do mês.
> Compras no cartão pertencem ao mês da fatura; a saída de caixa ocorre no
> vencimento.

<details>
<summary><strong>🎨 Identidade visual</strong></summary>

<br>

A interface segue o design system do Tuxedo Finance: bases discretas, tipografia
com contraste, ações em caramelo e cores com significado financeiro.

| Token | Cor | Uso |
|---|---:|---|
| `cream` | `#FAF8F3` | Fundo claro |
| `forest` | `#1A2E26` | Texto principal e superfícies escuras |
| `forest-deep` | `#101E18` | Fundo escuro |
| `caramel` | `#B88A59` | Marca e ações principais |
| `income` | `#176B52` | Receitas e entradas nas contas |
| `expense` | `#B42318` | Despesas, valores negativos e ações destrutivas |
| `investment` | `#7C5C13` | Investimentos |
| `installment` | `#6B4E8A` | Parcelamentos |
| `fixed` | `#A65300` | Recorrências fixas |
| `oneoff` | `#52605A` | Lançamentos avulsos |

O tema escuro usa as variantes mais claras descritas no catálogo, preservando
contraste e significado financeiro. O catálogo está em
[`docs/design-system.html`](docs/design-system.html), com orientações em
[`docs/frontend.md`](docs/frontend.md).

</details>

## 🧭 Como as partes se conectam

```text
Usuários ──► Bancos ──► Transações ──► Painel e Relatórios
                │             │
                └─────────────┴──────► Investimentos
```

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12 · Django 6.0 · autenticação nativa |
| Frontend | Templates Django · Tailwind CSS · melhorias com JavaScript e HTMX |
| Gráficos | SVG calculado no servidor |
| Banco de dados | SQLite em modo WAL |
| Dependências | `uv` com lockfile versionado |

## ⚙️ Configuração

A configuração vem do `.env` local ou das variáveis do processo. As variáveis
do processo têm prioridade.

| Variável | Finalidade | Padrão |
|---|---|---|
| `SECRET_KEY` | Chave de assinatura Django | Obrigatória |
| `DEBUG` | Modo de depuração | `True` |
| `ALLOWED_HOSTS` | Nomes de host separados por vírgula | `localhost,127.0.0.1` |
| `HTTPS` | Cookies seguros, redirecionamento HTTPS e HSTS | `False` |
| `ALLOW_SIGNUPS` | Permite novos cadastros | `True` |
| `TUXEDO_DATA_DIR` | Diretório de `db.sqlite3` | Raiz do projeto |
| `TUXEDO_ENV_FILE` | Arquivo alternativo de configuração | `.env` na raiz |
| `LOG_LEVEL` | Nível dos logs | `INFO` |

Use `ALLOW_SIGNUPS=False` após criar sua conta para impedir novos cadastros.
Ative `HTTPS=True` somente quando a aplicação estiver servida por TLS.

## ✅ Verificações de desenvolvimento

```bash
uv sync --locked
uv run python manage.py check
uv run python manage.py test
npm ci
npm audit --audit-level=high
npm run build:css
```

O executor de navegador cria seu próprio banco temporário e servidor local:

```bash
npx playwright install chromium
npm run test:e2e
npm run test:e2e -- --docker-image tuxedo-finance:local
npm run test:preview
```

A opção Docker também cria e remove seu volume temporário. Ambas ignoram um
`E2E_BASE_URL` existente e nunca usam o banco do responsável pela instalação.
Consulte [`CONTRIBUTING.md`](CONTRIBUTING.md) para verificações Django isoladas,
CI e o fluxo completo de desenvolvimento.

Para regenerar as imagens do tour com dados sintéticos descartáveis, execute
`npm run preview:capture`. O comando usa um banco temporário protegido e não
grava no `db.sqlite3` da instalação.

## 📚 Documentação

Os guias técnicos são mantidos em inglês.

- [Índice](docs/README.md) — arquitetura, dados, frontend e aplicativos
- [Changelog](CHANGELOG.md) — mudanças por versão
- [Versionamento e releases](docs/versioning.md) — SemVer, validação e publicação
- [Requisitos do produto](docs/product-requirements.md) — comportamento aprovado
- [Operações](docs/operations.md) — dependências e backup/restauração SQLite
- [Cobertura](docs/coverage-baseline.md) — política e comandos
- [Coleções de categorias](docs/category-collections/) — exemplos em inglês e português

## 🔐 Controle dos dados

Cada instalação tem um banco independente. Os registros financeiros ficam no
SQLite local e não são incluídos no repositório. Quem administra a instalação
cuida de acesso, backups, retenção e testes de restauração. Antes de atualizar
ou realizar manutenção que possa afetar os dados, interrompa as gravações e
siga o procedimento de backup.

## 🤝 Contribuições

Contribuições, relatos de problemas e sugestões são bem-vindos. Leia
[`CONTRIBUTING.md`](CONTRIBUTING.md) antes de propor uma alteração.

## 📄 Licença

Copyright (c) 2026 Henrique Mayer.

Licenciado sob a
[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0).
Uso pessoal e outros usos não comerciais são permitidos. Uso comercial e revenda
não são permitidos; consulte [`LICENSE`](LICENSE) para os termos completos.
