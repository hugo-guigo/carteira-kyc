import { vi } from 'vitest'

// fetch falso: cada rota ("MÉTODO /caminho") responde com uma função. Guarda as chamadas feitas.
type Resposta = { status?: number; corpo?: unknown }
type Rota = (init: RequestInit) => Resposta

export function servidorFalso(rotas: Record<string, Rota | Resposta>) {
  const chamadas: { rota: string; init: RequestInit }[] = []
  const fetchFalso = vi.fn(async (url: string, init: RequestInit = {}) => {
    const caminho = new URL(url).pathname + new URL(url).search
    const rota = `${init.method ?? 'GET'} ${caminho}`
    chamadas.push({ rota, init })
    const tratador = rotas[rota]
    if (!tratador) return new Response(JSON.stringify({ detail: `rota não prevista: ${rota}` }), { status: 500 })
    const { status = 200, corpo = {} } = typeof tratador === 'function' ? tratador(init) : tratador
    return new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchFalso)
  return chamadas
}

export function logarComo(access = 'acesso', refresh = 'renovacao') {
  sessionStorage.setItem('carteira-kyc-tokens', JSON.stringify({ access, refresh }))
}

export const perfil = (papel: string) => ({ id: 1, email: `${papel}@demo.local`, nome: `Nome ${papel}`, papel })

export const verificacao = (extra: Record<string, unknown> = {}) => ({
  id: 7, cliente_email: 'cliente@demo.local', nome_completo: 'Ana Ficticia', cpf: '52998224725',
  data_nascimento: '1999-05-10', documento_tipo: 'application/pdf', status: 'pendente', motivo_recusa: '',
  decidido_por_email: null, decidido_em: null, criado_em: '2026-09-29T15:00:00-03:00', ...extra,
})
