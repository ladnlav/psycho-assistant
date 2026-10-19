import { Anchor, Group, Text, Tooltip } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { api, type Source } from '../api';

/** Источники рекомендации — каждая подсказка системы ссылается на КР, инструкцию или шкалу. */
export function Sources({ ids, inverted = false }: { ids: string[]; inverted?: boolean }) {
  const color = inverted ? 'white' : undefined; // на залитом красном фоне критического алерта
  const { data } = useQuery({ queryKey: ['sources'], queryFn: () => api<Record<string, Source>>('/kb/sources'),
    staleTime: Infinity });
  if (!ids.length) return null;
  return (
    <Group gap={6} wrap="wrap">
      <Text size="xs" c={color ?? 'dimmed'}>Источники:</Text>
      {ids.map((id) => {
        const s = data?.[id];
        const label = s ? s.title.slice(0, 60) + (s.title.length > 60 ? '…' : '') : id;
        return (
          <Tooltip key={id} label={s?.title ?? id} multiline maw={420}>
            {s?.url ? (
              <Anchor href={s.url} target="_blank" size="xs" c={color} underline="always">{label}</Anchor>
            ) : (
              <Text size="xs" c={color}>{label}</Text>
            )}
          </Tooltip>
        );
      })}
    </Group>
  );
}
