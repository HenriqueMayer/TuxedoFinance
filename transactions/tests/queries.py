"""SQL write classification shared by ledger/read-model tests."""


def writes(queries):
    return [query['sql'] for query in queries if query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
