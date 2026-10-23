import { useState } from 'react';
import { Button, Group, Paper, ScrollArea, Stack, Text, Textarea } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Message, type MessageSent, type SafetyScreen } from '../api';
import { useAuth } from '../auth';
import { formatDateTime } from '../labels';

/** Чат врач–пациент. path: '/patient/messages' или '/doctor/patients/{id}/messages'.
 *  onSafety — у пациента: сервер прислал экран помощи, потому что в сообщении есть признаки риска.
 *  TODO: WebSocket вместо опроса раз в 5 с. */
export function Chat({ path, onSafety }: { path: string; onSafety?: (safety: SafetyScreen) => void }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const { data = [] } = useQuery({ queryKey: ['messages', path], queryFn: () => api<Message[]>(path),
    refetchInterval: 5000 });
  const send = useMutation({
    mutationFn: (body: string) => api<MessageSent>(path, { body: { body } }),
    onSuccess: (sent) => {
      setText('');
      if (sent.safety) onSafety?.(sent.safety);
      qc.invalidateQueries({ queryKey: ['messages', path] });
    },
  });

  return (
    <Stack gap="xs">
      <ScrollArea h={240} type="auto">
        <Stack gap={6}>
          {data.length === 0 && <Text c="dimmed" size="sm">Сообщений пока нет</Text>}
          {data.map((m) => {
            const mine = m.sender_id === me?.id;
            return (
              <Group key={m.id} justify={mine ? 'flex-end' : 'flex-start'}>
                <Paper p="xs" radius="md" bg={mine ? 'violet.0' : 'gray.0'} maw="80%">
                  <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{m.body}</Text>
                  <Text size="xs" c="dimmed" ta="right">{formatDateTime(m.created_at)}</Text>
                </Paper>
              </Group>
            );
          })}
        </Stack>
      </ScrollArea>
      <Group align="flex-end" wrap="nowrap">
        <Textarea style={{ flex: 1 }} autosize minRows={1} maxRows={4} placeholder="Сообщение"
          value={text} onChange={(e) => setText(e.currentTarget.value)} />
        <Button onClick={() => text.trim() && send.mutate(text.trim())} loading={send.isPending}>Отправить</Button>
      </Group>
    </Stack>
  );
}
