// Dinheiro em centavos inteiros, igual ao backend. "12,34" vira 1234 sem passar por número decimal:
// em ponto flutuante, 0,1 + 0,2 não dá 0,3, e um centavo a mais ou a menos numa carteira é bug.

// Aceita "12", "12,3", "12,34", "1.234,56" e "R$ 1.234,56". Recusa ponto como decimal ("12.5"), porque
// no Brasil ele separa milhar e a leitura ficaria ambígua.
const FORMATO = /^(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?$/

export function reaisParaCentavos(texto: string): number | null {
  const m = FORMATO.exec(texto.trim())
  if (!m) return null
  const reais = m[1].replaceAll('.', '')
  if (reais.length > 7) return null  // acima de R$ 9.999.999: fora de qualquer limite da demo
  const centavos = Number(reais) * 100 + Number((m[2] ?? '').padEnd(2, '0'))
  return centavos > 0 ? centavos : null
}

const REAIS = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

export function formatarCentavos(centavos: number): string {
  return REAIS.format(centavos / 100)  // divisão só para exibir; nenhuma conta é feita com o resultado
}
