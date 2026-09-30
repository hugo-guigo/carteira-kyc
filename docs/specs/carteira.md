# Especificação: carteira (depósito, saque e extrato)

Escrita antes do código. O que mudou durante a implementação e a revisão fica registrado no fim.

## Objetivo

Cliente com KYC aprovado tem uma conta em reais fictícios: deposita, saca e vê o extrato. Nada de
dinheiro de verdade; o depósito só simula uma entrada vinda de fora.

## Regras

1. **Conta só depois do KYC.** A conta nasce na mesma transação da aprovação. Clientes que já estavam
   aprovados ganham a conta numa migração de dados.
2. **Livro-razão em partidas dobradas.** Não existe coluna de saldo. Cada operação é uma `Transacao` com
   dois `Lancamento`: um na conta do cliente e o oposto na conta de sistema "caixa externo". O saldo é a
   soma dos lançamentos da conta. Um trigger do Postgres, adiado para o fim da transação, recusa qualquer
   transação cujos lançamentos não somem zero.
3. **Histórico imutável.** Transações e lançamentos só aceitam INSERT (trigger, como na auditoria do KYC).
   Estorno, se um dia existir, é uma transação nova.
4. **Dinheiro em centavos inteiros** (`bigint`), nunca `float`. Cada operação vai de R$ 0,01 a
   R$ 10.000,00 (limite da demo).
5. **Idempotência.** Depósito e saque exigem o cabeçalho `Idempotency-Key` (8 a 64 caracteres). A chave
   é única por conta (índice único). A mesma chave com o mesmo pedido devolve a transação original
   (200, `Idempotent-Replayed: true`) sem gravar de novo; com outro valor ou outro tipo, 422. Duas
   requisições simultâneas com a mesma chave: uma grava, a outra recebe a original.
6. **Saque não deixa saldo negativo**, nem com dois saques ao mesmo tempo: a linha da conta é travada
   (`select_for_update`) antes de calcular o saldo. Teste com duas threads, como o da decisão do KYC.
7. **Extrato** do mais novo para o mais antigo, com paginação por cursor (`criado_em`, `id`), 20 por página.
8. **Autorização.** Só o dono opera e vê a própria conta; operador e compliance não depositam nem sacam.
   A compliance vê depósitos e saques na trilha de auditoria.
9. **Auditoria.** Todo depósito e saque grava um `EventoAuditoria` na mesma transação. A tabela de
   auditoria ganha uma coluna para a transação (migração de schema), e cada evento aponta para
   exatamente um alvo: uma verificação ou uma transação.

## API

| Rota | Quem | Resposta |
|---|---|---|
| `GET /api/carteira` | cliente | `{saldo_centavos}`; 404 se o KYC ainda não foi aprovado |
| `POST /api/carteira/depositos` | cliente | `{valor_centavos}` + `Idempotency-Key` → 201 (ou 200 na repetição) |
| `POST /api/carteira/saques` | cliente | idem; 409 se o saldo não cobre |
| `GET /api/carteira/extrato` | cliente | lançamentos da conta, cursor em `next` |

## Banco

- Consulta do extrato medida com `EXPLAIN ANALYZE` numa conta com muitos lançamentos, antes e depois de
  um índice composto `(conta, criado_em, id)`, criado numa migração separada. Resultado em
  [docs/explain-extrato.md](../explain-extrato.md).

## Frontend

- Na área do cliente, depois do KYC aprovado: saldo, um campo de valor com os botões Depositar e Sacar,
  e o extrato com "carregar mais".
- A chave de idempotência é gerada quando a pessoa clica e reaproveitada se a mesma operação for
  repetida depois de uma falha de rede. Só uma operação bem-sucedida (ou um valor novo) gera chave nova.
- Valor digitado em reais ("12,34") vira centavos sem passar por `float`.

## Testes

- pytest-django: partidas dobradas e imutabilidade no banco, idempotência (repetida, conflitante e
  simultânea), saque sem saldo, corrida de dois saques, autorização por papel e por dono, auditoria.
- Vitest: conversão de reais para centavos, formulário (chave reaproveitada depois de erro de rede).
- Playwright: o fluxo de ponta a ponta ganha depósito, saque e extrato.
- Bug achado durante o trabalho: primeiro um teste que falha, depois a correção.

## Revisão

O que mudou em relação à especificação, o que foi recusado e o que foi corrigido.

### Recusado

- *Trigger que impede saldo negativo no banco.* Seria uma soma do histórico inteiro da conta a cada
  lançamento, e mesmo assim não protegeria de dois saques simultâneos: no nível de isolamento padrão do
  Postgres (READ COMMITTED), cada transação confere o saldo sem ver o saque da outra, que ainda não fez
  COMMIT. Quem garante o saldo é a trava da linha da conta (`select_for_update`), e o teste de corrida
  prova isso: sem a trava, ele falhou nas 3 execuções.
- *Saldo consolidado (fechamento periódico).* O `EXPLAIN ANALYZE` mostrou que o saldo continua somando o
  histórico todo mesmo com o índice. A saída seria guardar um fechamento por dia e somar só o que veio
  depois. Ficou registrado como limitação: numa demo com poucas operações por conta, a soma direta é mais
  simples e não erra.

### Corrigido

- *O caixa externo dependia de uma linha criada pela migração.* Os testes de corrida (escritos antes da
  correção) falharam: testes com threads limpam as tabelas com TRUNCATE no fim, e a linha sumia para os
  testes seguintes. Isso mostrou que o código dependia de um dado que alguém poderia apagar. Agora o
  serviço busca ou cria o caixa, e o índice único parcial impede que existam dois.
- *O teste de imutabilidade não testava o banco.* O `delete()` do ORM parava antes, no `PROTECT` das
  chaves estrangeiras, e o trigger nunca era exercitado. O teste passou a mandar o DELETE em SQL direto.
- *O extrato ficaria preso ao endereço absoluto da API.* O link da próxima página vem montado pelo
  backend; atrás do proxy da nuvem ele pode sair com http em vez de https. O frontend usa só o cursor.
- *Aviso do lint no React* (`setState` dentro de efeito): a carga inicial virou uma cadeia de promessas.
- *O primeiro deploy derrubou a API por 3,5 minutos.* O script de deploy empacotava uma lista fixa de
  pastas do backend, e o app `carteira` não estava nela: o Lambda subiu sem o módulo
  (`ImportModuleError`) e a migração falhou. Os testes do CI passaram porque rodam o código do
  repositório, não o pacote. O script passou a empacotar todo pacote Python do backend, e o deploy
  seguinte (com migração no Neon e teste de fumaça de 15 itens) passou.

### Mudou na implementação

- O índice do extrato ganhou `INCLUDE (valor_centavos)`, para o saldo sair só do índice, e o índice
  simples da chave estrangeira foi apagado por ficar redundante. A migração cria o novo antes de apagar o
  antigo, com `CREATE INDEX CONCURRENTLY`.
- Os testes de corrida e o de idempotência simultânea foram conferidos quebrando o código de propósito:
  sem a trava da conta, ou sem o tratamento do índice único, cada um falhou nas 3 execuções. No frontend,
  o teste da chave reaproveitada falhou quando a reutilização foi desligada.
