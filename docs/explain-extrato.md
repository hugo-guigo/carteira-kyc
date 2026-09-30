# EXPLAIN ANALYZE: extrato e saldo, antes e depois do índice

Medido em 30/09/2026 no Postgres 17 local (docker compose), num PC com Intel i3. Carga sintética:
400 mil lançamentos, dos quais 100 mil numa só conta (a medida), com datas aleatórias em 2 anos.
Tempos são a mediana de 7 execuções seguidas, com o cache já quente.

Reproduzir:

```bash
python manage.py migrate carteira 0003          # estado sem o índice
python manage.py medir_extrato --popular        # grava a carga e mede
python manage.py migrate carteira               # aplica a 0004 (índice do extrato)
python manage.py medir_extrato                  # mede de novo
```

As consultas são as que a API faz, montadas pelo próprio ORM: a primeira página do extrato (21 linhas,
porque a paginação por cursor busca uma a mais para saber se há próxima), uma página de um ano atrás e
a soma da conta.

## Resultado

| Consulta | Antes | Depois |
|---|---|---|
| Extrato, 1ª página | 21,4 ms | 1,01 ms |
| Extrato, página de 1 ano atrás | 17,0 ms | 1,04 ms |
| Saldo (soma da conta) | 15,5 ms | 13,5 ms |

**Antes:** só existia o índice que o Django cria em toda chave estrangeira (`conta_id`). Ele acha as 100 mil
linhas da conta, mas não na ordem da tela: o Postgres lê todas e ordena as 100 mil para devolver 21.

```text
Limit (actual time=19.840..23.616 rows=21)
  ->  Nested Loop
        ->  Gather Merge
              ->  Sort (actual rows=608 loops=3)
                    Sort Key: criado_em DESC, id DESC
                    Sort Method: quicksort  Memory: 3268kB
                    ->  Parallel Bitmap Heap Scan on carteira_lancamento (actual rows=33333 loops=3)
                          ->  Bitmap Index Scan on carteira_lancamento_conta_id_5687fd12 (actual rows=100000)
Execution Time: 24.155 ms
```

**Depois:** com o índice `(conta, criado_em desc, id desc) INCLUDE (valor_centavos)`, as linhas já saem na
ordem e a leitura para na 21ª.

```text
Limit (actual time=0.733..0.827 rows=21)
  Buffers: shared hit=108
  ->  Nested Loop
        ->  Index Scan using lancamento_extrato on carteira_lancamento (actual time=0.017..0.036 rows=21)
              Index Cond: (conta_id = 1004)
        ->  Memoize
              ->  Index Scan using carteira_transacao_pkey on carteira_transacao (rows=1 loops=21)
Execution Time: 1.001 ms
```

Do 1 ms que sobra, o índice do extrato leva 0,04 ms. O resto é a junção com `carteira_transacao`, uma
busca pela chave primária para cada uma das 21 linhas (o tipo da operação mostrado na tela).

A página de um ano atrás teve o mesmo ganho, porque o filtro de data entra na condição do índice
(`conta_id = 1004 AND criado_em < ...`) em vez de filtrar depois de ler.

## Saldo: o índice quase não ajudou, e por quê

```text
Antes:  Bitmap Heap Scan on carteira_lancamento (rows=100000)   Buffers: shared hit=1017   15,5 ms
Depois: Index Only Scan using lancamento_extrato (rows=100000)  Heap Fetches: 0
        Buffers: shared hit=606                                                          13,5 ms
```

Com o `INCLUDE (valor_centavos)`, o saldo passou a ser somado só pelo índice, sem ler a tabela (0 leituras
de heap, 40% menos blocos). Mas continua somando as 100 mil linhas: o tempo acompanha o tamanho do
histórico. É o custo de não ter coluna de saldo. Para contas com histórico longo, a saída seria um saldo
consolidado periódico (um fechamento por dia, por exemplo) somado só aos lançamentos posteriores. Não
está implementado: numa demo com poucas operações por conta, a soma direta é mais simples e não erra.

## Outras decisões da migração 0004

- O índice simples da chave estrangeira foi apagado: o novo começa pela conta e atende as mesmas buscas.
  A ordem na migração é criar o novo e só depois apagar o antigo, para a tabela nunca ficar sem índice.
- `CREATE INDEX CONCURRENTLY` (`AddIndexConcurrently`) não trava as escritas enquanto o índice é
  construído. Por isso a migração roda fora de transação (`atomic = False`).
