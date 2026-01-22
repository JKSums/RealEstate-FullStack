import { useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'
import { Button } from "@/components/ui/button"
import { AlignCenter } from 'lucide-react'
function App() {
  const [count, setCount] = useState(0)

  return (
    <>
    <Button style={{
    }}>
      Ok
    </Button>
    </>
  )
}

export default App
