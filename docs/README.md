# Documentation

Current reference of Tuxedo Finance 2.0. Each subject has one file. A change
of behavior updates its file in the same change.

| Subject | File |
|---|---|
| What the product is and what each area does | [Product](product.md) |
| Repository layout, the API, the client and the test policy | [Architecture](architecture.md) |
| Records, their owner applications and the financial rules | [Data model](data-model.md) |
| Setup, commands and checks | [Development](development.md) |
| Settings, data, backup and Docker | [Operations](operations.md) |

The interface decisions are in [`web/DESIGN.md`](../web/DESIGN.md). The API
reference is the OpenAPI schema: `/api/openapi.json` on a running server,
or `web/src/api/schema.json` in the repository.

History is not kept here. A release has one entry in the
[changelog](../CHANGELOG.md). The 1.x documentation is in the tag `v1.0.0`.
