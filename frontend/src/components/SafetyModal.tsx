import { useState } from 'react';
import { Anchor, Button, Divider, Modal, Stack, Text, Textarea, Title } from '@mantine/core';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, type MessageSent, type SafetyScreen } from '../api';
import { formatDateTime } from '../labels';
import { Done } from './Done';

/** Экран помощи. askReason — открыт кнопкой «Нужна срочная помощь»: номера 112/103 видны сразу,
 *  а ниже пациент может написать, что случилось; только тогда причина уходит врачу (чат и алерт). */
export function SafetyModal({ safety, onClose, askReason = false }:
  { safety: SafetyScreen | null; onClose: () => void; askReason?: boolean }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState('');
  const send = useMutation({
    mutationFn: () => api<MessageSent>('/patient/help', { body: { reason: reason.trim() } }),
    onSuccess: () => {
      setReason('');
      qc.invalidateQueries({ queryKey: ['messages', '/patient/messages'] });
      qc.invalidateQueries({ queryKey: ['my-reminders'] });
    },
  });
  const close = () => { send.reset(); setReason(''); onClose(); };
  return (
    <Modal opened={!!safety} onClose={close} title={<Title order={3} c="red">Вам нужна поддержка</Title>}
      centered size="md">
      {safety && (
        <Stack>
          <Text>{safety.message_ru}</Text>
          {safety.contacts.map((c) => (
            <Text key={c.phone} size="lg">
              {c.title_ru}: <Anchor href={`tel:${c.phone.replace(/[^\d+]/g, '')}`} fw={700}>{c.phone}</Anchor>
            </Text>
          ))}
          {askReason && (
            <>
              <Divider />
              {send.isSuccess ? (
                <Done animate>
                  <Text size="sm" fw={500}>Отправлено врачу {formatDateTime(send.data.created_at)}</Text>
                  <Text size="xs" c="dimmed">Врач может ответить не сразу. Если опасность сейчас — звоните 112 или 103.</Text>
                </Done>
              ) : (
                <Stack gap="xs">
                  <Text size="sm" fw={500}>Что случилось? Врач получит ваше сообщение</Text>
                  <Textarea placeholder="Опишите своими словами" autosize minRows={2} maxRows={5}
                    value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
                  <Button color="red" disabled={!reason.trim()} loading={send.isPending} onClick={() => send.mutate()}>
                    Отправить врачу
                  </Button>
                  {send.isError && <Text size="sm" c="red">{(send.error as Error).message}</Text>}
                </Stack>
              )}
            </>
          )}
        </Stack>
      )}
    </Modal>
  );
}
