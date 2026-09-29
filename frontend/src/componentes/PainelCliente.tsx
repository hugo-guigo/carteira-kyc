import { useEffect, useState, type FormEvent } from 'react'
import { enviarVerificacao, ErroApi, minhaVerificacao, type Verificacao } from '../api'
import { cpfValido, formatarCpf } from '../cpf'
import { SeloStatus } from './SeloStatus'

const TIPOS = ['application/pdf', 'image/jpeg', 'image/png']
const MAXIMO = 2 * 1024 * 1024

export function PainelCliente() {
  const [verificacao, setVerificacao] = useState<Verificacao | null | undefined>(undefined)
  const [erroCarga, setErroCarga] = useState('')

  useEffect(() => {
    minhaVerificacao().then(setVerificacao).catch(() => setErroCarga('Não foi possível carregar sua verificação.'))
  }, [])

  if (erroCarga) return <p className="erro" role="alert">{erroCarga}</p>
  if (verificacao === undefined) return <p>Carregando…</p>

  const podeEnviar = verificacao === null || verificacao.status === 'recusada'
  return (
    <section>
      <h2>Verificação de identidade</h2>
      {verificacao && (
        <div className="cartao">
          <p>Pedido enviado em {new Date(verificacao.criado_em).toLocaleString('pt-BR')}</p>
          <SeloStatus status={verificacao.status} />
          {verificacao.status === 'pendente' && <p>Um operador vai analisar seus dados.</p>}
          {verificacao.status === 'aprovada' && <p>Sua conta está liberada.</p>}
          {verificacao.status === 'recusada' && <p>Motivo: {verificacao.motivo_recusa}. Envie os dados de novo.</p>}
        </div>
      )}
      {podeEnviar && <FormularioKyc aoEnviar={setVerificacao} />}
    </section>
  )
}

function FormularioKyc({ aoEnviar }: { aoEnviar: (v: Verificacao) => void }) {
  const [nome, setNome] = useState('')
  const [cpf, setCpf] = useState('')
  const [nascimento, setNascimento] = useState('')
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [erros, setErros] = useState<Record<string, string>>({})
  const [enviando, setEnviando] = useState(false)

  function validar(): Record<string, string> {
    const e: Record<string, string> = {}
    if (!nome.trim()) e.nome_completo = 'Informe o nome completo.'
    if (!cpfValido(cpf)) e.cpf = 'CPF inválido.'
    if (!nascimento) e.data_nascimento = 'Informe a data de nascimento.'
    if (!arquivo) e.documento = 'Anexe um documento.'
    else if (!TIPOS.includes(arquivo.type)) e.documento = 'Envie um PDF, JPG ou PNG.'
    else if (arquivo.size > MAXIMO) e.documento = 'O arquivo passa de 2 MB.'
    return e
  }

  async function enviar(ev: FormEvent) {
    ev.preventDefault()
    const locais = validar()
    setErros(locais)
    if (Object.keys(locais).length) return
    const form = new FormData()
    form.append('nome_completo', nome)
    form.append('cpf', cpf)
    form.append('data_nascimento', nascimento)
    form.append('documento', arquivo as File)
    setEnviando(true)
    try {
      aoEnviar(await enviarVerificacao(form))
    } catch (erro) {
      setErros(erro instanceof ErroApi ? { geral: erro.message, ...erro.campos() } : { geral: 'Falha de conexão.' })
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className="cartao" onSubmit={enviar} noValidate>
      <p className="aviso">Use apenas dados fictícios. Este é um projeto de demonstração.</p>
      <label>Nome completo<input value={nome} onChange={e => setNome(e.target.value)} /></label>
      {erros.nome_completo && <p className="erro">{erros.nome_completo}</p>}
      <label>CPF<input value={cpf} inputMode="numeric" placeholder="000.000.000-00"
        onChange={e => setCpf(e.target.value)} onBlur={() => setCpf(formatarCpf(cpf))} /></label>
      {erros.cpf && <p className="erro">{erros.cpf}</p>}
      <label>Data de nascimento<input type="date" value={nascimento} onChange={e => setNascimento(e.target.value)} /></label>
      {erros.data_nascimento && <p className="erro">{erros.data_nascimento}</p>}
      <label>Documento (PDF, JPG ou PNG até 2 MB)
        <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={e => setArquivo(e.target.files?.[0] ?? null)} />
      </label>
      {erros.documento && <p className="erro">{erros.documento}</p>}
      {erros.geral && <p className="erro" role="alert">{erros.geral}</p>}
      <button className="principal" disabled={enviando}>Enviar para análise</button>
    </form>
  )
}
