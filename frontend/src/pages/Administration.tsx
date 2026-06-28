import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth.store'
import { api } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Users, Settings, Database, Activity, Shield } from 'lucide-react'

export default function Administration() {
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState('users')

  const { data: users } = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => api.users.list(),
    enabled: ['ADMIN', 'SUPERADMIN'].includes(user?.role ?? ''),
  })

  const { data: systemHealth } = useQuery({
    queryKey: ['admin', 'health'],
    queryFn: () => api.health.detailed(),
    refetchInterval: 30_000,
  })

  if (!['ADMIN', 'SUPERADMIN'].includes(user?.role ?? '')) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <Shield className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
          <p className="text-muted-foreground">Administrator access required.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Administration</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Organisation management, users, and system configuration
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="users" className="flex items-center gap-2">
            <Users className="h-3.5 w-3.5" />
            Users
          </TabsTrigger>
          <TabsTrigger value="system" className="flex items-center gap-2">
            <Activity className="h-3.5 w-3.5" />
            System Health
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center gap-2">
            <Settings className="h-3.5 w-3.5" />
            Settings
          </TabsTrigger>
        </TabsList>

        <TabsContent value="users" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Organisation Users</CardTitle>
              <CardDescription>Manage user access and roles</CardDescription>
            </CardHeader>
            <CardContent>
              {users && users.length > 0 ? (
                <div className="space-y-2">
                  {users.map((u: any) => (
                    <div key={u.id} className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                      <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
                        <span className="text-xs font-medium">
                          {u.full_name?.[0] ?? u.email[0].toUpperCase()}
                        </span>
                      </div>
                      <div className="flex-1">
                        <p className="text-sm font-medium">{u.full_name ?? u.email}</p>
                        <p className="text-xs text-muted-foreground">{u.email}</p>
                      </div>
                      <Badge variant="outline" className="text-xs">{u.role}</Badge>
                      <Badge variant={u.is_active ? 'default' : 'secondary'}>
                        {u.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">No users found.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="system" className="mt-4">
          <div className="grid grid-cols-2 gap-4">
            {[
              { label: 'Database', check: (systemHealth as any)?.checks?.database },
              { label: 'Event Bus (Redis)', check: (systemHealth as any)?.checks?.event_bus },
              { label: 'Scientific Graph (Neo4j)', check: (systemHealth as any)?.checks?.srg },
            ].map(({ label, check }) => (
              <Card key={label}>
                <CardContent className="flex items-center gap-3 p-4">
                  <div className={`h-3 w-3 rounded-full flex-shrink-0 ${
                    check?.connected || check?.status === 'healthy'
                      ? 'bg-emerald-400'
                      : check?.status === 'degraded'
                      ? 'bg-amber-400'
                      : 'bg-red-400'
                  }`} />
                  <div>
                    <p className="font-medium text-sm">{label}</p>
                    <p className="text-xs text-muted-foreground capitalize">
                      {check?.status ?? (check?.connected ? 'connected' : 'disconnected')}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="settings" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Platform Configuration</CardTitle>
              <CardDescription>
                Scientific loop intervals, objective weights, and model parameters
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Configuration management is available via the LOS API at /api/v1/admin/settings.
                Contact your LOS administrator to modify system-level settings.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
