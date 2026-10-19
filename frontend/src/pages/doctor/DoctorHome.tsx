import { useState } from 'react';
import { Button, Card, Code, Group, Modal, Stack, Table, Text, TextInput, Title } from '@mantine/core';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { api, type Invite, type PatientSummary } from '../../api';
import { AlertLevelBadge, ScoreBadge } from '../../components/Badges';

function InviteButton() {
  const [opened, setOpened] = useState(false);
  const [label, setLabel] = useState('');
  const create = useMutation({ mutationFn: () => api<Invite>('/doctor/invites', { body: { patient_label: label || null } }) });
  const close = () => { setOpened(false); setLabel(''); create.reset(); };
  return (
    <>
      <Button onClick={() => setOpened(true)}>Пригласить пациента</Button>
      <Modal opened={opened} onClose={close} title="Приглашение пациента" centered>
        {create.data ? (
          <Stack align="center">
            <Text>Передайте пациенту код для регистрации:</Text>
            <Code fz={32} p="md">{create.data.code}</Code>
            <Button onClick={close}>Готово</Button>
          </Stack>
        ) : (
          <Stack>
            <TextInput label="Пометка для себя (необязательно)" placeholder="например, Иванова, приём 18.10"
              value={label} onChange={(e) => setLabel(e.currentTarget.value)} />
            <Button loading={create.isPending} onClick={() => create.mutate()}>Создать код</Button>
          </Stack>
        )}
      </Modal>
    </>
  );
}

export function DoctorHome() {
  const navigate = useNavigate();
  const { data = [], isLoading } = useQuery({ queryKey: ['patients'],
    queryFn: () => api<PatientSummary[]>('/doctor/patients') });
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Мои пациенты</Title>
        <InviteButton />
      </Group>
      <Card withBorder radius="md" p={0}>
        <Table highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Пациент</Table.Th>
              <Table.Th>Риск</Table.Th>
              <Table.Th>Открытые алерты</Table.Th>
              <Table.Th>Последние шкалы</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.map((p) => (
              <Table.Tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/doctor/patients/${p.id}`)}>
                <Table.Td fw={500}>{p.full_name}</Table.Td>
                <Table.Td>{p.top_alert_level ? <AlertLevelBadge level={p.top_alert_level} /> : '—'}</Table.Td>
                <Table.Td>{p.open_alerts || '—'}</Table.Td>
                <Table.Td>
                  <Group gap={6}>
                    <ScoreBadge name="GAD-7" result={p.last_scores.gad7} />
                    <ScoreBadge name="PHQ-9" result={p.last_scores.phq9} />
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
            {!isLoading && data.length === 0 && (
              <Table.Tr><Table.Td colSpan={4}><Text c="dimmed" ta="center" p="md">
                Пациентов пока нет — создайте приглашение
              </Text></Table.Td></Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  );
}
