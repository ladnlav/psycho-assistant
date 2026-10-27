import { Badge, Checkbox, Group, Paper, Stack, Text } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import type { DrugWarning } from '../api';
import { DRUG_WARNING_KIND, DRUG_WARNING_STATUS, capitalize, labValueLine } from '../labels';
import { Sources } from './Sources';

/** Пункты инструкции, которые врач учитывает до назначения: каждый отмечает сам. */
export function DrugWarnings({ warnings, acked, onAck }: {
  warnings: DrugWarning[]; acked: Record<string, boolean>; onAck: (id: string, value: boolean) => void;
}) {
  return (
    <Stack gap="xs">
      {warnings.map((w) => {
        const kind = DRUG_WARNING_KIND[w.kind];
        const found = w.status === 'fired';
        return (
          <Paper key={w.id} withBorder p="sm" radius="md"
            style={{ borderLeft: `4px solid var(--mantine-color-${kind.color}-${found ? 6 : 3})` }}>
            <Group gap="xs" mb={4} wrap="nowrap">
              <IconAlertTriangle size={16} color={`var(--mantine-color-${kind.color}-6)`} aria-hidden />
              <Badge color={kind.color} variant={found ? 'light' : 'outline'} size="sm">{kind.label}</Badge>
              <Text size="xs" c={found ? kind.color : 'dimmed'} fw={found ? 600 : 400}>
                {DRUG_WARNING_STATUS[w.status]}{w.detail_ru ? `: ${w.detail_ru}` : ''}
              </Text>
            </Group>
            <Text size="sm">{capitalize(w.text_ru)}</Text>
            {w.check_ru && <Text size="xs" mt={2}><b>Что проверить:</b> {w.check_ru}</Text>}
            {w.labs.length > 0 && (
              <Text size="xs" mt={2}><b>Анализы в карточке:</b> {w.labs.map(labValueLine).join('; ')}</Text>
            )}
            <Text size="xs" c="dimmed" mb={4}>Инструкция, раздел «{w.section_ru}»</Text>
            <Sources ids={w.sources} />
            <Checkbox mt={6} size="xs" checked={!!acked[w.id]} onChange={(e) => onAck(w.id, e.currentTarget.checked)}
              label={w.status === 'manual' ? 'Проверено' : 'Учтено'} />
          </Paper>
        );
      })}
    </Stack>
  );
}
