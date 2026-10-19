import { useState } from 'react';
import { Alert as MAlert, Anchor, Badge, Button, Card, Group, NumberInput, SimpleGrid, Stack, Text, TextInput,
  Title } from '@mantine/core';
import { LineChart } from '@mantine/charts';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { api, type Alert, type PatientCard, type Recommendation } from '../../api';
import { AlertLevelBadge, ReferralBadge } from '../../components/Badges';
import { Chat } from '../../components/Chat';
import { Sources } from '../../components/Sources';
import { ALERT_LEVEL, formatDate, formatDateTime } from '../../labels';

function deliverySeconds(a: Alert): string | null {
  if (!a.delivered_at) return null;
  const s = (new Date(a.delivered_at).getTime() - new Date(a.created_at).getTime()) / 1000;
  return s.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function AlertsBlock({ card }: { card: PatientCard }) {
  const qc = useQueryClient();
  const ack = useMutation({
    mutationFn: (id: string) => api(`/doctor/alerts/${id}/ack`, { method: 'POST' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['card', card.id] }); qc.invalidateQueries({ queryKey: ['patients'] }); },
  });
  const open = card.alerts.filter((a) => !a.acknowledged_at);
  if (!open.length) return null;
  return (
    <Stack gap="xs">
      {open.map((a) => (
        <MAlert key={a.id} color={ALERT_LEVEL[a.level].color} variant={a.level === 'critical' ? 'filled' : 'light'}
          title={<Group gap="xs"><AlertLevelBadge level={a.level} /><span>{a.title}</span></Group>}>
          <Stack gap={4}>
            <Text size="xs">
              {formatDateTime(a.created_at)}
              {deliverySeconds(a) !== null ? ` · доставлено за ${deliverySeconds(a)} с` : ' · ещё не доставлено'}
            </Text>
            <Sources ids={a.sources} inverted={a.level === 'critical'} />
            <Group><Button size="xs" variant="white" color="dark" loading={ack.isPending}
              onClick={() => ack.mutate(a.id)}>Принято к сведению</Button></Group>
          </Stack>
        </MAlert>
      ))}
    </Stack>
  );
}

function RecommendationItem({ rec, patientId }: { rec: Recommendation; patientId: string }) {
  const qc = useQueryClient();
  const decide = useMutation({
    mutationFn: (decision: 'accepted' | 'rejected') =>
      api(`/doctor/recommendations/${rec.id}/decision`, { body: { decision } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['card', patientId] }),
  });
  return (
    <Card withBorder radius="md" style={rec.payload.level === 'mandatory' ? { borderColor: 'var(--mantine-color-red-6)',
      borderWidth: 2 } : undefined}>
      <Stack gap="xs">
        <Group justify="space-between">
          <Group gap="xs">
            {rec.payload.level && <ReferralBadge level={rec.payload.level} />}
            <Text fw={600}>{rec.title}</Text>
          </Group>
          {rec.status !== 'proposed' && (
            <Badge color={rec.status === 'accepted' ? 'teal' : 'gray'}>
              {rec.status === 'accepted' ? 'принято врачом' : 'отклонено врачом'}
            </Badge>
          )}
        </Group>
        {rec.payload.reason_ru && <Text size="sm">{rec.payload.reason_ru}</Text>}
        <Sources ids={rec.sources} />
        {rec.status === 'proposed' && (
          <Group>
            <Button size="xs" color="teal" loading={decide.isPending} onClick={() => decide.mutate('accepted')}>Принять</Button>
            <Button size="xs" variant="default" loading={decide.isPending} onClick={() => decide.mutate('rejected')}>
              Отклонить
            </Button>
            <Text size="xs" c="dimmed">Решение принимает врач</Text>
          </Group>
        )}
      </Stack>
    </Card>
  );
}

function PrescribeForm({ patientId }: { patientId: string }) {
  const qc = useQueryClient();
  const [dose, setDose] = useState<number | string>('');
  const [frequency, setFrequency] = useState('');
  const create = useMutation({
    mutationFn: () => api(`/doctor/patients/${patientId}/prescriptions`, { body: {
      drug_id: 'aviandr', drug_name: 'Авиандр', dose_mg: dose === '' ? null : Number(dose), frequency: frequency || null } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['card', patientId] }),
  });
  return (
    <Stack gap="xs">
      {/* TODO(Влад/Савва): режим дозирования, противопоказания и взаимодействия — из kb/drugs/aviandr.yaml (ГРЛС) */}
      <MAlert color="gray" variant="light">Справка по инструкции появится после заполнения kb/drugs/aviandr.yaml из ГРЛС.</MAlert>
      <Group align="flex-end">
        <NumberInput label="Доза, мг" value={dose} onChange={setDose} w={110} />
        <TextInput label="Режим" placeholder="по инструкции" value={frequency} onChange={(e) => setFrequency(e.currentTarget.value)} />
        <Button loading={create.isPending} onClick={() => create.mutate()}>Назначить Авиандр</Button>
      </Group>
    </Stack>
  );
}

export function PatientCardPage() {
  const { patientId = '' } = useParams();
  const { data: card } = useQuery({ queryKey: ['card', patientId],
    queryFn: () => api<PatientCard>(`/doctor/patients/${patientId}`) });
  if (!card) return <Text>Загрузка…</Text>;

  // Одна точка оси X на дату: результаты разных шкал за один день — в одной строке.
  const byDate = new Map<string, Record<string, number | string>>();
  const allResults = Object.values(card.scales).flat()
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  for (const r of allResults) {
    const date = formatDate(r.created_at);
    byDate.set(date, { ...(byDate.get(date) ?? { date }), [r.scale_id]: r.total });
  }
  const scaleSeries = [...byDate.values()];
  const diarySeries = card.diary.map((d) => ({ date: formatDate(d.day), Тревога: d.anxiety, Настроение: d.mood }));
  const active = card.prescriptions.filter((p) => p.active);

  return (
    <Stack>
      <Anchor component={Link} to="/doctor" size="sm">← Все пациенты</Anchor>
      <Title order={2}>{card.full_name}</Title>

      <AlertsBlock card={card} />

      {card.recommendations.length > 0 && (
        <Stack gap="xs">
          <Title order={4}>Предложения ассистента</Title>
          {card.recommendations.map((r) => <RecommendationItem key={r.id} rec={r} patientId={card.id} />)}
        </Stack>
      )}

      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Шкалы</Title>
          {scaleSeries.length ? (
            <LineChart h={220} data={scaleSeries} dataKey="date" connectNulls withLegend
              series={[{ name: 'gad7', label: 'GAD-7', color: 'violet.6' }, { name: 'phq9', label: 'PHQ-9', color: 'blue.6' }]} />
          ) : <Text c="dimmed" size="sm">Нет данных</Text>}
        </Card>
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Дневник пациента</Title>
          {diarySeries.length ? (
            <LineChart h={220} data={diarySeries} dataKey="date" withLegend yAxisProps={{ domain: [0, 10] }}
              series={[{ name: 'Тревога', color: 'red.6' }, { name: 'Настроение', color: 'teal.6' }]} />
          ) : <Text c="dimmed" size="sm">Нет данных</Text>}
        </Card>
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Терапия и приверженность</Title>
          <Stack gap="xs">
            {active.map((p) => (
              <Text key={p.id}>{p.drug_name}{p.dose_mg ? `, ${p.dose_mg} мг` : ''} — с {formatDate(p.start_date)}</Text>
            ))}
            <Text size="sm">
              Приверженность за 7 дней: {card.pdc_7d === null ? 'недостаточно данных' : `${Math.round(card.pdc_7d * 100)}%`}
            </Text>
            {active.length === 0 && <PrescribeForm patientId={card.id} />}
          </Stack>
        </Card>
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Нежелательные явления</Title>
          {card.adverse_events.length === 0 && <Text c="dimmed" size="sm">Не зарегистрированы</Text>}
          <Stack gap="xs">
            {card.adverse_events.map((ae) => (
              <Group key={ae.id} gap="xs" wrap="nowrap">
                {ae.serious && <Badge color="red">серьёзное</Badge>}
                <Text size="sm">{formatDate(ae.created_at)} — {ae.description}</Text>
              </Group>
            ))}
          </Stack>
        </Card>
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Чат с пациентом</Title>
          <Chat path={`/doctor/patients/${card.id}/messages`} />
        </Card>
      </SimpleGrid>
    </Stack>
  );
}
