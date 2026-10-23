import { useState } from 'react';
import { Alert as MAlert, Anchor, Badge, Button, Card, Group, NumberInput, SimpleGrid, Stack, Text, Textarea,
  TextInput, Title, Tooltip } from '@mantine/core';
import { LineChart } from '@mantine/charts';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { api, type Alert, type Diagnosis, type PatientCard, type PrescriptionCheck, type Recommendation } from '../../api';
import { AlertLevelBadge, ReferralBadge } from '../../components/Badges';
import { Chat } from '../../components/Chat';
import { DrugWarnings } from '../../components/DrugWarnings';
import { Sources } from '../../components/Sources';
import { ALERT_LEVEL, formatDate, formatDateTime } from '../../labels';

function deliverySeconds(a: Alert): string | null {
  if (!a.delivered_at) return null;
  const s = (new Date(a.delivered_at).getTime() - new Date(a.created_at).getTime()) / 1000;
  return s.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

/** Диагнозы — справочная строка под ФИО: нейтральный серый, чтобы не спорить с алертами и направлениями. */
function Diagnoses({ items }: { items: Diagnosis[] }) {
  if (!items.length) return <Text size="sm" c="dimmed">Диагнозы не внесены</Text>;
  return (
    <Group gap="xs">
      {items.map((d) => (
        <Tooltip key={d.id} label={d.confirmed ? 'Подтверждён врачом' : 'Не подтверждён врачом'}>
          <Badge size="lg" tt="none" color="gray" variant={d.confirmed ? 'light' : 'outline'}>
            <b>{d.icd10}</b> {d.title}{d.confirmed ? '' : ' · не подтверждён'}
          </Badge>
        </Tooltip>
      ))}
    </Group>
  );
}

function AlertsBlock({ card }: { card: PatientCard }) {
  const qc = useQueryClient();
  const ack = useMutation({
    mutationFn: (id: string) => api(`/doctor/alerts/${id}/ack`, { method: 'POST' }),
    onSuccess: (_, id) => {
      notifications.hide(id); // критичные уведомления не закрываются сами — убираем после подтверждения
      qc.invalidateQueries({ queryKey: ['card', card.id] });
      qc.invalidateQueries({ queryKey: ['patients'] });
    },
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
              {a.updated_at && ` · новые данные ${formatDateTime(a.updated_at)}`}
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

const AVIANDR = { drug_id: 'aviandr', drug_name: 'Авиандр' };

function PrescribeForm({ patientId }: { patientId: string }) {
  const qc = useQueryClient();
  const [dose, setDose] = useState<number | string>('');
  const [frequency, setFrequency] = useState('');
  const [acked, setAcked] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState('');
  // Пункты инструкции показываем сразу, ещё до нажатия «Назначить».
  const { data: check } = useQuery({ queryKey: ['rx-check', patientId, AVIANDR.drug_id],
    queryFn: () => api<PrescriptionCheck>(`/doctor/patients/${patientId}/prescriptions/check`, { body: AVIANDR }) });
  const warnings = check?.warnings ?? [];
  const needReason = warnings.some((w) => w.requires_reason);
  const ready = !!check && warnings.every((w) => acked[w.id]) && (!needReason || note.trim() !== '');
  const create = useMutation({
    mutationFn: () => api(`/doctor/patients/${patientId}/prescriptions`, { body: {
      ...AVIANDR, dose_mg: dose === '' ? null : Number(dose), frequency: frequency || null,
      acknowledged_warnings: warnings.filter((w) => acked[w.id]).map((w) => w.id), override_note: note.trim() || null } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['card', patientId] }),
    onError: () => qc.invalidateQueries({ queryKey: ['rx-check', patientId] }), // данные пациента могли измениться
  });
  return (
    <Stack gap="xs">
      {check?.notice_ru && <MAlert color="gray" variant="light">{check.notice_ru}</MAlert>}
      {warnings.length > 0 && (
        <>
          <Text size="sm" fw={500}>Перед назначением отметьте каждый пункт инструкции</Text>
          <DrugWarnings warnings={warnings} acked={acked} onAck={(id, v) => setAcked((a) => ({ ...a, [id]: v }))} />
          {needReason && (
            <Textarea label="Почему назначаете, несмотря на противопоказание" required value={note}
              onChange={(e) => setNote(e.currentTarget.value)} />
          )}
        </>
      )}
      <Group align="flex-end">
        <NumberInput label="Доза, мг" value={dose} onChange={setDose} w={110} />
        <TextInput label="Режим" placeholder="по инструкции" value={frequency} onChange={(e) => setFrequency(e.currentTarget.value)} />
        <Button disabled={!ready} loading={create.isPending} onClick={() => create.mutate()}>Назначить Авиандр</Button>
      </Group>
      {create.isError && <MAlert color="red" variant="light">{(create.error as Error).message}</MAlert>}
    </Stack>
  );
}

export function PatientCardPage() {
  const { patientId = '' } = useParams();
  // Записи пациента без алерта (дневник, приём, лёгкий побочный эффект) по WebSocket не приходят — опрашиваем, как чат.
  const { data: card } = useQuery({ queryKey: ['card', patientId], refetchInterval: 10_000,
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
      <Stack gap={6}>
        <Title order={2}>{card.full_name}</Title>
        <Diagnoses items={card.diagnoses} />
      </Stack>

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
