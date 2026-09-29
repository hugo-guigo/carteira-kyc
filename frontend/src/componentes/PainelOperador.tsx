import { useCallback, useEffect, useState } from 'react'
import { abrirDocumento, decidir, ErroApi, fila, type Status, type Verificacao } from '../api'
import { formatarCpf } from '../cpf'
import { SeloStatus } from './SeloStatus'

export function PainelOperador() {
  const [filtro, setFiltro] = useState<Status>('pendente')
  const [itens, setItens] = useState<Verificacao[] | null>(null)
  const [erro, setErro] = useState('')

  const carregar = useCallback(() => {
    fila(filtro).then(setItens).catch(() => setErro('Não foi possível carregar a fila.'))
  }, [filtro])

  useEffect(carregar, [carregar])

  function trocarFiltro(s: Status) {
    setItens(null)  // mostra "Carregando…" enquanto busca a outra aba
    setFiltro(s)
  }

  return (
    <section>
      <h2>Fila de verificação</h2>
      <div className="abas" role="tablist">
        {(['pendente', 'aprovada', 'recusada'] as Status[]).map(s => (
          <button key={s} type="button" role="tab" aria-selected={filtro === s} onClick={() => trocarFiltro(s)}>
            {s === 'pendente' ? 'Pendentes' : s === 'aprovada' ? 'Aprovadas' : 'Recusadas'}
          </button>
        ))}
      </div>
      {erro && <p className="erro" role="alert">{erro}</p>}
      {itens === null && !erro && <p>Carregando…</p>}
      {itens?.length === 0 && <p>Nenhum pedido aqui.</p>}
      {itens?.map(v => <Item key={v.id} v={v} aoDecidir={carregar} />)}
    </section>
  )
}

function Item({ v, aoDecidir }: { v: Verificacao; aoDecidir: () => void }) {
  const [recusando, setRecusando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState('')

  async function enviar(aprovar: boolean) {
    setErro('')
    try {
      await decidir(v.id, aprovar, motivo)
      aoDecidir()
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : 'Falha de conexão.')
    }
  }

  async function verDocumento() {
    try {
      window.open(await abrirDocumento(v.id), '_blank', 'noopener')
    } catch {
      setErro('Não foi possível abrir o documento.')
    }
  }

  return (
    <article className="cartao item">
      <header>
        <strong>{v.nome_completo}</strong> <SeloStatus status={v.status} />
      </header>
      <p className="mudo">{v.cliente_email} · CPF {formatarCpf(v.cpf)} · nascimento {v.data_nascimento.split("-").reverse().join("/")}</p>
      {v.status === 'recusada' && <p>Motivo: {v.motivo_recusa}</p>}
      {v.decidido_por_email && <p className="mudo">Decidido por {v.decidido_por_email}</p>}
      <div className="acoes">
        <button type="button" onClick={verDocumento}>Ver documento</button>
        {v.status === 'pendente' && !recusando && (
          <>
            <button type="button" className="principal" onClick={() => enviar(true)}>Aprovar</button>
            <button type="button" className="perigo" onClick={() => setRecusando(true)}>Recusar</button>
          </>
        )}
      </div>
      {recusando && (
        <div className="recusa">
          <label>Motivo da recusa<textarea value={motivo} onChange={e => setMotivo(e.target.value)} /></label>
          <button type="button" className="perigo" disabled={!motivo.trim()} onClick={() => enviar(false)}>
            Confirmar recusa
          </button>
          <button type="button" onClick={() => setRecusando(false)}>Cancelar</button>
        </div>
      )}
      {erro && <p className="erro" role="alert">{erro}</p>}
    </article>
  )
}
