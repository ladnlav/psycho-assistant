import { Card, Divider, Stack, Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { api, type PatientHistory } from '../api';
import { AnamnesisText, diagnosisSourceLine, updatedLine } from './Anamnesis';
import { LatestLabs } from './Labs';

/** «Моя история» у пациента: то, что записал врач, — только для чтения. */
export function MyHistory() {
  const { data } = useQuery({ queryKey: ['my-history'], queryFn: () => api<PatientHistory>('/patient/history') });
  if (!data) return null;
  const updated = updatedLine(data.anamnesis);
  return (
    <Card withBorder radius="md">
      <Title order={4} mb="sm">Моя история</Title>
      <Stack gap="sm">
        <AnamnesisText anamnesis={data.anamnesis} />
        {updated && <Text size="xs" c="dimmed">{updated}</Text>}
        <Divider label="Диагнозы" labelPosition="left" />
        {data.diagnoses.length === 0 && <Text size="sm" c="dimmed">Диагнозы не внесены</Text>}
        {data.diagnoses.map((d) => (
          <Stack key={d.id} gap={0}>
            <Text size="sm">{d.title} <Text span size="xs" c="dimmed">({d.icd10})</Text></Text>
            <Text size="xs" c="dimmed">{diagnosisSourceLine(d)}</Text>
          </Stack>
        ))}
        <Divider label="Анализы" labelPosition="left" />
        <LatestLabs history={data} compact />
        <Text size="xs" c="dimmed">Если что-то записано неточно, напишите врачу в чат.</Text>
      </Stack>
    </Card>
  );
}
