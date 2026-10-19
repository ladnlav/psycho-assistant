import { useState } from 'react';
import { Badge, Button, Card, Checkbox, Group, SegmentedControl, SimpleGrid, Slider, Stack, Text, Textarea,
  Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router';
import { api, type Intake, type Prescription, type SafetyScreen, type Scale } from '../../api';
import { useAuth } from '../../auth';
import { Chat } from '../../components/Chat';
import { SafetyModal } from '../../components/SafetyModal';

function DiaryCard() {
  const [v, setV] = useState({ anxiety: 5, mood: 5, sleep_quality: 5 });
  const [note, setNote] = useState('');
  const save = useMutation({
    mutationFn: () => api('/patient/diary', { body: { ...v, note: note || null } }),
    onSuccess: () => notifications.show({ message: 'Записано. Спасибо!', color: 'teal' }),
  });
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
      <Stack>
        {slider('anxiety', 'Тревога', 'нет', 'максимум')}
        {slider('mood', 'Настроение', 'плохое', 'отличное')}
        {slider('sleep_quality', 'Сон', 'плохо', 'отлично')}
        <Textarea placeholder="Заметка (необязательно)" value={note} onChange={(e) => setNote(e.currentTarget.value)} />
        <Button onClick={() => save.mutate()} loading={save.isPending}>Сохранить</Button>
      </Stack>
    </Card>
  );
}

function MedicationCard() {
  const qc = useQueryClient();
  const { data: rx = [] } = useQuery({ queryKey: ['my-rx'], queryFn: () => api<Prescription[]>('/patient/prescriptions') });
  const { data: intakes = [] } = useQuery({ queryKey: ['my-intakes'], queryFn: () => api<Intake[]>('/patient/intakes') });
  const today = new Date().toISOString().slice(0, 10);
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

function AdverseEventCard() {
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState('mild');
  const [serious, setSerious] = useState(false);
  const send = useMutation({
    mutationFn: () => api('/patient/adverse-events', { body: { description, severity, serious } }),
    onSuccess: () => {
      setDescription('');
      setSerious(false);
      notifications.show({ message: 'Врач получит сообщение о побочном эффекте', color: 'orange' });
    },
  });
  return (
    <Card withBorder radius="md">
      <Title order={4} mb="sm">Сообщить о побочном эффекте</Title>
      <Stack>
        <Textarea placeholder="Что вы заметили?" value={description} onChange={(e) => setDescription(e.currentTarget.value)} />
        <SegmentedControl value={severity} onChange={setSeverity}
          data={[{ value: 'mild', label: 'Слабо' }, { value: 'moderate', label: 'Умеренно' }, { value: 'severe', label: 'Сильно' }]} />
        <Checkbox checked={serious} onChange={(e) => setSerious(e.currentTarget.checked)}
          label="Понадобилась медицинская помощь или состояние резко ухудшилось" />
        <Button color="orange" disabled={!description.trim()} loading={send.isPending} onClick={() => send.mutate()}>
          Отправить врачу
        </Button>
      </Stack>
    </Card>
  );
}

export function PatientHome() {
  const { me } = useAuth();
  const [safety, setSafety] = useState<SafetyScreen | null>(null);
  const { data: scales = [] } = useQuery({ queryKey: ['my-scales'], queryFn: () => api<Scale[]>('/patient/scales') });
  return (
    <Stack>
      <Group justify="space-between">
        <div>
          <Title order={2}>Здравствуйте, {me?.full_name}</Title>
          {me?.doctor_name && <Text c="dimmed">Ваш врач: {me.doctor_name}</Text>}
        </div>
        <Button color="red" variant="light" onClick={async () => setSafety(await api<SafetyScreen>('/patient/safety'))}>
          Нужна срочная помощь
        </Button>
      </Group>
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <DiaryCard />
        <Stack>
          <MedicationCard />
          <Card withBorder radius="md">
            <Title order={4} mb="sm">Опросники</Title>
            <Stack gap="xs">
              {scales.map((s) => (
                <Group key={s.id} justify="space-between">
                  <Text size="sm">{s.title_ru}</Text>
                  <Button size="xs" component={Link} to={`/patient/scales/${s.id}`}>Заполнить</Button>
                </Group>
              ))}
            </Stack>
          </Card>
        </Stack>
        <AdverseEventCard />
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Чат с врачом</Title>
          <Chat path="/patient/messages" />
        </Card>
      </SimpleGrid>
      <SafetyModal safety={safety} onClose={() => setSafety(null)} />
    </Stack>
  );
}
