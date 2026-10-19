import { AppShell, Badge, Button, Container, Group, Text } from '@mantine/core';
import { Link, Outlet } from 'react-router';
import { useAuth } from '../auth';
import { SPECIALTY } from '../labels';
import { useDoctorAlerts } from '../useDoctorAlerts';

export function Layout() {
  const { me, signOut } = useAuth();
  useDoctorAlerts(me?.role === 'doctor');
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Container size="lg" h="100%">
          <Group h="100%" justify="space-between" wrap="nowrap">
            <Text component={Link} to="/" fw={700} c="violet.8" style={{ textDecoration: 'none' }}>
              🧭 Клинический компас
            </Text>
            {me && (
              <Group gap="xs" wrap="nowrap">
                <Text size="sm" visibleFrom="sm">{me.full_name}</Text>
                <Badge variant="light">
                  {me.role === 'doctor' ? `врач${me.specialty ? ' · ' + (SPECIALTY[me.specialty] ?? me.specialty) : ''}`
                    : 'пациент'}
                </Badge>
                <Button size="xs" variant="subtle" onClick={signOut}>Выйти</Button>
              </Group>
            )}
          </Group>
        </Container>
      </AppShell.Header>
      <AppShell.Main>
        <Container size="lg" px={0}>
          <Outlet />
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
