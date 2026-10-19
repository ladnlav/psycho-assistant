import { useState } from 'react';
import { Alert, Anchor, Button, Checkbox, Paper, PasswordInput, SegmentedControl, Select, Stack, Text, TextInput,
  Title } from '@mantine/core';
import { Link } from 'react-router';
import { api } from '../api';
import { useAuth } from '../auth';

export function RegisterPage() {
  const { signIn } = useAuth();
  const [role, setRole] = useState<'patient' | 'doctor'>('patient');
  const [form, setForm] = useState({ full_name: '', email: '', password: '', invite_code: '', specialty: 'therapist' });
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { full_name, email, password, invite_code, specialty } = form;
      const res = role === 'doctor'
        ? await api<{ access_token: string }>('/auth/register/doctor', { body: { full_name, email, password, specialty } })
        : await api<{ access_token: string }>('/auth/register/patient',
            { body: { full_name, email, password, invite_code, consent_pd: consent } });
      signIn(res.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка регистрации');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Paper maw={460} mx="auto" mt="xl" p="lg" withBorder radius="md">
      <form onSubmit={submit}>
        <Stack>
          <Title order={2}>Регистрация</Title>
          <SegmentedControl value={role} onChange={(v) => setRole(v as 'patient' | 'doctor')}
            data={[{ value: 'patient', label: 'Я пациент' }, { value: 'doctor', label: 'Я врач' }]} />
          <TextInput label="ФИО" required value={form.full_name} onChange={(e) => set('full_name')(e.currentTarget.value)} />
          <TextInput label="Email" type="email" required value={form.email}
            onChange={(e) => set('email')(e.currentTarget.value)} />
          <PasswordInput label="Пароль (от 8 символов)" required value={form.password}
            onChange={(e) => set('password')(e.currentTarget.value)} />
          {role === 'patient' ? (
            <>
              <TextInput label="Код от врача" required value={form.invite_code}
                onChange={(e) => set('invite_code')(e.currentTarget.value.toUpperCase())} />
              {/* TODO: юридически выверенный текст согласия (152-ФЗ) */}
              <Checkbox checked={consent} onChange={(e) => setConsent(e.currentTarget.checked)}
                label="Даю согласие на обработку моих персональных данных, включая сведения о состоянии здоровья,
                  лечащим врачом в целях медицинского наблюдения" />
            </>
          ) : (
            <Select label="Специальность" value={form.specialty} onChange={(v) => v && set('specialty')(v)}
              data={[{ value: 'therapist', label: 'Терапевт' }, { value: 'neurologist', label: 'Невролог' },
                { value: 'psychiatrist', label: 'Психиатр' }]} />
          )}
          {error && <Alert color="red">{error}</Alert>}
          <Button type="submit" loading={loading} disabled={role === 'patient' && !consent}>Зарегистрироваться</Button>
          <Text size="sm">Уже есть аккаунт? <Anchor component={Link} to="/login">Войти</Anchor></Text>
        </Stack>
      </form>
    </Paper>
  );
}
