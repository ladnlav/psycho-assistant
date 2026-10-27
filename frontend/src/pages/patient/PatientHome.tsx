import { useState } from 'react';
import { Alert as MAlert, Badge, Button, Card, Checkbox, Group, SegmentedControl, SimpleGrid, Slider, Stack, Text,
  Textarea, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router';
import { api, type AdverseEvent, type AdverseEventSent, type DiaryEntry, type Intake, type Prescription,
  type Reminder, type SafetyScreen, type Scale, type ScaleSchedule } from '../../api';
import { useAuth } from '../../auth';
import { Chat } from '../../components/Chat';
import { Done } from '../../components/Done';
import { MyHistory } from '../../components/MyHistory';
import { SafetyModal } from '../../components/SafetyModal';
import { AE_SEVERITY, formatDate, formatDateTime } from '../../labels';

/** Дата «сегодня» в том же виде, что и day на сервере (UTC). */
const todayIso = () => new Date().toISOString().slice(0, 10);

function DiaryCard() {
  const qc = useQueryClient();
  const { data: diary, isLoading } = useQuery({ queryKey: ['my-diary'], queryFn: () => api<DiaryEntry[]>('/patient/diary') });
  const todayEntry = diary?.find((d) => d.day === todayIso());
  const [editing, setEditing] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [v, setV] = useState({ anxiety: 5, mood: 5, sleep_quality: 5 });
  const [note, setNote] = useState('');
  const save = useMutation({
    mutationFn: () => api('/patient/diary', { body: { ...v, note: note || null } }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['my-diary'] });
      qc.invalidateQueries({ queryKey: ['my-reminders'] });
      setEditing(false);
      setJustSaved(true);
    },
  });
  const edit = () => {
    if (todayEntry) {
      setV({ anxiety: todayEntry.anxiety, mood: todayEntry.mood, sleep_quality: todayEntry.sleep_quality ?? 5 });
      setNote(todayEntry.note ?? '');
    }
    setEditing(true);
  };
  const slider = (key: keyof typeof v, label: string, left: string, right: string) => (
    <Stack gap={4}>
      <Group justify="space-between"><Text size="sm" fw={500}>{label}</Text><Badge>{v[key]}</Badge></Group>
      <Slider min={0} max={10} step={1} value={v[key]} onChange={(x) => setV((s) => ({ ...s, [key]: x }))}
        label={null} aria-label={label} mx="xl" />
      <Group justify="space-between"><Text size="xs" c="dimmed">{left}</Text><Text size="xs" c="dimmed">{right}</Text></Group>
    </Stack>
  );
  return (
    <Card withBorder radius="md">
      <Title order={4} mb="sm">Как вы сегодня?</Title>
      {isLoading ? null : todayEntry && !editing ? (
        <Stack gap="xs">
          <Done animate={justSaved}>
            <Text size="sm" fw={500}>Сегодня отмечено</Text>
            <Text size="sm" c="dimmed">
              Тревога {todayEntry.anxiety} · настроение {todayEntry.mood}
              {todayEntry.sleep_quality !== null ? ` · сон ${todayEntry.sleep_quality}` : ''}
            </Text>
          </Done>
          <Group><Button size="xs" variant="subtle" onClick={edit}>Изменить</Button></Group>
        </Stack>
      ) : (
        <Stack>
          {slider('anxiety', 'Тревога', 'нет', 'максимум')}
          {slider('mood', 'Настроение', 'плохое', 'отличное')}
          {slider('sleep_quality', 'Сон', 'плохо', 'отлично')}
          <Textarea placeholder="Заметка (необязательно)" value={note} onChange={(e) => setNote(e.currentTarget.value)} />
          <Button onClick={() => save.mutate()} loading={save.isPending}>
            {todayEntry ? 'Сохранить исправление' : 'Сохранить'}
          </Button>
          {editing && <Button variant="default" onClick={() => setEditing(false)}>Отмена</Button>}
        </Stack>
      )}
    </Card>
  );
}

function MedicationCard() {
  const qc = useQueryClient();
  const { data: rx = [] } = useQuery({ queryKey: ['my-rx'], queryFn: () => api<Prescription[]>('/patient/prescriptions') });
  const { data: intakes = [] } = useQuery({ queryKey: ['my-intakes'], queryFn: () => api<Intake[]>('/patient/intakes') });
  const today = todayIso();
  const mark = useMutation({
    mutationFn: (b: { prescription_id: string; status: 'taken' | 'missed' }) => api('/patient/intakes', { body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-intakes'] }),
  });
  return (
    <Card withBorder radius="md">
      <Title order={4} mb="sm">Приём препаратов</Title>
      {rx.length === 0 && <Text c="dimmed" size="sm">Врач пока ничего не назначил</Text>}
      <Stack>
        {rx.map((p) => {
          const todayMark = intakes.find((i) => i.prescription_id === p.id && i.day === today);
          return (
            <Stack key={p.id} gap={6}>
              <Text fw={500}>{p.drug_name}{p.dose_mg ? `, ${p.dose_mg} мг` : ''}{p.frequency ? ` — ${p.frequency}` : ''}</Text>
              <Group>
                <Button size="xs" color="teal" variant={todayMark?.status === 'taken' ? 'filled' : 'light'}
                  onClick={() => mark.mutate({ prescription_id: p.id, status: 'taken' })}>Принял сегодня</Button>
                <Button size="xs" color="gray" variant={todayMark?.status === 'missed' ? 'filled' : 'light'}
                  onClick={() => mark.mutate({ prescription_id: p.id, status: 'missed' })}>Пропустил</Button>
              </Group>
            </Stack>
          );
        })}
      </Stack>
    </Card>
  );
}

function ScalesCard() {
  const justDone = (useLocation().state as { justDone?: string } | null)?.justDone;
  const { data: scales = [] } = useQuery({ queryKey: ['my-scales'], queryFn: () => api<Scale[]>('/patient/scales') });
  const { data: schedule = [] } = useQuery({
    queryKey: ['my-schedule'], queryFn: () => api<ScaleSchedule[]>('/patient/scales/schedule'),
  });
  return (
    <Card withBorder radius="md">
      <Title order={4} mb="sm">Опросники</Title>
      <Stack gap="md">
        {scales.map((s) => {
          const plan = schedule.find((x) => x.scale_id === s.id);
          const link = `/patient/scales/${s.id}`;
          if (!plan || plan.due || !plan.last_taken_at || !plan.next_due) {
            return (
              <Group key={s.id} justify="space-between" wrap="nowrap">
                <div>
                  <Text size="sm">{s.title_ru}</Text>
                  {plan?.last_taken_at && (
                    <Text size="xs" c="dimmed">Пора заполнить · последний раз {formatDate(plan.last_taken_at)}</Text>
                  )}
                </div>
                <Button size="xs" component={Link} to={link}>Заполнить</Button>
              </Group>
            );
          }
          return (
            <Stack key={s.id} gap={6}>
              <Text size="sm">{s.title_ru}</Text>
              <Done animate={justDone === s.id}>
                <Text size="sm">Заполнено {formatDate(plan.last_taken_at)} · следующий — {formatDate(plan.next_due)}</Text>
              </Done>
              <Group>
                <Button size="xs" variant="subtle" color="gray" component={Link} to={link}>
                  Стало хуже — пройти сейчас
                </Button>
              </Group>
            </Stack>
          );
        })}
      </Stack>
    </Card>
  );
}

function AdverseEventCard({ onSafety }: { onSafety: (safety: SafetyScreen) => void }) {
  const qc = useQueryClient();
  const { data: sent = [] } = useQuery({
    queryKey: ['my-adverse-events'], queryFn: () => api<AdverseEvent[]>('/patient/adverse-events'),
  });
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState('mild');
  const [serious, setSerious] = useState(false);
  const [lastSent, setLastSent] = useState<AdverseEvent | null>(null);
  const send = useMutation({
    mutationFn: () => api<AdverseEventSent>('/patient/adverse-events', { body: { description, severity, serious } }),
    onSuccess: (ae) => {
      if (ae.safety) onSafety(ae.safety); // в описании есть признаки риска — сразу экран помощи
      setDescription('');
      setSeverity('mild');
      setSerious(false);
      setLastSent(ae);
      qc.invalidateQueries({ queryKey: ['my-adverse-events'] });
    },
  });
  return (
    <Card withBorder radius="md">
      <Title order={4} mb="sm">Сообщить о побочном эффекте</Title>
      <Stack>
        {lastSent && (
          <Done animate key={lastSent.id}>
            <Text size="sm" fw={500}>Отправлено врачу {formatDateTime(lastSent.created_at)}</Text>
            <Text size="xs" c="dimmed">Если заметите что-то ещё — сообщите снова.</Text>
          </Done>
        )}
        <Textarea placeholder="Что вы заметили?" value={description} onChange={(e) => setDescription(e.currentTarget.value)} />
        <SegmentedControl value={severity} onChange={setSeverity}
          data={[{ value: 'mild', label: 'Слабо' }, { value: 'moderate', label: 'Умеренно' }, { value: 'severe', label: 'Сильно' }]} />
        <Checkbox checked={serious} onChange={(e) => setSerious(e.currentTarget.checked)}
          label="Понадобилась медицинская помощь или состояние резко ухудшилось" />
        <Button color="orange" disabled={!description.trim()} loading={send.isPending} onClick={() => send.mutate()}>
          Отправить врачу
        </Button>
        {sent.length > 0 && (
          <Stack gap={4}>
            <Text size="sm" fw={500}>Вы уже сообщали</Text>
            {sent.slice(0, 5).map((a) => (
              <Text key={a.id} size="xs" c="dimmed" lineClamp={1}>
                {formatDateTime(a.created_at)} · {AE_SEVERITY[a.severity] ?? a.severity}
                {a.serious ? ' · нужна была помощь' : ''} — {a.description}
              </Text>
            ))}
          </Stack>
        )}
      </Stack>
    </Card>
  );
}

/** Напоминания из правил базы знаний (например, «нет записей 3 дня»). Синие — не путать с красным экраном помощи.
 *  Любая запись пациента снимает напоминание: дневник обновляет его сразу, остальное — при следующем опросе. */
function Reminders() {
  const { data = [] } = useQuery({ queryKey: ['my-reminders'], queryFn: () => api<Reminder[]>('/patient/reminders'),
    refetchInterval: 15_000 });
  if (!data.length) return null;
  return (
    <Stack gap="xs">
      {data.map((r) => <MAlert key={r.rule_id} color="blue" variant="light" title="Напоминание">{r.text_ru}</MAlert>)}
    </Stack>
  );
}

export function PatientHome() {
  const { me } = useAuth();
  const [safety, setSafety] = useState<SafetyScreen | null>(null);
  const [askReason, setAskReason] = useState(false); // экран открыт кнопкой — можно написать врачу, что случилось
  const showSafety = (screen: SafetyScreen) => { setAskReason(false); setSafety(screen); };
  return (
    <Stack>
      <Group justify="space-between">
        <div>
          <Title order={2}>Здравствуйте, {me?.full_name}</Title>
          {me?.doctor_name && <Text c="dimmed">Ваш врач: {me.doctor_name}</Text>}
        </div>
        <Button color="red" variant="light" onClick={async () => { setAskReason(true); setSafety(await api<SafetyScreen>('/patient/safety')); }}>
          Нужна срочная помощь
        </Button>
      </Group>
      <Reminders />
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <DiaryCard />
        <Stack>
          <MedicationCard />
          <ScalesCard />
        </Stack>
        <AdverseEventCard onSafety={showSafety} />
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Чат с врачом</Title>
          <Chat path="/patient/messages" onSafety={showSafety} />
        </Card>
        <MyHistory />
      </SimpleGrid>
      <SafetyModal safety={safety} askReason={askReason} onClose={() => setSafety(null)} />
    </Stack>
  );
}
