// Ponta a ponta, com backend e banco de verdade: cliente se cadastra e envia o KYC, operador aprova,
// cliente deposita e saca na carteira, compliance vê a decisão e o depósito na auditoria.
// Com PRINTS=1 grava as telas em ../docs/prints.
import { expect, test, type Page } from '@playwright/test'

const senhaDemo = process.env.DEMO_SENHA ?? ''
const prints = process.env.PRINTS === '1'

async function print(page: Page, nome: string) {
  if (prints) await page.screenshot({ path: `../docs/prints/${nome}.png`, fullPage: true })
}

async function entrar(page: Page, email: string, senha: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Senha').fill(senha)
  await page.getByRole('button', { name: 'Entrar' }).click()
}

test('cliente envia, operador aprova, cliente usa a carteira e compliance audita', async ({ page }) => {
  test.skip(!senhaDemo, 'defina DEMO_SENHA e rode python manage.py popular_demo')
  const marca = Date.now()
  const email = `e2e-${marca}@teste.local`
  const nome = `Cliente E2E ${marca}`
  const senhaCliente = 'senha-ficticia-e2e-4821'

  // 1. Cadastro e envio do KYC (dados fictícios)
  await page.goto('/')
  await print(page, '1-entrar')
  await page.getByRole('tab', { name: 'Criar conta' }).click()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Nome').fill(nome)
  await page.getByLabel('Senha').fill(senhaCliente)
  await page.getByRole('button', { name: 'Criar conta' }).click()
  await page.getByLabel('Nome completo').fill(nome)
  await page.getByLabel('CPF').fill('529.982.247-25')
  await page.getByLabel('Data de nascimento').fill('1998-03-14')
  await page.getByLabel(/Documento/).setInputFiles({
    name: 'documento-ficticio.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n% ficticio\n'),
  })
  await print(page, '2-cliente-formulario')
  await page.getByRole('button', { name: 'Enviar para análise' }).click()
  await expect(page.getByText('Em análise')).toBeVisible()
  await print(page, '3-cliente-em-analise')
  await page.getByRole('button', { name: 'Sair' }).click()

  // 2. Operador aprova este pedido
  await entrar(page, 'operador@demo.local', senhaDemo)
  const pedido = page.locator('article', { hasText: nome })
  await expect(pedido).toBeVisible()
  await print(page, '4-operador-fila')
  await pedido.getByRole('button', { name: 'Aprovar' }).click()
  await expect(pedido).toHaveCount(0)
  await page.getByRole('button', { name: 'Sair' }).click()

  // 3. Cliente aprovado usa a carteira: deposita, saca, tenta sacar mais do que tem
  await entrar(page, email, senhaCliente)
  const saldo = page.getByTestId('saldo')
  await expect(saldo).toHaveText(/R\$\s0,00/)
  const valor = page.getByLabel('Valor (R$)')
  await valor.fill('100,00')
  await page.getByRole('button', { name: 'Depositar' }).click()
  await expect(saldo).toHaveText(/R\$\s100,00/)
  await valor.fill('30')
  await page.getByRole('button', { name: 'Sacar' }).click()
  await expect(saldo).toHaveText(/R\$\s70,00/)
  await valor.fill('1.000')
  await page.getByRole('button', { name: 'Sacar' }).click()
  await expect(page.getByRole('alert')).toHaveText('Saldo insuficiente.')
  await expect(saldo).toHaveText(/R\$\s70,00/)
  await expect(page.getByRole('row')).toHaveCount(3)  // cabeçalho + depósito + saque
  await print(page, '6-cliente-carteira')
  await page.getByRole('button', { name: 'Sair' }).click()

  // 4. Compliance vê a aprovação e o depósito na trilha
  await entrar(page, 'compliance@demo.local', senhaDemo)
  await expect(page.getByRole('cell', { name: 'Aprovou verificação' }).first()).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Depositou' }).first()).toBeVisible()
  await print(page, '5-compliance-auditoria')
})
