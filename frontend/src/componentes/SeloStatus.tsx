import type { Status } from '../api'

const TEXTO: Record<Status, string> = { pendente: 'Em análise', aprovada: 'Aprovada', recusada: 'Recusada' }

export function SeloStatus({ status }: { status: Status }) {
  return <span className={`selo selo-${status}`}>{TEXTO[status]}</span>
}
