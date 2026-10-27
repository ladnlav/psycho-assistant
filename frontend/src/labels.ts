import type { AlertLevel, DrugWarning, Recommendation, ReferralLevel } from './api';

// Визуальное различение — обязательное условие кейса:
// уровни алертов, «обязательно» / «желательно» и предупреждения безопасности не должны путаться.
export const ALERT_LEVEL: Record<AlertLevel, { label: string; color: string }> = {
  critical: { label: 'Критично', color: 'red' },
  high: { label: 'Высокий', color: 'orange' },
  medium: { label: 'Внимание', color: 'yellow' },
};

export const REFERRAL_LEVEL: Record<ReferralLevel, { label: string; color: string; variant: 'filled' | 'outline' }> = {
  mandatory: { label: 'ОБЯЗАТЕЛЬНО', color: 'red', variant: 'filled' },
  desirable: { label: 'ЖЕЛАТЕЛЬНО', color: 'blue', variant: 'outline' },
};

/** Чем закончилось предложение ассистента; superseded — закрыто без решения, причина в decision_note. */
export const RECOMMENDATION_STATUS: Record<Exclude<Recommendation['status'], 'proposed'>,
  { label: string; color: string }> = {
  accepted: { label: 'принято врачом', color: 'teal' },
  rejected: { label: 'отклонено врачом', color: 'gray' },
  superseded: { label: 'закрыто', color: 'gray' },
};

export const SEVERITY_COLOR: Record<string, string> = {
  normal: 'teal', // PHQ-4: нет дистресса
  minimal: 'teal',
  mild: 'lime',
  moderate: 'yellow',
  moderately_severe: 'orange',
  severe: 'red',
};

/** Пункты инструкции при назначении: свой вид (полоса слева и треугольник), не похожий на алерты и направления. */
export const DRUG_WARNING_KIND: Record<DrugWarning['kind'], { label: string; color: string }> = {
  contraindication: { label: 'Противопоказание', color: 'red' },
  caution: { label: 'С осторожностью', color: 'orange' },
  interaction: { label: 'Взаимодействие', color: 'grape' },
};

export const DRUG_WARNING_STATUS: Record<DrugWarning['status'], string> = {
  fired: 'Найдено в карточке пациента',
  unchecked: 'Не хватает данных',
  manual: 'Проверьте у пациента',
};

/** Выраженность побочного эффекта, как её выбирает пациент. */
export const AE_SEVERITY: Record<string, string> = {
  mild: 'слабо',
  moderate: 'умеренно',
  severe: 'сильно',
};

export const SPECIALTY: Record<string, string> = {
  therapist: 'терапевт',
  neurologist: 'невролог',
  psychiatrist: 'психиатр',
  psychotherapist: 'психотерапевт',
};

/** 1 балл, 2 балла, 5 баллов */
export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

/** Пункты инструкции перенесены дословно, а в списках инструкции они со строчной буквы. */
export function capitalize(text: string): string {
  return text ? text[0].toLocaleUpperCase('ru-RU') + text.slice(1) : text;
}

const SCALE_NAME: Record<string, string> = { gad7: 'GAD-7', phq9: 'PHQ-9', phq4: 'PHQ-4' };

/** Что запустило проверку правил (Alert.trigger). */
export function triggerLabel(trigger: string | null): string {
  if (!trigger) return 'нет данных';
  if (trigger.startsWith('scale:')) return `заполнена шкала ${SCALE_NAME[trigger.slice(6)] ?? trigger.slice(6)}`;
  if (trigger.startsWith('scenario:')) return 'загружен демо-сценарий';
  return ({
    diary: 'запись в дневнике',
    intake: 'отметка приёма',
    adverse_event: 'сообщение о нежелательном явлении',
    message: 'сообщение врачу',
    schedule: 'проверка по расписанию',
    help_request: 'просьба пациента о помощи',
  } as Record<string, string>)[trigger] ?? trigger;
}

const SCALE_FIELD: Record<string, string> = {
  total: 'сумма баллов',
  n: 'число измерений',
  delta_prev: 'изменение к прошлому измерению',
  delta_baseline: 'изменение к первому измерению',
  mcid: 'порог значимого изменения',
};

/** Данные, на которых сработало правило (Alert.evidence): «PHQ-9 · пункт 9» = 1. */
export function evidenceRows(evidence: Record<string, string | number | boolean | null>): { label: string; value: string }[] {
  return Object.entries(evidence).map(([key, v]) => {
    const value = v === null ? 'нет данных' : v === true ? 'да' : v === false ? 'нет' : String(v);
    if (key === 'last_report') return { label: 'Последняя запись пациента', value: v ? formatDate(String(v)) : value };
    if (key === 'pdc_7d') return { label: 'Дней с приёмом за неделю', value: typeof v === 'number' ? `${Math.round(v * 100)} %` : value };
    if (key === 'ae.serious_7d') return { label: 'Серьёзных нежелательных явлений за 7 дней', value };
    if (key === 'ae.any_7d') return { label: 'Нежелательных явлений за 7 дней', value };
    if (key === 'text.critical') return { label: 'Текст пациента с признаками риска', value };
    if (key === 'help.requests_24h') return { label: 'Просьб о срочной помощи за сутки', value };
    const [root, field] = key.split('.');
    if (SCALE_NAME[root] && field) {
      const item = field.match(/^item(\d+)$/);
      return { label: `${SCALE_NAME[root]} · ${item ? `пункт ${item[1]}` : SCALE_FIELD[field] ?? field}`, value };
    }
    return { label: key, value };
  });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
