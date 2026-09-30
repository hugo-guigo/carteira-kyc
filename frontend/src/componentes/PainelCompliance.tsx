import { useEffect, useState } from 'react'
import { auditoria, type Evento } from '../api'
import { formatarCentavos } from '../dinheiro'

const ACOES: Record<string, string> = {
  kyc_enviado: 'Enviou verificação', kyc_aprovado: 'Aprovou verificação', kyc_recusado: 'Recusou verificação',
  deposito: 'Depositou', saque: 'Sacou',
}

export function PainelCompliance() {
  const [eventos, setEventos] = useState<Evento[] | null>(null)
  const [erro, setErro] = useState('')

  useEffect(() => {
    auditoria().then(setEventos).catch(() => setErro('Não foi possível carregar a auditoria.'))
  }, [])

  return (
    <section>
      <h2>Trilha de auditoria</h2>
      <p className="mudo">Somente leitura. O banco recusa alteração e exclusão destes registros.</p>
      {erro && <p className="erro" role="alert">{erro}</p>}
      {eventos === null && !erro && <p>Carregando…</p>}
      {eventos && (
        <table>
          <thead><tr><th>Quando</th><th>Quem</th><th>O quê</th><th>Alvo</th><th>Detalhes</th></tr></thead>
          <tbody>
            {eventos.map(e => (
              <tr key={e.id}>
                <td>{new Date(e.criado_em).toLocaleString('pt-BR')}</td>
                <td>{e.ator_email}</td>
                <td>{ACOES[e.acao] ?? e.acao}</td>
                <td>{e.verificacao !== null ? `Verificação #${e.verificacao}` : 'Carteira'}</td>
                <td>{detalhes(e)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function detalhes(e: Evento): string {
  if (typeof e.dados.valor_centavos === 'number') return formatarCentavos(e.dados.valor_centavos)
  return e.dados.motivo ? `Motivo: ${e.dados.motivo}` : ''
}
