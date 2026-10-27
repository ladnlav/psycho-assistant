import { useState } from 'react';
import { Alert as MAlert, Button, Card, Divider, Group, NumberInput, Select, Stack, Table, Text, TextInput,
  Title } from '@mantine/core';
import { useMutation } from '@tanstack/react-query';
import { api, type LabResult, type LabResultIn, type LabSource, type PatientHistory } from '../api';
import { LAB_SOURCE, formatFullDate, labValue, sourceLabel } from '../labels';
import { useHistory, useRefreshPatient } from './Anamnesis';

const LAB_SOURCES = (Object.keys(LAB_SOURCE) as LabSource[]).map((s) => ({ value: s, label: LAB_SOURCE[s] }));

/** Последние значения по каждому показателю из kb/labs.yaml; earlier — предыдущие результаты (labs уже по убыванию даты). */
export function LatestLabs({ history, compact = false }: { history: PatientHistory; compact?: boolean }) {
  const rows = history.lab_tests.map((t) => {
    const all = history.labs.filter((r) => r.analyte === t.id);
    return { test: t, last: all[0] as LabResult | undefined, earlier: all.slice(1, 3) };
  }).filter((r) => !compact || r.last);
  if (compact && !rows.length) return <Text size="sm" c="dimmed">Анализов нет</Text>;
  return (
    <Table verticalSpacing={4} horizontalSpacing="xs">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Показатель</Table.Th>
          <Table.Th>Последнее значение</Table.Th>
          <Table.Th>Дата сдачи</Table.Th>
          {!compact && <Table.Th>Источник</Table.Th>}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {rows.map(({ test, last, earlier }) => (
          <Table.Tr key={test.id}>
            <Table.Td><Text size="sm" title={test.name_ru ?? undefined}>{test.title_ru}</Text></Table.Td>
            <Table.Td>
              {last ? <Text size="sm" fw={500} style={{ whiteSpace: 'nowrap' }}>{labValue(last.value, last.unit)}</Text> : <Text size="sm" c="dimmed">нет</Text>}
              {!compact && earlier.length > 0 && (
                <Text size="xs" c="dimmed">
                  ранее: {earlier.map((r) => `${labValue(r.value, r.unit)} (${formatFullDate(r.taken_on)})`).join('; ')}
                </Text>
              )}
            </Table.Td>
            <Table.Td><Text size="sm" style={{ whiteSpace: 'nowrap' }}>{last ? formatFullDate(last.taken_on) : ''}</Text></Table.Td>
            {!compact && (
              <Table.Td><Text size="xs" c="dimmed">{last ? sourceLabel(LAB_SOURCE, last.source, last.source_note) : ''}</Text></Table.Td>
            )}
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

const todayIso = () => new Date().toISOString().slice(0, 10);

function AddLabResult({ history, patientId }: { history: PatientHistory; patientId: string }) {
  const refresh = useRefreshPatient(patientId);
  const [analyte, setAnalyte] = useState<string | null>(null);
  const [value, setValue] = useState<number | string>('');
  const [takenOn, setTakenOn] = useState(todayIso());
  const [source, setSource] = useState<LabSource>('lab');
  const [note, setNote] = useState('');
  const test = history.lab_tests.find((t) => t.id === analyte);
  const add = useMutation({
    mutationFn: (body: LabResultIn) => api<LabResult>(`/doctor/patients/${patientId}/labs`, { body }),
    onSuccess: () => { setValue(''); setNote(''); refresh(); },
  });
  const ready = !!analyte && value !== '' && !!takenOn && (source !== 'other' || note.trim() !== '');
  return (
    <Stack gap="xs">
      <Group align="flex-end" gap="xs" wrap="wrap">
        <Select label="Показатель" placeholder="Выберите" w={170} allowDeselect={false} value={analyte} onChange={setAnalyte}
          data={history.lab_tests.map((t) => ({ value: t.id, label: t.title_ru }))} />
        <NumberInput label="Значение" w={test?.unit ? 210 : 120} min={0} hideControls value={value} onChange={setValue}
          rightSection={test?.unit ? <Text size="xs" c="dimmed" pr={6} style={{ whiteSpace: 'nowrap' }}>{test.unit}</Text>
            : undefined} rightSectionWidth={test?.unit ? 100 : undefined} rightSectionPointerEvents="none" />
        <TextInput label="Дата сдачи" type="date" w={160} value={takenOn} onChange={(e) => setTakenOn(e.currentTarget.value)} />
      </Group>
      <Group align="flex-end" gap="xs" wrap="wrap">
        <Select label="Источник" w={170} allowDeselect={false} data={LAB_SOURCES} value={source}
          onChange={(s) => s && setSource(s as LabSource)} />
        <TextInput label={source === 'other' ? 'Откуда результат' : 'Уточнение'} required={source === 'other'}
          placeholder="Лаборатория, выписка" style={{ flex: 1 }} miw={180} value={note}
          onChange={(e) => setNote(e.currentTarget.value)} />
        <Button disabled={!ready} loading={add.isPending} onClick={() => ready && add.mutate({
          analyte: analyte as string, value: Number(value), taken_on: takenOn, source, source_note: note.trim() || null })}>Внести</Button>
      </Group>
      {add.isError && <MAlert color="red" variant="light">{(add.error as Error).message}</MAlert>}
      <Text size="xs" c="dimmed">
        Ошиблись — внесите результат ещё раз с той же датой сдачи. Анализы видит проверка назначения; класс и стадию
        по ним система не вычисляет.
      </Text>
    </Stack>
  );
}

/** Раздел «Лабораторные исследования»: последние значения с датами и внесение результата врачом. */
export function LabsCard({ patientId }: { patientId: string }) {
  const { data } = useHistory(patientId);
  return (
    <Card withBorder radius="md">
      <Title order={4} mb="sm">Лабораторные исследования</Title>
      {!data ? <Text size="sm" c="dimmed">Загрузка…</Text> : (
        <Stack gap="sm">
          <LatestLabs history={data} />
          <Divider label="Внести результат" labelPosition="left" />
          <AddLabResult history={data} patientId={patientId} />
        </Stack>
      )}
    </Card>
  );
}
