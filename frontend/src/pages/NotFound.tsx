import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Waves } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="text-center">
        <Waves className="h-16 w-16 text-muted-foreground mx-auto mb-6" />
        <h1 className="text-4xl font-bold mb-2">404</h1>
        <p className="text-muted-foreground mb-6">
          The page you are looking for does not exist.
        </p>
        <Button asChild>
          <Link to="/dashboard/executive">Return to Dashboard</Link>
        </Button>
      </div>
    </div>
  )
}
