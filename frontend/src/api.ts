// Cliente da API. Guarda os tokens JWT e renova o de acesso (15 min) uma vez quando a API responde 401.
//
// Os tokens ficam no sessionStorage: somem ao fechar a aba e sobrevivem a um F5. Qualquer script na
// página consegue lê-los, então a defesa principal é não ter XSS (o React escapa o texto que renderiza).
// Cookie HttpOnly seria mais seguro; fica anotado como próximo passo no README.

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export type Papel = 'cliente' | 'operador' | 'compliance'
export type Status = 'pendente' | 'aprovada' | 'recusada'

export interface Perfil { id: number; email: string; nome: string; papel: Papel }
export interface Verificacao {
  id: number; cliente_email: string; nome_completo: string; cpf: string; data_nascimento: string
  documento_tipo: string; status: Status; motivo_recusa: string; decidido_por_email: string | null
  decidido_em: string | null; criado_em: string
}
export interface Evento {
  id: number; ator_email: string; acao: string; verificacao: number; dados: Record<string, string>; criado_em: string
}
interface Pagina<T> { count: number; results: T[] }

export class ErroApi extends Error {
  status: number
  dados: Record<string, unknown>
  constructor(status: number, dados: Record<string, unknown>) {
    super(typeof dados.detail === 'string' ? dados.detail : `erro ${status}`)
    this.status = status
    this.dados = dados
  }
  // Mensagens por campo, no formato do Django REST Framework: {"cpf": ["CPF inválido"]}
  campos(): Record<string, string> {
    const saida: Record<string, string> = {}
    for (const [campo, valor] of Object.entries(this.dados)) {
      if (Array.isArray(valor)) saida[campo] = String(valor[0])
    }
    return saida
  }
}

const CHAVE = 'carteira-kyc-tokens'
type Tokens = { access: string; refresh: string }

function lerTokens(): Tokens | null {
  const bruto = sessionStorage.getItem(CHAVE)
  return bruto ? (JSON.parse(bruto) as Tokens) : null
}

export function sair(): void {
  sessionStorage.removeItem(CHAVE)
}

export function estaLogado(): boolean {
  return lerTokens() !== null
}

async function corpo(r: Response): Promise<Record<string, unknown>> {
  try { return await r.json() } catch { return {} }
}

async function renovar(): Promise<boolean> {
  const tokens = lerTokens()
  if (!tokens) return false
  const r = await fetch(`${API_URL}/api/token/renovar`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh: tokens.refresh }),
  })
  if (!r.ok) { sair(); return false }
  const { access } = (await r.json()) as { access: string }
  sessionStorage.setItem(CHAVE, JSON.stringify({ ...tokens, access }))
  return true
}

export async function requisitar(caminho: string, init: RequestInit = {}, jaRenovou = false): Promise<Response> {
  const tokens = lerTokens()
  const headers = new Headers(init.headers)
  if (tokens) headers.set('Authorization', `Bearer ${tokens.access}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const r = await fetch(`${API_URL}${caminho}`, { ...init, headers })
  if (r.status === 401 && tokens && !jaRenovou && (await renovar())) {
    return requisitar(caminho, init, true)
  }
  if (!r.ok) throw new ErroApi(r.status, await corpo(r))
  return r
}

async function json<T>(caminho: string, init?: RequestInit): Promise<T> {
  return (await requisitar(caminho, init)).json() as Promise<T>
}

export async function entrar(email: string, senha: string): Promise<Perfil> {
  const r = await fetch(`${API_URL}/api/token`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password: senha }),
  })
  if (!r.ok) throw new ErroApi(r.status, await corpo(r))
  sessionStorage.setItem(CHAVE, JSON.stringify(await r.json()))
  return eu()
}

export const eu = () => json<Perfil>('/api/contas/eu')

export const cadastrar = (dados: { email: string; nome: string; senha: string }) =>
  json<Perfil>('/api/contas/cadastro', { method: 'POST', body: JSON.stringify(dados) })

export async function minhaVerificacao(): Promise<Verificacao | null> {
  try {
    return await json<Verificacao>('/api/kyc/minha')
  } catch (erro) {
    if (erro instanceof ErroApi && erro.status === 404) return null
    throw erro
  }
}

export const enviarVerificacao = (form: FormData) =>
  json<Verificacao>('/api/kyc/minha', { method: 'POST', body: form })

export const fila = async (status: Status) =>
  (await json<Pagina<Verificacao>>(`/api/kyc/fila?status=${status}`)).results

export const decidir = (id: number, aprovar: boolean, motivo = '') =>
  json<Verificacao>(`/api/kyc/${id}/decisao`, { method: 'POST', body: JSON.stringify({ aprovar, motivo }) })

export const auditoria = async () => (await json<Pagina<Evento>>('/api/auditoria')).results

// O documento exige o token no cabeçalho, então não dá para usar um <a href> direto: baixa como blob.
export async function abrirDocumento(id: number): Promise<string> {
  const blob = await (await requisitar(`/api/kyc/${id}/documento`)).blob()
  return URL.createObjectURL(blob)
}
