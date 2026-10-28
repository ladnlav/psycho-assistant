import { useState } from 'react';
import { Alert as MAlert, Anchor, Badge, Button, Card, Divider, Group, Input, Modal, NumberInput, ScrollArea,
  SegmentedControl, Select, SimpleGrid, Stack, Table, Text, Textarea, TextInput, Title, Tooltip } from '@mantine/core';
import { LineChart } from '@mantine/charts';
import { notifications } from '@mantine/notifications';
import { IconCircleCheck } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { api, type Alert, type Diagnosis, type PatientCard, type Prescription, type PrescriptionCheck,
  type Recommendation, type Referral, type ReferralIn, type ReferralLevel, type ReferralSpecialty } from '../../api';
import { AnamnesisCard, diagnosisSourceLine } from '../../components/Anamnesis';
import { AlertLevelBadge, ReferralBadge } from '../../components/Badges';
import { Chat } from '../../components/Chat';
import { DrugWarnings } from '../../components/DrugWarnings';
import { LabsCard } from '../../components/Labs';
import { Sources } from '../../components/Sources';
import { ALERT_LEVEL, DIAGNOSIS_SOURCE, RECOMMENDATION_STATUS, REFERRAL_LEVEL, SPECIALTY, capitalize, evidenceRows,
  formatDate, formatDateTime, formatFullDate, plural, triggerLabel } from '../../labels';

/** «доставлено за 15 мс» / «за 2,3 с»; если врач был не в сети — когда алерт пришёл при подключении. */
function deliveryText(a: Alert): string {
  if (!a.delivered_at) return ' · ещё не доставлено';
  const ms = new Date(a.delivered_at).getTime() - new Date(a.created_at).getTime();
  if (ms < 1000) return ` · доставлено за ${Math.max(1, Math.round(ms))} мс`;
  if (ms < 60_000) return ` · доставлено за ${(ms / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с`;
  return ` · доставлено при подключении врача ${formatDateTime(a.delivered_at)}`;
}

/** Диагнозы — справочная строка под ФИО: нейтральный серый, чтобы не спорить с алертами и направлениями.
 *  Откуда диагноз — на значке, подробнее и дата постановки — в подсказке и в разделе «Анамнез». */
function Diagnoses({ items }: { items: Diagnosis[] }) {
  if (!items.length) return <Text size="sm" c="dimmed">Диагнозы не внесены</Text>;
  return (
    <Group gap="xs">
      {items.map((d) => (
        <Tooltip key={d.id} label={`${capitalize(diagnosisSourceLine(d))} · ${d.confirmed ? 'подтверждён врачом' : 'не подтверждён врачом'}`}>
          <Badge size="lg" tt="none" color="gray" variant={d.confirmed ? 'light' : 'outline'}>
            <b>{d.icd10}</b> {d.title}{d.source ? ` · ${DIAGNOSIS_SOURCE[d.source]}` : ''}{d.confirmed ? '' : ' · не подтверждён'}
          </Badge>
        </Tooltip>
      ))}
    </Group>
  );
}

function useAck(patientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/doctor/alerts/${id}/ack`, { method: 'POST' }),
    onSuccess: (_, id) => {
      notifications.hide(id); // критичные уведомления не закрываются сами — убираем после подтверждения
      qc.invalidateQueries({ queryKey: ['card', patientId] });
      qc.invalidateQueries({ queryKey: ['patients'] });
    },
  });
}

/** Алерт целиком: когда создан и доставлен, что запустило проверку, на каких данных сработало правило, источники.
 *  Один вид для открытого алерта и для записи из истории. */
function AlertCard({ alert: a, ack }: { alert: Alert; ack: ReturnType<typeof useAck> }) {
  const evidence = evidenceRows(a.evidence);
  return (
    <MAlert color={ALERT_LEVEL[a.level].color} variant={a.level === 'critical' ? 'filled' : 'light'}
      title={<Group gap="xs"><AlertLevelBadge level={a.level} /><span>{a.title}</span></Group>}>
      <Stack gap={4}>
        <Text size="xs">
          {formatDateTime(a.created_at)} · {triggerLabel(a.trigger)}
          {deliveryText(a)}
          {a.updated_at && ` · новые данные ${formatDateTime(a.updated_at)}`}
          {a.updates > 1 && ` (${a.updates} ${plural(a.updates, 'раз', 'раза', 'раз')})`}
        </Text>
        {evidence.length > 0 && (
          <Text size="xs">Данные: {evidence.map((e) => `${e.label} — ${e.value}`).join('; ')}</Text>
        )}
        <Sources ids={a.sources} inverted={a.level === 'critical'} />
        {a.acknowledged_at ? (
          <Text size="xs" fw={600}>Принято к сведению {formatDateTime(a.acknowledged_at)}</Text>
        ) : (
          <Group><Button size="xs" variant="white" color="dark" loading={ack.isPending}
            onClick={() => ack.mutate(a.id)}>Принято к сведению</Button></Group>
        )}
      </Stack>
    </MAlert>
  );
}

function AlertsBlock({ card }: { card: PatientCard }) {
  const ack = useAck(card.id);
  const open = card.alerts.filter((a) => !a.acknowledged_at);
  if (!open.length) return null;
  return <Stack gap="xs">{open.map((a) => <AlertCard key={a.id} alert={a} ack={ack} />)}</Stack>;
}

/** Все алерты пациента, включая принятые к сведению; строка открывает алерт целиком. */
function AlertHistory({ card }: { card: PatientCard }) {
  const ack = useAck(card.id);
  const [openId, setOpenId] = useState<string | null>(null);
  const selected = card.alerts.find((a) => a.id === openId);
  return (
    <Card withBorder radius="md">
      <Title order={4} mb="sm">История алертов</Title>
      {card.alerts.length === 0 ? <Text c="dimmed" size="sm">Алертов не было</Text> : (
        <ScrollArea.Autosize mah={240}>
          <Table highlightOnHover verticalSpacing={4}>
            <Table.Tbody>
              {card.alerts.map((a) => (
                <Table.Tr key={a.id} style={{ cursor: 'pointer' }} tabIndex={0} onClick={() => setOpenId(a.id)}
                  onKeyDown={(e) => e.key === 'Enter' && setOpenId(a.id)}>
                  <Table.Td w={92}><Text size="xs" c="dimmed">{formatDateTime(a.created_at)}</Text></Table.Td>
                  <Table.Td w={1}><AlertLevelBadge level={a.level} /></Table.Td>
                  <Table.Td><Text size="sm" lineClamp={1}>{a.title}</Text></Table.Td>
                  <Table.Td w={1} style={{ whiteSpace: 'nowrap' }}>
                    <Text size="xs" c={a.acknowledged_at ? 'dimmed' : undefined} fw={a.acknowledged_at ? 400 : 600}>
                      {a.acknowledged_at ? 'принят' : 'открыт'}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea.Autosize>
      )}
      <Modal opened={!!selected} onClose={() => setOpenId(null)} title={<Text fw={600}>Алерт</Text>} size="lg" centered>
        {selected && <AlertCard alert={selected} ack={ack} />}
      </Modal>
    </Card>
  );
}

function RecommendationItem({ rec, patientId }: { rec: Recommendation; patientId: string }) {
  const qc = useQueryClient();
  const decide = useMutation({
    mutationFn: (decision: 'accepted' | 'rejected') =>
      api(`/doctor/recommendations/${rec.id}/decision`, { body: { decision } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['card', patientId] }),
  });
  // Закрытое без решения (пациент уже направлен) приглушено и без красной рамки: решения оно не ждёт.
  const closed = rec.status === 'superseded';
  return (
    <Card withBorder radius="md" style={closed ? { opacity: 0.6 } : rec.payload.level === 'mandatory'
      ? { borderColor: 'var(--mantine-color-red-6)', borderWidth: 2 } : undefined}>
      <Stack gap="xs">
        <Group justify="space-between">
          <Group gap="xs">
            {rec.payload.level && <ReferralBadge level={rec.payload.level} />}
            <Text fw={600}>{rec.title}</Text>
          </Group>
          {rec.status !== 'proposed' && (
            <Badge color={RECOMMENDATION_STATUS[rec.status].color} variant={closed ? 'outline' : 'filled'}>
              {RECOMMENDATION_STATUS[rec.status].label}
              {closed && `: ${rec.decision_note || 'уже направлен'}`}
            </Badge>
          )}
        </Group>
        {rec.payload.reason_ru && <Text size="sm">{rec.payload.reason_ru}</Text>}
        <Sources ids={rec.sources} />
        {rec.status === 'proposed' && (
          <Group>
            <Button size="xs" color="teal" loading={decide.isPending} onClick={() => decide.mutate('accepted')}>Принять</Button>
            <Button size="xs" variant="default" loading={decide.isPending} onClick={() => decide.mutate('rejected')}>
              Отклонить
            </Button>
            <Text size="xs" c="dimmed">Решение принимает врач</Text>
          </Group>
        )}
      </Stack>
    </Card>
  );
}

const AVIANDR = { drug_id: 'aviandr', drug_name: 'Авиандр' };

/** Назначение Авиандра: пункты инструкции показываем сразу, ещё до нажатия «Назначить».
 *  Если препарат уже назначен — плашка вместо формы: повторное назначение сервер всё равно отклонит. */
function Prescribe({ patientId }: { patientId: string }) {
  const { data: check } = useQuery({ queryKey: ['rx-check', patientId, AVIANDR.drug_id],
    queryFn: () => api<PrescriptionCheck>(`/doctor/patients/${patientId}/prescriptions/check`, { body: AVIANDR }) });
  if (!check) return null;
  const rx = check.already_prescribed;
  if (rx) {
    return (
      <MAlert color="teal" variant="light" icon={<IconCircleCheck />} title={`${rx.drug_name} уже назначен`}>
        <Text size="sm">
          С {formatFullDate(rx.start_date)}{rx.dose_mg ? `, ${rx.dose_mg} мг` : ''}{rx.frequency ? `, ${rx.frequency}` : ''}.
          Повторно назначить нельзя: чтобы изменить дозу или режим, отмените текущее назначение.
        </Text>
      </MAlert>
    );
  }
  // После отмены назначения форма появляется заново, и пункты инструкции врач отмечает снова.
  return <PrescribeForm patientId={patientId} check={check} />;
}

function PrescribeForm({ patientId, check }: { patientId: string; check: PrescriptionCheck }) {
  const qc = useQueryClient();
  // Доза и кратность по умолчанию — из инструкции (kb/drugs, dosing); дальше их меняет врач.
  const dosing = check.dosing;
  const [dose, setDose] = useState<number | string>(dosing?.single_mg ?? '');
  const [frequency, setFrequency] = useState(dosing?.frequency_ru ?? '');
  const [acked, setAcked] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState('');
  const warnings = check.warnings;
  const needReason = warnings.some((w) => w.requires_reason);
  const ready = warnings.every((w) => acked[w.id]) && (!needReason || note.trim() !== '');
  const create = useMutation({
    mutationFn: () => api(`/doctor/patients/${patientId}/prescriptions`, { body: {
      ...AVIANDR, dose_mg: dose === '' ? null : Number(dose), frequency: frequency || null,
      acknowledged_warnings: warnings.filter((w) => acked[w.id]).map((w) => w.id), override_note: note.trim() || null } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['card', patientId] });
      qc.invalidateQueries({ queryKey: ['rx-check', patientId] }); // проверка вернёт «уже назначен» — форма сменится плашкой
    },
    onError: () => qc.invalidateQueries({ queryKey: ['rx-check', patientId] }), // данные пациента могли измениться
  });
  return (
    <Stack gap="xs">
      {check.notice_ru && <MAlert color="gray" variant="light">{check.notice_ru}</MAlert>}
      {warnings.length > 0 && (
        <>
          <Text size="sm" fw={500}>Перед назначением отметьте каждый пункт инструкции</Text>
          <DrugWarnings warnings={warnings} acked={acked} onAck={(id, v) => setAcked((a) => ({ ...a, [id]: v }))} />
          {needReason && (
            <Textarea label="Почему назначаете, несмотря на противопоказание" required value={note}
              onChange={(e) => setNote(e.currentTarget.value)} />
          )}
        </>
      )}
      <Group align="flex-end">
        <NumberInput label="Доза, мг" value={dose} onChange={setDose} w={110} />
        <TextInput label="Режим" placeholder="по инструкции" value={frequency} onChange={(e) => setFrequency(e.currentTarget.value)} />
        <Button disabled={!ready || create.isSuccess} loading={create.isPending} onClick={() => create.mutate()}>
          Назначить Авиандр
        </Button>
      </Group>
      {dosing?.schedule_ru && <Text size="xs" c="dimmed">По инструкции (ГРЛС): {dosing.schedule_ru}</Text>}
      {create.isError && <MAlert color="red" variant="light">{(create.error as Error).message}</MAlert>}
    </Stack>
  );
}

function rxLabel(p: Prescription): string {
  return `${p.drug_name}${p.dose_mg ? `, ${p.dose_mg} мг` : ''}`;
}

/** Отмена назначения — тоже решение врача: с подтверждением, причина необязательна и пишется в аудит. */
function StopPrescription({ rx, patientId }: { rx: Prescription; patientId: string }) {
  const qc = useQueryClient();
  const [opened, setOpened] = useState(false);
  const [reason, setReason] = useState('');
  const stop = useMutation({
    mutationFn: () => api(`/doctor/prescriptions/${rx.id}/stop`, { body: { reason: reason.trim() || null } }),
    onSuccess: () => {
      setOpened(false);
      setReason('');
      qc.invalidateQueries({ queryKey: ['card', patientId] });
      qc.invalidateQueries({ queryKey: ['rx-check', patientId] }); // препарат снова можно назначить
    },
  });
  const close = () => {
    setOpened(false);
    stop.reset();
  };
  return (
    <>
      <Button size="xs" variant="light" color="red" onClick={() => setOpened(true)}>Отменить назначение</Button>
      <Modal opened={opened} onClose={close} title={<Text fw={600}>Отменить назначение?</Text>} centered>
        <Stack gap="sm">
          <Text size="sm">
            {rxLabel(rx)} — с {formatDate(rx.start_date)}. Препарат пропадёт из приложения пациента, отметки приёма
            прекратятся.
          </Text>
          <Textarea label="Причина" description="Необязательно; сохранится в журнале действий врача" autosize
            minRows={2} value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
          {stop.isError && <MAlert color="red" variant="light">{(stop.error as Error).message}</MAlert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>Не отменять</Button>
            <Button color="red" loading={stop.isPending} onClick={() => stop.mutate()}>Отменить назначение</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

const REFERRAL_SPECIALTIES: ReferralSpecialty[] = ['psychiatrist', 'psychotherapist', 'neurologist'];

/** Все направления пациента: принятые предложения правил и направления по решению врача.
 *  Уровень — тем же значком ОБЯЗАТЕЛЬНО / ЖЕЛАТЕЛЬНО, что и в предложениях. */
function Referrals({ card }: { card: PatientCard }) {
  const qc = useQueryClient();
  const [to, setTo] = useState<string | null>(null);
  const [level, setLevel] = useState<ReferralLevel>('desirable');
  const [reason, setReason] = useState('');
  const create = useMutation({
    mutationFn: (body: ReferralIn) => api<Referral>(`/doctor/patients/${card.id}/referrals`, { body }),
    onSuccess: () => {
      setTo(null);
      setReason('');
      qc.invalidateQueries({ queryKey: ['card', card.id] });
    },
  });
  const ready = to !== null && reason.trim() !== '';
  return (
    <Card withBorder radius="md">
      <Title order={4} mb="sm">Направления</Title>
      <Stack gap="sm">
        {card.referrals.length === 0 && <Text c="dimmed" size="sm">Направлений нет</Text>}
        {card.referrals.map((r) => {
          const rec = card.recommendations.find((x) => x.id === r.recommendation_id);
          return (
            <Stack key={r.id} gap={2}>
              <Group gap="xs">
                <ReferralBadge level={r.level} />
                <Text fw={600}>{capitalize(SPECIALTY[r.to_specialty] ?? r.to_specialty)}</Text>
                <Text size="xs" c="dimmed">{formatDate(r.created_at)}</Text>
              </Group>
              {r.reason && <Text size="sm">{r.reason}</Text>}
              <Text size="xs" c="dimmed">
                {r.recommendation_id ? 'По предложению правила, принято врачом' : 'Решение врача, без предложения правила'}
              </Text>
              {rec && <Sources ids={rec.sources} />}
            </Stack>
          );
        })}
        <Divider label="Направить пациента" labelPosition="left" />
        <Group align="flex-end" gap="xs">
          <Select label="Специалист" placeholder="Выберите" w={170} allowDeselect={false} value={to} onChange={setTo}
            data={REFERRAL_SPECIALTIES.map((s) => ({ value: s, label: capitalize(SPECIALTY[s]) }))} />
          <Input.Wrapper label="Уровень">
            <SegmentedControl value={level} onChange={(v) => setLevel(v as ReferralLevel)}
              color={REFERRAL_LEVEL[level].color}
              data={(['mandatory', 'desirable'] as const).map((l) => ({ value: l, label: REFERRAL_LEVEL[l].label }))} />
          </Input.Wrapper>
        </Group>
        <Textarea label="Причина" required autosize minRows={2} value={reason}
          onChange={(e) => setReason(e.currentTarget.value)} />
        <Group>
          <Button disabled={!ready} loading={create.isPending} onClick={() => ready && create.mutate(
            { to_specialty: to as ReferralSpecialty, level, reason: reason.trim() })}>Направить</Button>
          <Text size="xs" c="dimmed">Направление запишется от вашего имени</Text>
        </Group>
        {create.isError && <MAlert color="red" variant="light">{(create.error as Error).message}</MAlert>}
      </Stack>
    </Card>
  );
}

export function PatientCardPage() {
  const { patientId = '' } = useParams();
  // Записи пациента без алерта (дневник, приём, лёгкий побочный эффект) по WebSocket не приходят — опрашиваем, как чат.
  const { data: card } = useQuery({ queryKey: ['card', patientId], refetchInterval: 10_000,
    queryFn: () => api<PatientCard>(`/doctor/patients/${patientId}`) });
  if (!card) return <Text>Загрузка…</Text>;

  // Одна точка оси X на дату: результаты разных шкал за один день — в одной строке.
  const byDate = new Map<string, Record<string, number | string>>();
  const allResults = Object.values(card.scales).flat()
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  for (const r of allResults) {
    const date = formatDate(r.created_at);
    byDate.set(date, { ...(byDate.get(date) ?? { date }), [r.scale_id]: r.total });
  }
  const scaleSeries = [...byDate.values()];
  const diarySeries = card.diary.map((d) => ({ date: formatDate(d.day), Тревога: d.anxiety, Настроение: d.mood }));
  const active = card.prescriptions.filter((p) => p.active);
  const past = card.prescriptions.filter((p) => !p.active);

  return (
    <Stack>
      <Anchor component={Link} to="/doctor" size="sm">← Все пациенты</Anchor>
      <Stack gap={6}>
        <Title order={2}>{card.full_name}</Title>
        <Diagnoses items={card.diagnoses} />
      </Stack>

      <AlertsBlock card={card} />

      {card.recommendations.length > 0 && (
        <Stack gap="xs">
          <Title order={4}>Предложения ассистента</Title>
          {card.recommendations.map((r) => <RecommendationItem key={r.id} rec={r} patientId={card.id} />)}
        </Stack>
      )}

      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Шкалы</Title>
          {scaleSeries.length ? (
            <LineChart h={220} data={scaleSeries} dataKey="date" connectNulls withLegend
              series={[{ name: 'gad7', label: 'GAD-7', color: 'violet.6' }, { name: 'phq9', label: 'PHQ-9', color: 'blue.6' },
                { name: 'phq4', label: 'PHQ-4', color: 'teal.6' }]} />
          ) : <Text c="dimmed" size="sm">Нет данных</Text>}
        </Card>
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Дневник пациента</Title>
          {diarySeries.length ? (
            <LineChart h={220} data={diarySeries} dataKey="date" withLegend yAxisProps={{ domain: [0, 10] }}
              series={[{ name: 'Тревога', color: 'red.6' }, { name: 'Настроение', color: 'teal.6' }]} />
          ) : <Text c="dimmed" size="sm">Нет данных</Text>}
        </Card>
        <AnamnesisCard patientId={card.id} />
        <LabsCard patientId={card.id} />
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Терапия и приверженность</Title>
          <Stack gap="xs">
            {active.map((p) => (
              <Group key={p.id} justify="space-between" gap="xs">
                <Text>{rxLabel(p)} — с {formatDate(p.start_date)}</Text>
                <StopPrescription rx={p} patientId={card.id} />
              </Group>
            ))}
            <Text size="sm">
              Приверженность за 7 дней: {card.pdc_7d === null ? 'недостаточно данных' : `${Math.round(card.pdc_7d * 100)}%`}
            </Text>
            <Prescribe patientId={card.id} />
            {past.length > 0 && (
              <Text size="xs" c="dimmed">
                Ранее: {past.map((p) => `${rxLabel(p)} (${formatDate(p.start_date)}–${p.end_date ? formatDate(p.end_date) : '?'})`)
                  .join('; ')}
              </Text>
            )}
          </Stack>
        </Card>
        <Referrals card={card} />
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Нежелательные явления</Title>
          {card.adverse_events.length === 0 && <Text c="dimmed" size="sm">Не зарегистрированы</Text>}
          <Stack gap="xs">
            {card.adverse_events.map((ae) => (
              <Group key={ae.id} gap="xs" wrap="nowrap">
                {ae.serious && <Badge color="red">серьёзное</Badge>}
                <Text size="sm">{formatDate(ae.created_at)} — {ae.description}</Text>
              </Group>
            ))}
          </Stack>
        </Card>
        <AlertHistory card={card} />
        <Card withBorder radius="md">
          <Title order={4} mb="sm">Чат с пациентом</Title>
          <Chat path={`/doctor/patients/${card.id}/messages`} />
        </Card>
      </SimpleGrid>
    </Stack>
  );
}
