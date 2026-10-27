// Типы повторяют backend/app/schemas.py.

export type Role = 'doctor' | 'patient';
export type AlertLevel = 'critical' | 'high' | 'medium';
export type ReferralLevel = 'mandatory' | 'desirable';

export interface Me {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  specialty: string | null;
  doctor_name: string | null;
}

export interface ScaleOption { value: number; label_en: string; label_ru: string | null }
export interface ScaleItem { id: string; text_en: string; text_ru: string | null }
export interface Scale {
  id: string;
  name: string;
  title_ru: string;
  rater: 'patient' | 'clinician';
  status: 'draft' | 'validated';
  instruction_en: string;
  instruction_ru: string | null;
  options: ScaleOption[];
  items: ScaleItem[];
  /** Подшкалы (PHQ-4: тревога и депрессия): сумма пунктов ≥ positive_min — положительный скрининг. */
  subscales: { id: string; name: string; title_ru: string; items: string[]; positive_min: number; label_ru: string }[];
  severity: { min: number; max: number; level: string; label_ru: string }[];
  mcid: number | null;
  sources: string[];
}

export interface ScaleResult { id: string; scale_id: string; total: number; severity: string; created_at: string }
export interface ScaleSchedule { scale_id: string; last_taken_at: string | null; next_due: string | null; due: boolean }
export interface SafetyScreen { message_ru: string; contacts: { title_ru: string; phone: string }[] }
export interface Reminder { rule_id: string; text_ru: string } // из правил с remind_patient (kb/rules)
export interface ScaleSubmitResult { result: ScaleResult; severity_label_ru: string; safety: SafetyScreen | null }

export interface DiaryEntry {
  id: string; day: string; anxiety: number; mood: number; sleep_quality: number | null; note: string | null;
}
export interface AdverseEvent { id: string; description: string; severity: string; serious: boolean; created_at: string }
/** Ответ на отправку пациентом: экран помощи, если в тексте есть признаки риска (kb/rules/free_text_risk). */
export interface AdverseEventSent extends AdverseEvent { safety: SafetyScreen | null }
export interface Prescription {
  id: string; drug_id: string | null; drug_name: string; dose_mg: number | null; frequency: string | null;
  start_date: string; end_date: string | null; active: boolean; // end_date — окончание или отмена врачом
}
export interface Intake { id: string; prescription_id: string; day: string; status: 'taken' | 'missed' }
/** Последнее значение анализа из карточки рядом с пунктом инструкции; value null — результата нет. */
export interface LabValue { analyte: string; title_ru: string; unit: string | null; value: number | null; taken_on: string | null }
export interface DrugWarning {
  id: string; kind: 'contraindication' | 'caution' | 'interaction'; status: 'fired' | 'manual' | 'unchecked';
  text_ru: string; section_ru: string; detail_ru: string | null; check_ru: string | null; requires_reason: boolean;
  labs: LabValue[]; // анализы из карточки, которые относятся к пункту (lab() и labs в kb/drugs)
  sources: string[];
}
/** Режим дозирования из инструкции (kb/drugs, dosing) — значения по умолчанию в форме назначения. */
export interface Dosing { single_mg: number; times_per_day: number; frequency_ru: string; schedule_ru: string | null }
export interface PrescriptionCheck {
  checked: boolean; notice_ru: string | null; warnings: DrugWarning[]; dosing: Dosing | null;
}

export interface Alert {
  id: string; patient_id: string; rule_id: string; level: AlertLevel; title: string; sources: string[];
  created_at: string; delivered_at: string | null; acknowledged_at: string | null;
  updated_at: string | null; // новые данные в открытом алерте
  updates: number; // сколько раз в открытый алерт приходили новые данные
  trigger: string | null; // что запустило проверку правил: scale:gad7, diary, schedule…
  evidence: Record<string, string | number | boolean | null>; // на каких данных сработало правило
}
export interface Recommendation {
  id: string;
  kind: string;
  title: string;
  payload: { to?: string; level?: ReferralLevel; reason_ru?: string };
  sources: string[];
  rule_id: string | null;
  status: 'proposed' | 'accepted' | 'rejected' | 'superseded'; // superseded — закрыто: уже направлен
  created_at: string;
  decided_at: string | null;
  decision_note: string | null; // у superseded — почему закрыто
}
export type ReferralSpecialty = 'psychiatrist' | 'psychotherapist' | 'neurologist';
/** Направление по решению врача, без предложения правила (POST /doctor/patients/{id}/referrals). */
export interface ReferralIn { to_specialty: ReferralSpecialty; level: ReferralLevel; reason: string }
export interface Referral {
  id: string; to_specialty: string; level: ReferralLevel; reason: string; created_at: string;
  recommendation_id: string | null; // null — врач направил сам, без предложения правила
}
export interface PatientSummary {
  id: string; full_name: string; open_alerts: number; top_alert_level: AlertLevel | null;
  last_scores: Record<string, ScaleResult>;
  diagnoses: Diagnosis[];
}
/** Откуда диагноз: выписка, осмотр, со слов пациента, МИС или другое (source_note — своими словами). */
export type DiagnosisSource = 'discharge' | 'exam' | 'patient' | 'mis' | 'other';
export type LabSource = 'lab' | 'discharge' | 'mis' | 'patient' | 'other';
export interface Diagnosis {
  id: string; icd10: string; title: string; confirmed: boolean;
  source: DiagnosisSource | null; // null — не указано (внесён до 27.10)
  source_note: string | null;
  diagnosed_on: string | null; // дата постановки
}
export interface DiagnosisSourceIn { source: DiagnosisSource; source_note: string | null; diagnosed_on: string | null }
export interface DiagnosisIn extends DiagnosisSourceIn { icd10: string; title: string }
export interface AnamnesisIn { complaints: string | null; history: string | null; notes: string | null }
export interface Anamnesis extends AnamnesisIn {
  updated_at: string | null; // null — анамнез ещё не заполняли
  updated_by_name: string | null;
}
export interface LabTest { id: string; title_ru: string; name_ru: string | null; unit: string | null } // kb/labs.yaml
export interface LabResultIn {
  analyte: string; value: number; taken_on: string; source: LabSource; source_note: string | null;
}
export interface LabResult {
  id: string; analyte: string; value: number; unit: string | null; taken_on: string; source: LabSource;
  source_note: string | null; created_at: string;
}
/** Раздел «Анамнез» у врача и «Моя история» у пациента. */
export interface PatientHistory {
  anamnesis: Anamnesis;
  diagnoses: Diagnosis[];
  labs: LabResult[]; // все результаты, сначала последние по дате сдачи
  lab_tests: LabTest[]; // показатели из kb/labs.yaml в порядке файла
}
export interface PatientCard {
  id: string;
  full_name: string;
  birth_date: string | null;
  diagnoses: Diagnosis[];
  scales: Record<string, ScaleResult[]>;
  diary: DiaryEntry[];
  prescriptions: Prescription[];
  intakes: Intake[];
  pdc_7d: number | null;
  adverse_events: AdverseEvent[];
  alerts: Alert[];
  recommendations: Recommendation[];
  referrals: Referral[]; // принятые предложения правил и направления по решению врача
}
export interface Invite { code: string; patient_label: string | null; created_at: string; used_at: string | null }
export interface Message {
  id: string; sender_id: string; body: string; created_at: string;
  kind: 'chat' | 'help'; // help — просьба о срочной помощи с причиной (кнопка «Нужна срочная помощь»)
}
export interface MessageSent extends Message { safety?: SafetyScreen | null } // safety — только у пациента
export interface Source { id: string; type: string; title: string; url: string | null; verified: boolean; note: string | null }

const TOKEN_KEY = 'compass_token';

export const tokenStore = {
  get(): string | null {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set(token: string | null): void {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch { /* приватный режим: токен живёт до перезагрузки */ }
  },
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface RequestOptions { method?: string; body?: unknown; form?: Record<string, string> }

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) {
    body = new URLSearchParams(opts.form);
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
  } else if (opts.body !== undefined) {
    body = JSON.stringify(opts.body);
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(`/api${path}`, { method: opts.method ?? (body ? 'POST' : 'GET'), headers, body });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch { /* тело не JSON */ }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

export function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}${path}`;
}
