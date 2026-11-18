# Receita: novo endpoint em um módulo existente

Exemplo de referência: `app/user/` (CRUD) e `app/auth/` (login/me). Nomes abaixo são ilustrativos.

1. **Schema** (`schemas.py`): classe Pydantic v2 de entrada e de saída. Saída com `model_config = ConfigDict(from_attributes=True)`. Chaves novas em snake_case (ADR 0001). Validações de domínio com `field_validator`.
2. **Repository** (`repository.py`): método com `select()`/`where()`; sem commit. Se retorna lista, ordene de forma determinística.
3. **Service** (`services.py`): regra de negócio, erros de domínio (`ExceptionData` + exceção de `common.errors`, `is_expected=True`), `commit` ao fim da operação, `rollback` em `IntegrityError`.
4. **Dependência** (`deps.py`): se o service ainda não tem factory, siga `get_user_service`.
5. **Rota** (`routes.py`): `@router.<verbo>(..., response_model=..., status_code=...)`, parâmetros com `Annotated[...]`, docstring de uma linha (aparece no OpenAPI). Autorização: `CurrentUser` (autenticado) ou `AdminUser` (`interno_adm`); para "próprio ou admin" reutilize o padrão de `_ensure_self_or_admin`.
6. **Registro**: o router do módulo já é incluído em `app/main.py:create_app()`; módulo novo exige `app.include_router(...)` ali e import do model em `main.py` e `migrations/env.py`.
7. **Testes** (`tests/`): use o `client` e as fixtures de `tests/conftest.py` (SQLite em memória com `StaticPool`, `make_user`, `login`, `admin_headers`). Cubra: sucesso, validação (422), autenticação (401), autorização (403), conflito (409) e não encontrado (404) quando aplicável.
8. **OpenAPI**: `make -C apps/ressonant_backend export-openapi`.
9. **Gate**: `make test APP=backend`, `make -C apps/ressonant_backend lint`, `make -C apps/ressonant_backend check-structure`.

## Armadilhas

- `UserRepository.get_by_id` valida UUID antes de consultar; id malformado vira 404, não 500. Mantenha esse comportamento em buscas por id.
- E-mail é normalizado em minúsculas no schema e no login.
- `status_ativo=False` é soft delete; leitura de usuário inativo continua possível para admin, mas o usuário inativo perde acesso.
- Não exponha `cpf` em rota nova sem decisão explícita (hoje ele é devolvido em `UserResponse`; é dado pessoal sob LGPD).
