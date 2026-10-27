import { useState } from 'react';
import { Alert as MAlert, Button, Card, Divider, Group, Modal, Select, Stack, Text, Textarea, TextInput,
  Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Anamnesis, type AnamnesisIn, type Diagnosis, type DiagnosisIn, type DiagnosisSource,
  type DiagnosisSourceIn, type PatientHistory } from '../api';
import { DIAGNOSIS_SOURCE, formatDateTime, formatFullDate, sourceLabel } from '../labels';

const FIELDS: { key: keyof AnamnesisIn; label: string }[] = [
  { key: 'complaints', label: 'Жалобы' },
  { key: 'history', label: 'История заболевания' },
  { key: 'notes', label: 'Примечания' },
];

const DIAGNOSIS_SOURCES = (Object.keys(DIAGNOSIS_SOURCE) as DiagnosisSource[])
  .map((s) => ({ value: s, label: DIAGNOSIS_SOURCE[s] }));

export function useHistory(patientId: string) {
  return useQuery({ queryKey: ['history', patientId],
    queryFn: () => api<PatientHistory>(`/doctor/patients/${patientId}/history`) });
}

/** Диагнозы и анализы видит проверка назначения (dx(), lab()) — после изменения пункты инструкции пересчитываются. */
export function useRefreshPatient(patientId: string) {
  const qc = useQueryClient();
  return () => {
    for (const key of ['history', 'card', 'rx-check']) qc.invalidateQueries({ queryKey: [key, patientId] });
  };
}

/** Жалобы, история заболевания, примечания: текст как есть, с переносами строк. */
export function AnamnesisText({ anamnesis }: { anamnesis: Anamnesis }) {
  const filled = FIELDS.filter((f) => anamnesis[f.key]);
  if (!filled.length) return <Text size="sm" c="dimmed">Анамнез ещё не заполнен</Text>;
  return (
    <Stack gap="xs">
      {filled.map((f) => (
        <div key={f.key}>
          <Text size="xs" fw={600} c="dimmed" tt="uppercase">{f.label}</Text>
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{anamnesis[f.key]}</Text>
        </div>
      ))}
    </Stack>
  );
}

export function updatedLine(a: Anamnesis): string | null {
  if (!a.updated_at) return null;
  return `Обновлено ${formatDateTime(a.updated_at)}${a.updated_by_name ? ` · ${a.updated_by_name}` : ''}`;
}

/** «выписка: выписка нефролога · поставлен 14.05.2024» */
export function diagnosisSourceLine(d: Diagnosis): string {
  const date = d.diagnosed_on ? ` · поставлен ${formatFullDate(d.diagnosed_on)}` : '';
  return `${sourceLabel(DIAGNOSIS_SOURCE, d.source, d.source_note)}${date}`;
}

function SourceFields({ value, onChange }: { value: DiagnosisSourceIn; onChange: (v: DiagnosisSourceIn) => void }) {
  return (
    <Group align="flex-end" gap="xs" wrap="wrap">
      <Select label="Откуда" w={170} allowDeselect={false} data={DIAGNOSIS_SOURCES} value={value.source}
        onChange={(s) => s && onChange({ ...value, source: s as DiagnosisSource })} />
      <TextInput label={value.source === 'other' ? 'Источник' : 'Уточнение'} required={value.source === 'other'}
        placeholder={value.source === 'other' ? 'Откуда диагноз' : 'Какая выписка, чей осмотр'} style={{ flex: 1 }}
        miw={180} value={value.source_note ?? ''} onChange={(e) => onChange({ ...value, source_note: e.currentTarget.value })} />
      <TextInput label="Дата постановки" type="date" w={160} value={value.diagnosed_on ?? ''}
        onChange={(e) => onChange({ ...value, diagnosed_on: e.currentTarget.value || null })} />
    </Group>
  );
}

const sourceReady = (v: DiagnosisSourceIn) => v.source !== 'other' || !!v.source_note?.trim();
const clean = (v: DiagnosisSourceIn): DiagnosisSourceIn => ({ ...v, source_note: v.source_note?.trim() || null });

function EditDiagnosisSource({ diagnosis: d, patientId }: { diagnosis: Diagnosis; patientId: string }) {
  const refresh = useRefreshPatient(patientId);
  const [opened, setOpened] = useState(false);
  const [value, setValue] = useState<DiagnosisSourceIn>({ source: 'exam', source_note: null, diagnosed_on: null });
  const save = useMutation({
    mutationFn: () => api<Diagnosis>(`/doctor/diagnoses/${d.id}`, { method: 'PATCH', body: clean(value) }),
    onSuccess: () => { setOpened(false); refresh(); },
  });
  const open = () => {
    setValue({ source: d.source ?? 'exam', source_note: d.source_note, diagnosed_on: d.diagnosed_on });
    save.reset();
    setOpened(true);
  };
  return (
    <>
      <Button size="compact-xs" variant="subtle" onClick={open}>{d.source ? 'Изменить источник' : 'Указать источник'}</Button>
      <Modal opened={opened} onClose={() => setOpened(false)} size="lg" centered
        title={<Text fw={600}>{d.icd10} {d.title}: откуда диагноз</Text>}>
        <Stack gap="sm">
          <SourceFields value={value} onChange={setValue} />
          {save.isError && <MAlert color="red" variant="light">{(save.error as Error).message}</MAlert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setOpened(false)}>Отмена</Button>
            <Button disabled={!sourceReady(value)} loading={save.isPending} onClick={() => save.mutate()}>Сохранить</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

function AddDiagnosis({ patientId }: { patientId: string }) {
  const refresh = useRefreshPatient(patientId);
  const empty = { icd10: '', title: '', source: 'exam' as DiagnosisSource, source_note: null, diagnosed_on: null };
  const [value, setValue] = useState<DiagnosisIn>(empty);
  const [opened, setOpened] = useState(false);
  const add = useMutation({
    mutationFn: () => api<Diagnosis>(`/doctor/patients/${patientId}/diagnoses`,
      { body: { ...clean(value), icd10: value.icd10.trim(), title: value.title.trim() } }),
    onSuccess: () => { setValue(empty); setOpened(false); refresh(); },
  });
  if (!opened) return <Group><Button size="xs" variant="light" onClick={() => setOpened(true)}>Добавить диагноз</Button></Group>;
  const ready = value.icd10.trim() !== '' && value.title.trim() !== '' && sourceReady(value);
  return (
    <Stack gap="xs">
      <Group align="flex-end" gap="xs">
        <TextInput label="Код МКБ-10" required w={110} value={value.icd10}
          onChange={(e) => setValue({ ...value, icd10: e.currentTarget.value })} />
        <TextInput label="Диагноз" required style={{ flex: 1 }} value={value.title}
          onChange={(e) => setValue({ ...value, title: e.currentTarget.value })} />
      </Group>
      <SourceFields value={value} onChange={(v) => setValue({ ...value, ...v })} />
      {add.isError && <MAlert color="red" variant="light">{(add.error as Error).message}</MAlert>}
      <Group>
        <Button size="xs" disabled={!ready} loading={add.isPending} onClick={() => add.mutate()}>Добавить</Button>
        <Button size="xs" variant="default" onClick={() => setOpened(false)}>Отмена</Button>
        <Text size="xs" c="dimmed">Диагноз запишется от вашего имени и попадёт в проверку назначения</Text>
      </Group>
    </Stack>
  );
}

function EditAnamnesis({ anamnesis, patientId, onDone }: { anamnesis: Anamnesis; patientId: string; onDone: () => void }) {
  const refresh = useRefreshPatient(patientId);
  const [value, setValue] = useState<AnamnesisIn>({
    complaints: anamnesis.complaints, history: anamnesis.history, notes: anamnesis.notes });
  const save = useMutation({
    mutationFn: () => api<Anamnesis>(`/doctor/patients/${patientId}/anamnesis`, { method: 'PUT', body: value }),
    onSuccess: () => { refresh(); onDone(); },
  });
  return (
    <Stack gap="xs">
      {FIELDS.map((f) => (
        <Textarea key={f.key} label={f.label} autosize minRows={2} maxRows={10} value={value[f.key] ?? ''}
          onChange={(e) => setValue({ ...value, [f.key]: e.currentTarget.value })} />
      ))}
      {save.isError && <MAlert color="red" variant="light">{(save.error as Error).message}</MAlert>}
      <Group>
        <Button size="xs" loading={save.isPending} onClick={() => save.mutate()}>Сохранить</Button>
        <Button size="xs" variant="default" onClick={onDone}>Отмена</Button>
        <Text size="xs" c="dimmed">Пациент видит анамнез в приложении, в разделе «Моя история»</Text>
      </Group>
    </Stack>
  );
}

/** Раздел «Анамнез» карточки: жалобы, история заболевания, примечания и диагнозы — откуда и когда поставлены. */
export function AnamnesisCard({ patientId }: { patientId: string }) {
  const { data } = useHistory(patientId);
  const [editing, setEditing] = useState(false);
  const updated = data && updatedLine(data.anamnesis);
  return (
    <Card withBorder radius="md">
      <Group justify="space-between" mb="sm">
        <Title order={4}>Анамнез</Title>
        {data && !editing && <Button size="xs" variant="subtle" onClick={() => setEditing(true)}>Изменить</Button>}
      </Group>
      {!data ? <Text size="sm" c="dimmed">Загрузка…</Text> : (
        <Stack gap="sm">
          {editing ? <EditAnamnesis anamnesis={data.anamnesis} patientId={patientId} onDone={() => setEditing(false)} />
            : <AnamnesisText anamnesis={data.anamnesis} />}
          {updated && <Text size="xs" c="dimmed">{updated}</Text>}
          <Divider label="Диагнозы" labelPosition="left" />
          {data.diagnoses.length === 0 && <Text size="sm" c="dimmed">Диагнозы не внесены</Text>}
          {data.diagnoses.map((d) => (
            <Stack key={d.id} gap={0}>
              <Text size="sm"><b>{d.icd10}</b> {d.title}</Text>
              <Group gap="xs">
                <Text size="xs" c={d.source ? 'dimmed' : 'orange'}>
                  {diagnosisSourceLine(d)}{d.confirmed ? ' · подтверждён врачом' : ' · не подтверждён'}
                </Text>
                <EditDiagnosisSource diagnosis={d} patientId={patientId} />
              </Group>
            </Stack>
          ))}
          <AddDiagnosis patientId={patientId} />
        </Stack>
      )}
    </Card>
  );
}
