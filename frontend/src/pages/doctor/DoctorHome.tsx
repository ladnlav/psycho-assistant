import { useState } from 'react';
import { Badge, Button, Card, Code, CopyButton, Group, List, Modal, Stack, Table, Text, TextInput, Title,
  Tooltip } from '@mantine/core';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { api, type Diagnosis, type Invite, type PatientSummary } from '../../api';
import { AlertLevelBadge, ScoreBadge } from '../../components/Badges';

/** Коды МКБ-10 в списке — компактно, полное название во всплывающей подсказке; серые, как в карточке. */
function DiagnosisCodes({ items }: { items: Diagnosis[] }) {
  if (!items.length) return <Text c="dimmed">—</Text>;
  return (
    <Group gap={4}>
      {items.map((d) => (
        <Tooltip key={d.id} label={`${d.title}${d.confirmed ? '' : ' · не подтверждён врачом'}`}>
          <Badge tt="none" color="gray" variant={d.confirmed ? 'light' : 'outline'}>{d.icd10}</Badge>
        </Tooltip>
      ))}
    </Group>
  );
}

function Copy({ value, label }: { value: string; label: string }) {
  return (
    <CopyButton value={value} timeout={1500}>
      {({ copied, copy }) => (
        <Button variant="light" color={copied ? 'teal' : undefined} onClick={copy}>
          {copied ? 'Скопировано' : label}
        </Button>
      )}
    </CopyButton>
  );
}

function InviteButton() {
  const [opened, setOpened] = useState(false);
  const [label, setLabel] = useState('');
  const create = useMutation({ mutationFn: () => api<Invite>('/doctor/invites', { body: { patient_label: label || null } }) });
  const close = () => { setOpened(false); setLabel(''); create.reset(); };
  const code = create.data?.code;
  const link = code ? `${window.location.origin}/register?code=${encodeURIComponent(code)}` : '';
  return (
    <>
      <Button onClick={() => setOpened(true)}>Пригласить пациента</Button>
      <Modal opened={opened} onClose={close} title="Приглашение пациента" centered>
        {code ? (
          <Stack>
            <Code fz={32} p="md" ta="center" block>{code}</Code>
            <Code block style={{ wordBreak: 'break-all', whiteSpace: 'normal' }}>{link}</Code>
            <Group grow>
              <Copy value={code} label="Скопировать код" />
              <Copy value={link} label="Скопировать ссылку" />
            </Group>
            <List type="ordered" size="sm" spacing={4}>
              <List.Item>Отправьте пациенту ссылку (например, в мессенджер) или продиктуйте код.</List.Item>
              <List.Item>Пациент открывает ссылку на телефоне — код подставится сам — или вводит код на странице
                регистрации.</List.Item>
              <List.Item>Пациент регистрируется и даёт согласие на обработку персональных данных.</List.Item>
              <List.Item>После этого пациент появится в списке «Мои пациенты».</List.Item>
            </List>
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
  // Опрос раз в 10 с, как в карточке: приглашённый пациент появляется сам, когда зарегистрируется.
  const { data = [], isLoading } = useQuery({ queryKey: ['patients'], refetchInterval: 10_000,
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
              <Table.Th>Диагнозы</Table.Th>
              <Table.Th>Риск</Table.Th>
              <Table.Th>Открытые алерты</Table.Th>
              <Table.Th>Последние шкалы</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.map((p) => (
              <Table.Tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/doctor/patients/${p.id}`)}>
                <Table.Td fw={500}>{p.full_name}</Table.Td>
                <Table.Td><DiagnosisCodes items={p.diagnoses} /></Table.Td>
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
              <Table.Tr><Table.Td colSpan={5}><Text c="dimmed" ta="center" p="md">
                Пациентов пока нет — создайте приглашение
              </Text></Table.Td></Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  );
}
