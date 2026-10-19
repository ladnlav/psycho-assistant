import { useState } from 'react';
import { Alert, Anchor, Button, Paper, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core';
import { Link } from 'react-router';
import { login, useAuth } from '../auth';

export function LoginPage() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      signIn(await login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка входа');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Paper maw={420} mx="auto" mt="xl" p="lg" withBorder radius="md">
      <form onSubmit={submit}>
        <Stack>
          <Title order={2}>Вход</Title>
          <TextInput label="Email" type="email" required value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
          <PasswordInput label="Пароль" required value={password} onChange={(e) => setPassword(e.currentTarget.value)} />
          {error && <Alert color="red">{error}</Alert>}
          <Button type="submit" loading={loading}>Войти</Button>
          <Text size="sm">
            Нет аккаунта? <Anchor component={Link} to="/register">Регистрация</Anchor>
          </Text>
        </Stack>
      </form>
    </Paper>
  );
}
