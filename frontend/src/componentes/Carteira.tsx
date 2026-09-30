import { useEffect, useState, type FormEvent } from 'react'
import { ErroApi, extrato, operar, saldoDaCarteira, type Lancamento } from '../api'
import { formatarCentavos, reaisParaCentavos } from '../dinheiro'

type Rota = 'depositos' | 'saques'
// Operação que ainda não teve resposta do servidor (falha de rede). Repetir a mesma operação reaproveita
// a chave: se a primeira tentativa chegou a gravar, o backend devolve a original em vez de duplicar.
type Pendente = { rota: Rota; centavos: number; chave: string }

const NOMES = { deposito: 'Depósito', saque: 'Saque' }

export function Carteira() {
  const [saldo, setSaldo] = useState<number | null>(null)
  const [itens, setItens] = useState<Lancamento[]>([])
  const [proximo, setProximo] = useState<string | null>(null)
  const [valor, setValor] = useState('')
  const [erro, setErro] = useState('')
  const [operando, setOperando] = useState(false)
  const [pendente, setPendente] = useState<Pendente | null>(null)

  useEffect(() => {
    Promise.all([saldoDaCarteira(), extrato()])
      .then(([s, pagina]) => {
        setSaldo(s)
        setItens(pagina.itens)
        setProximo(pagina.proximo)
      })
      .catch(() => setErro('Não foi possível carregar a carteira.'))
  }, [])

  async function executar(rota: Rota) {
    const centavos = reaisParaCentavos(valor)
    if (centavos === null) {
      setErro('Informe um valor como 50 ou 1.234,56.')
      return
    }
    const mesma = pendente && pendente.rota === rota && pendente.centavos === centavos
    const tentativa = mesma ? pendente : { rota, centavos, chave: crypto.randomUUID() }
    setPendente(tentativa)
    setErro('')
    setOperando(true)
    try {
      const r = await operar(rota, centavos, tentativa.chave)
      setPendente(null)
      setValor('')
      setSaldo(r.saldo_centavos)
      const pagina = await extrato()
      setItens(pagina.itens)
      setProximo(pagina.proximo)
    } catch (e) {
      if (e instanceof ErroApi) {
        setPendente(null)  // o servidor respondeu: a operação não foi feita, e a próxima usa chave nova
        setErro(e.status === 409 ? 'Saldo insuficiente.' : (e.campos().valor_centavos ?? e.message))
      } else {
        setErro('Falha de conexão. Tente de novo: a mesma operação não será feita duas vezes.')
      }
    } finally {
      setOperando(false)
    }
  }

  async function carregarMais() {
    if (!proximo) return
    const pagina = await extrato(proximo)
    setItens(atuais => [...atuais, ...pagina.itens])
    setProximo(pagina.proximo)
  }

  if (saldo === null && !erro) return <p>Carregando a carteira…</p>

  return (
    <div className="cartao">
      <h2>Carteira</h2>
      <p>Saldo: <strong data-testid="saldo">{saldo === null ? '–' : formatarCentavos(saldo)}</strong></p>
      <form className="acoes" onSubmit={(ev: FormEvent) => ev.preventDefault()}>
        <label>Valor (R$)
          <input value={valor} inputMode="decimal" placeholder="0,00" onChange={e => setValor(e.target.value)} />
        </label>
        <button type="button" className="principal" disabled={operando} onClick={() => executar('depositos')}>
          Depositar
        </button>
        <button type="button" disabled={operando} onClick={() => executar('saques')}>Sacar</button>
      </form>
      <p className="aviso">Dinheiro fictício: o depósito só simula uma entrada. Até R$ 10.000,00 por operação.</p>
      {erro && <p className="erro" role="alert">{erro}</p>}
      <h3>Extrato</h3>
      {itens.length === 0 ? <p className="mudo">Nenhuma movimentação ainda.</p> : (
        <table>
          <thead><tr><th>Quando</th><th>Operação</th><th>Valor</th></tr></thead>
          <tbody>
            {itens.map(l => (
              <tr key={l.id}>
                <td>{new Date(l.criado_em).toLocaleString('pt-BR')}</td>
                <td>{NOMES[l.tipo]}</td>
                <td className={l.valor_centavos < 0 ? 'saida' : 'entrada'}>
                  {l.valor_centavos < 0 ? '−' : '+'}{formatarCentavos(Math.abs(l.valor_centavos))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {proximo && <button type="button" onClick={carregarMais}>Carregar mais</button>}
    </div>
  )
}
