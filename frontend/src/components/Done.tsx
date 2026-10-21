import { useEffect, useState, type ReactNode } from 'react';
import { Group, ThemeIcon, Transition } from '@mantine/core';
import { IconCheck } from '@tabler/icons-react';

/** Отметка «готово». animate — действие только что выполнено: галочка появляется с короткой анимацией. */
export function Done({ animate = false, children }: { animate?: boolean; children: ReactNode }) {
  const [shown, setShown] = useState(!animate);
  useEffect(() => {
    if (!animate) return;
    const frame = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(frame);
  }, [animate]);
  return (
    <Transition mounted={shown} transition="pop" duration={250} timingFunction="ease-out">
      {(styles) => (
        <Group gap="xs" wrap="nowrap" align="flex-start" style={styles}>
          <ThemeIcon color="teal" radius="xl" size="md" aria-hidden><IconCheck size={16} stroke={3} /></ThemeIcon>
          <div>{children}</div>
        </Group>
      )}
    </Transition>
  );
}
