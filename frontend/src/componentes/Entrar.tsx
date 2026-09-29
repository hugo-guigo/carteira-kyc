import { useState, type FormEvent } from 'react'
import { cadastrar, entrar, ErroApi, type Perfil } from '../api'

export function Entrar({ aoEntrar }: { aoEntrar: (p: Perfil) => void }) {
  const [modo, setModo] = useState<'entrar' | 'cadastrar'>('entrar')
  const [email, setEmail] = useState('')
  const [nome, setNome] = useState('')
  const [senha, setSenha] = useState('')
  const [erros, setErros] = useState<Record<string, string>>({})
  const [enviando, setEnviando] = useState(false)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setErros({})
    setEnviando(true)
    try {
      if (modo === 'cadastrar') await cadastrar({ email, nome, senha })
      aoEntrar(await entrar(email, senha))
    } catch (erro) {
      if (erro instanceof ErroApi) {
        setErros(erro.status === 401 ? { geral: 'Email ou senha incorretos.' } : { geral: erro.message, ...erro.campos() })
      } else {
        setErros({ geral: 'Não foi possível falar com o servidor.' })
      }
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className="cartao estreito" onSubmit={enviar} noValidate>
      <div className="abas" role="tablist">
        <button type="button" role="tab" aria-selected={modo === 'entrar'} onClick={() => setModo('entrar')}>Entrar</button>
        <button type="button" role="tab" aria-selected={modo === 'cadastrar'} onClick={() => setModo('cadastrar')}>Criar conta</button>
      </div>
      <label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label>
      {erros.email && <p className="erro">{erros.email}</p>}
      {modo === 'cadastrar' && (
        <label>Nome<input value={nome} onChange={e => setNome(e.target.value)} required /></label>
      )}
      <label>Senha<input type="password" value={senha} onChange={e => setSenha(e.target.value)} required /></label>
      {erros.senha && <p className="erro">{erros.senha}</p>}
      {erros.non_field_errors && <p className="erro">{erros.non_field_errors}</p>}
      {erros.geral && <p className="erro" role="alert">{erros.geral}</p>}
      <button className="principal" disabled={enviando}>{modo === 'entrar' ? 'Entrar' : 'Criar conta'}</button>
    </form>
  )
}
