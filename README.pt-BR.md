[English](README.md) · [Português (Brasil)](README.pt-BR.md)

<h1><img src="docs/assets/readme-cover.svg" alt="Tuxedo Finance" width="1240"></h1>

<a id="-controle-dos-dados"></a>

Receitas, despesas, contas, cartões e investimentos em um app local.
Você instala no seu computador e usa em português ou inglês, com tema claro ou
escuro. Seus registros ficam na sua instalação.

<a id="prévia-da-interface"></a>

<p align="center">
  <a href="https://henriquemayer.github.io/TuxedoFinance/pt-br/"><img src="docs/assets/preview-link.svg" width="320" height="64" alt="Abrir o preview da interface do Tuxedo Finance"></a>
</p>

<p>
  <a href="https://github.com/HenriqueMayer/TuxedoFinance/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/HenriqueMayer/TuxedoFinance/ci.yml?branch=main&amp;style=flat&amp;label=CI&amp;labelColor=1A2E26&amp;color=176B52" alt="Status da integração contínua"></a>
  <img src="https://img.shields.io/badge/version-0.10.0-B88A59?style=flat&amp;labelColor=1A2E26" alt="Versão 0.10.0">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-B88A59?style=flat&amp;labelColor=1A2E26" alt="Licença PolyForm Noncommercial"></a>
</p>

[Instalação](#instalação) · [Documentação](docs/README.md) · [Alterações](CHANGELOG.md)

<a id="-funcionalidades"></a>
<a id="cinco-áreas"></a>

## O que tem no app

| Área | O que você pode fazer |
|---|---|
| **Início** | Conferir saldos, compromissos próximos e relatórios financeiros. |
| **Transações** | Registrar receitas e despesas, dividir categorias, gerenciar recorrências e parcelas, exportar CSV. |
| **Contas** | Organizar contas bancárias, PIX, cartões, faturas, transferências e fidelidade. |
| **Investimentos** | Acompanhar posições, movimentações, cofrinhos e preços datados. |
| **Planejar** | Definir limites por categoria, reservar saldos existentes para metas e comparar simulações. |

**No código ainda não publicado:** o [assistente Tuxedo](docs/apps/assistant.md)
opcional pode consultar suas finanças salvas, simular cenários e preparar alterações
para sua confirmação. A conexão com o ChatGPT vem desativada; quando habilitada,
registros relevantes e o histórico necessário da conversa são enviados à OpenAI.
O Open Finance permanece no [roadmap](docs/roadmap.md#personal-open-finance-study).

<a id="-instalação-inicial"></a>

## Instalação

### Docker

Requer Docker Engine 28+ (ou Docker Desktop atualizado), Compose v2+ e um
shell POSIX (WSL no Windows). Não é necessário clonar o repositório nem instalar
Python ou Node.js no computador.
Baixe [compose.yaml](https://github.com/HenriqueMayer/TuxedoFinance/releases/download/v0.10.0/compose.yaml)
e [docker.env.example](https://github.com/HenriqueMayer/TuxedoFinance/releases/download/v0.10.0/docker.env.example)
da release **v0.10.0** para uma nova pasta de instalação. Abra um terminal
nessa pasta e execute:

```bash
image=ghcr.io/henriquemayer/tuxedofinance:v0.10.0
docker pull "$image"
(
  umask 077
  set -o noclobber
  docker run --rm --entrypoint python -e TUXEDO_IMAGE="$image" "$image" -c \
    'import os,secrets; print("TUXEDO_IMAGE="+os.environ["TUXEDO_IMAGE"]); print("SECRET_KEY="+secrets.token_urlsafe(64))' > .env.docker
)
docker compose --env-file .env.docker up -d --wait
```

Abra [127.0.0.1:8000](http://127.0.0.1:8000/). A configuração preserva um
`.env.docker` existente; mantenha sua chave de assinatura, a pasta de instalação
e o volume de dados nas atualizações. Consulte o [guia de Docker](docs/docker.md)
para configuração, atualizações e backups. Esses comandos instalam a release
publicada; alterações do checkout exigem uma
[compilação local da imagem](docs/docker.md#build-from-a-checkout).

<a id="código-em-desenvolvimento"></a>

<a id="python-e-uv"></a>

**Python 3.12 + [uv](https://docs.astral.sh/uv/getting-started/installation/):**
para uma nova instalação a partir do código:

```bash
git clone https://github.com/HenriqueMayer/TuxedoFinance.git
cd TuxedoFinance
uv sync --locked
uv run python scripts/init_local.py
uv run python manage.py migrate
uv run python manage.py runserver
```

Abra [127.0.0.1:8000](http://127.0.0.1:8000/), crie um usuário e adicione um banco
e uma conta bancária. Node.js é necessário apenas nas ferramentas de desenvolvimento.
Antes de atualizar uma instalação existente, siga o
[procedimento de backup e migração](docs/operations.md#updating-a-native-installation).
Preserve o banco de dados e a chave de assinatura.

<a id="dados-de-demonstração-opcionais"></a><a id="-configuração"></a><a id="-desenvolvimento"></a><a id="-documentação"></a><a id="-contribuição"></a>

## Guias

[Configuração e operação](docs/operations.md) · [Dados de demonstração](docs/demo-data.md) ·
[Design system](docs/design-system.html) · [Como contribuir](CONTRIBUTING.md) ·
[Roadmap](docs/roadmap.md) · [Segurança](SECURITY.md)

<a id="-tecnologia"></a>

Desenvolvido com **Django, SQLite, HTMX e assets servidos localmente**.
O [índice da documentação](docs/README.md) reúne os detalhes técnicos e financeiros,
em inglês.

---

<a id="-licença"></a>

Copyright © 2026 Henrique Mayer. [PolyForm Noncommercial 1.0.0](LICENSE).
