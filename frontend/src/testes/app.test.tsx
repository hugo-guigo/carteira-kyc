import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../App'
import { requisitar } from '../api'
import { cpfValido, formatarCpf } from '../cpf'
import { logarComo, perfil, servidorFalso, verificacao } from './servidorFalso'

describe('cpf', () => {
  it('valida pelos dígitos verificadores, igual ao backend', () => {
    expect(cpfValido('529.982.247-25')).toBe(true)
    expect(cpfValido('529.982.247-24')).toBe(false)
    expect(cpfValido('111.111.111-11')).toBe(false)
    expect(formatarCpf('52998224725')).toBe('529.982.247-25')
  })
})

describe('login', () => {
  it('entra e mostra o painel do papel da pessoa', async () => {
    servidorFalso({
      'POST /api/token': { corpo: { access: 'a', refresh: 'r' } },
      'GET /api/contas/eu': { corpo: perfil('operador') },
      'GET /api/kyc/fila?status=pendente': { corpo: { count: 0, results: [] } },
    })
    render(<App />)
    await userEvent.type(screen.getByLabelText('Email'), 'operador@demo.local')
    await userEvent.type(screen.getByLabelText('Senha'), 'qualquer')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText('Fila de verificação')).toBeInTheDocument()
    expect(screen.getByText('Nome operador · Operador')).toBeInTheDocument()
  })

  it('senha errada mostra mensagem e não guarda token', async () => {
    servidorFalso({ 'POST /api/token': { status: 401, corpo: { detail: 'No active account' } } })
    render(<App />)
    await userEvent.type(screen.getByLabelText('Email'), 'x@demo.local')
    await userEvent.type(screen.getByLabelText('Senha'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Email ou senha incorretos.')
    expect(sessionStorage.length).toBe(0)
  })
})

describe('cliente', () => {
  it('CPF inválido é barrado no navegador, sem chamar a API', async () => {
    logarComo()
    const chamadas = servidorFalso({
      'GET /api/contas/eu': { corpo: perfil('cliente') },
      'GET /api/kyc/minha': { status: 404, corpo: { detail: 'nenhuma verificação enviada' } },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Nome completo'), 'Ana Ficticia')
    await userEvent.type(screen.getByLabelText('CPF'), '111.111.111-11')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar para análise' }))
    expect(screen.getByText('CPF inválido.')).toBeInTheDocument()
    expect(chamadas.some(c => c.rota === 'POST /api/kyc/minha')).toBe(false)
  })

  it('envia o formulário e passa a mostrar "Em análise"', async () => {
    logarComo()
    const chamadas = servidorFalso({
      'GET /api/contas/eu': { corpo: perfil('cliente') },
      'GET /api/kyc/minha': { status: 404, corpo: {} },
      'POST /api/kyc/minha': { status: 201, corpo: verificacao() },
    })
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Nome completo'), 'Ana Ficticia')
    await userEvent.type(screen.getByLabelText('CPF'), '52998224725')
    await userEvent.type(screen.getByLabelText('Data de nascimento'), '1999-05-10')
    const pdf = new File(['%PDF-1.4'], 'rg.pdf', { type: 'application/pdf' })
    await userEvent.upload(screen.getByLabelText(/Documento/), pdf)
    await userEvent.click(screen.getByRole('button', { name: 'Enviar para análise' }))
    expect(await screen.findByText('Em análise')).toBeInTheDocument()
    const envio = chamadas.find(c => c.rota === 'POST /api/kyc/minha')!
    expect((envio.init.body as FormData).get('cpf')).toBe('529.982.247-25')  // formatado no blur, limpo no backend
  })

  it('mostra o motivo da recusa e libera novo envio', async () => {
    logarComo()
    servidorFalso({
      'GET /api/contas/eu': { corpo: perfil('cliente') },
      'GET /api/kyc/minha': { corpo: verificacao({ status: 'recusada', motivo_recusa: 'foto ilegível' }) },
    })
    render(<App />)
    expect(await screen.findByText(/foto ilegível/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar para análise' })).toBeInTheDocument()
  })
})

describe('operador', () => {
  it('recusar exige motivo e envia o motivo digitado', async () => {
    logarComo()
    let pendentes = [verificacao()]
    const chamadas = servidorFalso({
      'GET /api/contas/eu': { corpo: perfil('operador') },
      'GET /api/kyc/fila?status=pendente': () => ({ corpo: { count: pendentes.length, results: pendentes } }),
      'POST /api/kyc/7/decisao': () => { pendentes = []; return { corpo: verificacao({ status: 'recusada' }) } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Recusar' }))
    const confirmar = screen.getByRole('button', { name: 'Confirmar recusa' })
    expect(confirmar).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Motivo da recusa'), 'documento vencido')
    await userEvent.click(confirmar)
    expect(await screen.findByText('Nenhum pedido aqui.')).toBeInTheDocument()
    const decisao = chamadas.find(c => c.rota === 'POST /api/kyc/7/decisao')!
    expect(JSON.parse(decisao.init.body as string)).toEqual({ aprovar: false, motivo: 'documento vencido' })
  })

  it('pedido já decidido por outro operador mostra o conflito', async () => {
    logarComo()
    servidorFalso({
      'GET /api/contas/eu': { corpo: perfil('operador') },
      'GET /api/kyc/fila?status=pendente': { corpo: { count: 1, results: [verificacao()] } },
      'POST /api/kyc/7/decisao': { status: 409, corpo: { detail: 'verificação já está aprovada' } },
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Aprovar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('verificação já está aprovada')
  })
})

describe('compliance e sessão', () => {
  it('compliance vê a trilha de auditoria', async () => {
    logarComo()
    servidorFalso({
      'GET /api/contas/eu': { corpo: perfil('compliance') },
      'GET /api/auditoria': { corpo: { count: 1, results: [
        { id: 1, ator_email: 'op@demo.local', acao: 'kyc_recusado', verificacao: 7,
          dados: { antes: 'pendente', depois: 'recusada', motivo: 'documento vencido' }, criado_em: '2026-09-29T15:00:00-03:00' },
      ] } },
    })
    render(<App />)
    expect(await screen.findByText('Recusou verificação')).toBeInTheDocument()
    expect(screen.getByText('Motivo: documento vencido')).toBeInTheDocument()
  })

  it('token vencido é renovado uma vez e a requisição é repetida', async () => {
    logarComo('velho', 'renovacao')
    let tentativas = 0
    const chamadas = servidorFalso({
      'GET /api/contas/eu': (init) => {
        tentativas++
        const auth = new Headers(init.headers).get('Authorization')
        return auth === 'Bearer novo' ? { corpo: perfil('cliente') } : { status: 401, corpo: {} }
      },
      'POST /api/token/renovar': { corpo: { access: 'novo' } },
    })
    const r = await requisitar('/api/contas/eu')
    expect((await r.json()).papel).toBe('cliente')
    expect(tentativas).toBe(2)
    expect(chamadas.filter(c => c.rota === 'POST /api/token/renovar')).toHaveLength(1)
  })
})
