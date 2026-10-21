import { useState } from 'react';
import { Alert, Badge, Button, Card, Group, Radio, Stack, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { api, type Scale, type ScaleSubmitResult } from '../../api';
import { SafetyModal } from '../../components/SafetyModal';
import { plural, SEVERITY_COLOR } from '../../labels';

export function ScalePage() {
  const { scaleId } = useParams();
  const { data: scales } = useQuery({ queryKey: ['my-scales'], queryFn: () => api<Scale[]>('/patient/scales') });
  const scale = scales?.find((s) => s.id === scaleId);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [safetyClosed, setSafetyClosed] = useState(false);
  const qc = useQueryClient();
  const submit = useMutation({
    mutationFn: () => api<ScaleSubmitResult>(`/patient/scales/${scaleId}`, { body: { answers } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-schedule'] }),
  });

  if (!scale) return <Text>Загрузка…</Text>;
  const complete = scale.items.every((i) => answers[i.id] !== undefined);
  const result = submit.data;

  if (result) {
    return (
      <Card withBorder radius="md" maw={640} mx="auto">
        <Stack>
          <Title order={3}>
            {scale.name}: {result.result.total} {plural(result.result.total, 'балл', 'балла', 'баллов')}
          </Title>
          <Badge size="lg" color={SEVERITY_COLOR[result.result.severity] ?? 'gray'}>{result.severity_label_ru}</Badge>
          <Text c="dimmed">Результат передан вашему врачу.</Text>
          <Button component={Link} to="/patient" state={{ justDone: scale.id }}>На главную</Button>
        </Stack>
        <SafetyModal safety={safetyClosed ? null : result.safety} onClose={() => setSafetyClosed(true)} />
      </Card>
    );
  }

  return (
    <Card withBorder radius="md" maw={720} mx="auto">
      <Stack>
        <Group justify="space-between">
          <Title order={3}>{scale.title_ru}</Title>
          {scale.status !== 'validated' && <Badge color="gray" variant="outline">черновик</Badge>}
        </Group>
        {!scale.instruction_ru && (
          <Alert color="gray" variant="light">Официальный русский текст шкалы ещё не внесён — показан оригинал.</Alert>
        )}
        <Text fw={500}>{scale.instruction_ru ?? scale.instruction_en}</Text>
        {scale.items.map((item, idx) => (
          <Radio.Group key={item.id} label={`${idx + 1}. ${item.text_ru ?? item.text_en}`}
            value={answers[item.id]?.toString() ?? null}
            onChange={(v) => setAnswers((a) => ({ ...a, [item.id]: Number(v) }))}>
            <Group mt={6} gap="md">
              {scale.options.map((o) => (
                <Radio key={o.value} value={o.value.toString()} label={o.label_ru ?? o.label_en} />
              ))}
            </Group>
          </Radio.Group>
        ))}
        {submit.isError && <Alert color="red">{(submit.error as Error).message}</Alert>}
        <Button disabled={!complete} loading={submit.isPending} onClick={() => submit.mutate()}>Отправить</Button>
      </Stack>
    </Card>
  );
}
