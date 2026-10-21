import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import '@mantine/charts/styles.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Center, createTheme, Loader, MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router';
import { AuthProvider, useAuth } from './auth';
import { Layout } from './components/Layout';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { DoctorHome } from './pages/doctor/DoctorHome';
import { PatientCardPage } from './pages/doctor/PatientCardPage';
import { PatientHome } from './pages/patient/PatientHome';
import { ScalePage } from './pages/patient/ScalePage';

const theme = createTheme({ primaryColor: 'violet', defaultRadius: 'md', respectReducedMotion: true });
const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: true } } });

function AppRoutes() {
  const { me, loading } = useAuth();
  if (loading) return <Center h="100vh"><Loader /></Center>;
  return (
    <Routes>
      <Route element={<Layout />}>
        {!me && (
          <>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </>
        )}
        {me?.role === 'doctor' && (
          <>
            <Route path="/doctor" element={<DoctorHome />} />
            <Route path="/doctor/patients/:patientId" element={<PatientCardPage />} />
            <Route path="*" element={<Navigate to="/doctor" replace />} />
          </>
        )}
        {me?.role === 'patient' && (
          <>
            <Route path="/patient" element={<PatientHome />} />
            <Route path="/patient/scales/:scaleId" element={<ScalePage />} />
            <Route path="*" element={<Navigate to="/patient" replace />} />
          </>
        )}
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={theme}>
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
);
