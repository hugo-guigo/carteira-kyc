import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../App'
import { formatarCentavos, reaisParaCentavos } from '../dinheiro'
import { logarComo, perfil, servidorFalso, verificacao } from './servidorFalso'

describe('dinheiro', () => {
  it('converte reais digitados em centavos sem ponto flutuante', () => {
    expect(reaisParaCentavos('12')).toBe(1200)
    expect(reaisParaCentavos('12,3')).toBe(1230)
    expect(reaisParaCentavos('0,10')).toBe(10)
    expect(reaisParaCentavos('1.234,56')).toBe(123456)
    expect(reaisParaCentavos('R$ 10.000,00')).toBe(1000000)
    expect(reaisParaCentavos(' 0,07 ')).toBe(7)
  })

  it('recusa o que é ambíguo ou inválido', () => {
    for (const texto of ['', '0', '0,00', '12.5', '1,234', '12,345', '-5', 'abc', '1.23,00', '99999999']) {
      expect(reaisParaCentavos(texto), texto).toBeNull()
    }
  })

  it('formata centavos como reais', () => {
    expect(formatarCentavos(123456).replace(/\s/g, ' ')).toBe('R$ 1.234,56')
  })
})

const lancamento = (id: number, tipo: 'deposito' | 'saque', valor: number) =>
  ({ id, transacao: `t${id}`, tipo, valor_centavos: valor, criado_em: '2026-09-30T10:00:00-03:00' })

function clienteAprovado(rotas: Record<string, unknown> = {}) {
  logarComo()
  return servidorFalso({
    'GET /api/contas/eu': { corpo: perfil('cliente') },
    'GET /api/kyc/minha': { corpo: verificacao({ status: 'aprovada' }) },
    'GET /api/carteira': { corpo: { saldo_centavos: 5000 } },
    'GET /api/carteira/extrato': { corpo: { next: null, results: [lancamento(1, 'deposito', 5000)] } },
    ...rotas,
  } as Parameters<typeof servidorFalso>[0])
}

const chaveDe = (init: RequestInit) => new Headers(init.headers).get('Idempotency-Key')

describe('carteira', () => {
  it('cliente sem KYC aprovado não vê a carteira', async () => {
    logarComo()
    servidorFalso({
      'GET /api/contas/eu': { corpo: perfil('cliente') },
      'GET /api/kyc/minha': { corpo: verificacao() },
    })
    render(<App />)
    expect(await screen.findByText('Em análise')).toBeInTheDocument()
    expect(screen.queryByText('Carteira')).not.toBeInTheDocument()
  })

  it('mostra saldo e extrato, deposita com chave de idempotência e atualiza', async () => {
    const chamadas = clienteAprovado({
      'POST /api/carteira/depositos': { status: 201, corpo: { id: 'x', tipo: 'deposito', valor_centavos: 2550, saldo_centavos: 7550 } },
    })
    render(<App />)
    expect(await screen.findByTestId('saldo')).toHaveTextContent('50,00')
    expect(screen.getByText('Depósito')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Valor (R$)'), '25,50')
    await userEvent.click(screen.getByRole('button', { name: 'Depositar' }))
    expect(await screen.findByTestId('saldo')).toHaveTextContent('75,50')
    const deposito = chamadas.find(c => c.rota === 'POST /api/carteira/depositos')!
    expect(JSON.parse(deposito.init.body as string)).toEqual({ valor_centavos: 2550 })
    expect(chaveDe(deposito.init)).toMatch(/^[0-9a-f-]{36}$/)
    expect(screen.getByLabelText('Valor (R$)')).toHaveValue('')
  })

  it('valor inválido é barrado no navegador, sem chamar a API', async () => {
    const chamadas = clienteAprovado()
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Valor (R$)'), '12.5')
    await userEvent.click(screen.getByRole('button', { name: 'Sacar' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Informe um valor')
    expect(chamadas.some(c => c.rota.startsWith('POST'))).toBe(false)
  })

  it('depois de falha de rede, repetir a operação reaproveita a chave', async () => {
    let tentativas = 0
    const chamadas = clienteAprovado({
      'POST /api/carteira/saques': () => {
        tentativas += 1
        if (tentativas === 1) throw new TypeError('Failed to fetch')  // a resposta se perdeu no caminho
        return { status: 200, corpo: { id: 'x', tipo: 'saque', valor_centavos: 1000, saldo_centavos: 4000 } }
      },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Valor (R$)'), '10')
    await userEvent.click(screen.getByRole('button', { name: 'Sacar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('não será feita duas vezes')
    await userEvent.click(screen.getByRole('button', { name: 'Sacar' }))
    expect(await screen.findByTestId('saldo')).toHaveTextContent('40,00')
    const saques = chamadas.filter(c => c.rota === 'POST /api/carteira/saques')
    expect(saques).toHaveLength(2)
    expect(chaveDe(saques[1].init)).toBe(chaveDe(saques[0].init))
  })

  it('saldo insuficiente mostra a mensagem, e a próxima operação usa chave nova', async () => {
    const chamadas = clienteAprovado({
      'POST /api/carteira/saques': { status: 409, corpo: { detail: 'saldo insuficiente' } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Valor (R$)'), '999')
    await userEvent.click(screen.getByRole('button', { name: 'Sacar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Saldo insuficiente.')
    await userEvent.click(screen.getByRole('button', { name: 'Sacar' }))
    const saques = chamadas.filter(c => c.rota === 'POST /api/carteira/saques')
    expect(chaveDe(saques[1].init)).not.toBe(chaveDe(saques[0].init))
  })

  it('carrega a página seguinte do extrato só com o cursor', async () => {
    const chamadas = clienteAprovado({
      'GET /api/carteira/extrato': { corpo: {
        next: 'http://api.exemplo/api/carteira/extrato?cursor=abc', results: [lancamento(2, 'saque', -1000)] } },
      'GET /api/carteira/extrato?cursor=abc': { corpo: { next: null, results: [lancamento(1, 'deposito', 5000)] } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Carregar mais' }))
    expect(await screen.findByText('Depósito')).toBeInTheDocument()
    expect(screen.getByText('Saque')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Carregar mais' })).not.toBeInTheDocument()
    expect(chamadas.map(c => c.rota)).toContain('GET /api/carteira/extrato?cursor=abc')
  })
})
