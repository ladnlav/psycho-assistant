import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, tokenStore, type Me } from './api';

interface AuthContextValue {
  me: Me | null;
  loading: boolean;
  signIn: (token: string) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => tokenStore.get());
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: ['me', token],
    queryFn: () => api<Me>('/auth/me'),
    enabled: !!token,
    retry: false,
  });

  const signIn = useCallback((t: string) => {
    tokenStore.set(t);
    setToken(t);
  }, []);

  const signOut = useCallback(() => {
    tokenStore.set(null);
    setToken(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    if (token && meQuery.isError) signOut(); // токен истёк или недействителен
  }, [token, meQuery.isError, signOut]);

  const me = token && meQuery.data ? meQuery.data : null;

  return (
    <AuthContext.Provider value={{ me, loading: !!token && meQuery.isLoading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth вне AuthProvider');
  return ctx;
}

export async function login(email: string, password: string): Promise<string> {
  const res = await api<{ access_token: string }>('/auth/login', { form: { username: email, password } });
  return res.access_token;
}
