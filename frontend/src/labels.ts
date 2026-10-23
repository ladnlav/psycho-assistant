import type { AlertLevel, DrugWarning, ReferralLevel } from './api';

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

export const SEVERITY_COLOR: Record<string, string> = {
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

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
