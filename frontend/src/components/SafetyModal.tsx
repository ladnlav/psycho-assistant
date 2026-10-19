import { Anchor, Modal, Stack, Text, Title } from '@mantine/core';
import type { SafetyScreen } from '../api';

export function SafetyModal({ safety, onClose }: { safety: SafetyScreen | null; onClose: () => void }) {
  return (
    <Modal opened={!!safety} onClose={onClose} title={<Title order={3} c="red">Вам нужна поддержка</Title>}
      centered size="md">
      {safety && (
        <Stack>
          <Text>{safety.message_ru}</Text>
          {safety.contacts.map((c) => (
            <Text key={c.phone} size="lg">
              {c.title_ru}: <Anchor href={`tel:${c.phone}`} fw={700}>{c.phone}</Anchor>
            </Text>
          ))}
        </Stack>
      )}
    </Modal>
  );
}
