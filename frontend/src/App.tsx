import { useEffect, useState } from 'react'
import { estaLogado, eu, sair, type Perfil } from './api'
import { Entrar } from './componentes/Entrar'
import { PainelCliente } from './componentes/PainelCliente'
import { PainelCompliance } from './componentes/PainelCompliance'
import { PainelOperador } from './componentes/PainelOperador'

const NOME_PAPEL = { cliente: 'Cliente', operador: 'Operador', compliance: 'Compliance' }

export default function App() {
  const [perfil, setPerfil] = useState<Perfil | null>(null)
  const [carregando, setCarregando] = useState(estaLogado())

  useEffect(() => {
    if (!estaLogado()) return
    eu().then(setPerfil).catch(sair).finally(() => setCarregando(false))
  }, [])

  function deslogar() {
    sair()
    setPerfil(null)
  }

  return (
    <>
      <header className="topo">
        <h1>Carteira KYC</h1>
        {perfil && (
          <div className="usuario">
            <span>{perfil.nome} · {NOME_PAPEL[perfil.papel]}</span>
            <button type="button" onClick={deslogar}>Sair</button>
          </div>
        )}
      </header>
      <p className="faixa">Demonstração com dados fictícios. Nenhum documento ou dinheiro real.</p>
      <main>
        {carregando ? <p>Carregando…</p>
          : !perfil ? <Entrar aoEntrar={setPerfil} />
          : perfil.papel === 'cliente' ? <PainelCliente />
          : perfil.papel === 'operador' ? <PainelOperador />
          : <PainelCompliance />}
      </main>
    </>
  )
}
