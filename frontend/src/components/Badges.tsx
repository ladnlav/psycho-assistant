import { Badge, Tooltip } from '@mantine/core';
import type { AlertLevel, ReferralLevel, ScaleResult } from '../api';
import { ALERT_LEVEL, REFERRAL_LEVEL, SEVERITY_COLOR } from '../labels';

export function AlertLevelBadge({ level }: { level: AlertLevel }) {
  const { label, color } = ALERT_LEVEL[level];
  return <Badge color={color} variant={level === 'critical' ? 'filled' : 'light'}>{label}</Badge>;
}

export function ReferralBadge({ level }: { level: ReferralLevel }) {
  const { label, color, variant } = REFERRAL_LEVEL[level];
  return <Badge color={color} variant={variant} size="lg">{label}</Badge>;
}

export function ScoreBadge({ result, name }: { result?: ScaleResult; name: string }) {
  if (!result) return <Badge color="gray" variant="light">{name}: —</Badge>;
  return (
    <Tooltip label={new Date(result.created_at).toLocaleDateString('ru-RU')}>
      <Badge color={SEVERITY_COLOR[result.severity] ?? 'gray'} variant="light">
        {name}: {result.total}
      </Badge>
    </Tooltip>
  );
}
