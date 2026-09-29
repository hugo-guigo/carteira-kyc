// Mesma regra do backend (kyc/validadores.py). Validar aqui dá resposta imediata ao usuário; o backend
// valida de novo, porque qualquer um pode chamar a API sem passar pelo formulário.

export const apenasDigitos = (cpf: string) => cpf.replace(/\D/g, '')

export function cpfValido(cpf: string): boolean {
  const n = apenasDigitos(cpf)
  if (n.length !== 11 || /^(\d)\1{10}$/.test(n)) return false
  for (const posicao of [9, 10]) {
    let soma = 0
    for (let i = 0; i < posicao; i++) soma += Number(n[i]) * (posicao + 1 - i)
    if (((soma * 10) % 11) % 10 !== Number(n[posicao])) return false
  }
  return true
}

export function formatarCpf(cpf: string): string {
  const n = apenasDigitos(cpf)
  return n.length === 11 ? `${n.slice(0, 3)}.${n.slice(3, 6)}.${n.slice(6, 9)}-${n.slice(9)}` : cpf
}
