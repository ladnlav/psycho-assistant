import { useEffect } from 'react';
import { notifications } from '@mantine/notifications';
import { useQueryClient } from '@tanstack/react-query';
import { tokenStore, wsUrl, type Alert } from './api';
import { ALERT_LEVEL } from './labels';

/** Алерты врачу в реальном времени (WebSocket /ws/doctor) с переподключением. */
export function useDoctorAlerts(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      const token = tokenStore.get();
      if (!token) return;
      ws = new WebSocket(wsUrl(`/ws/doctor?token=${encodeURIComponent(token)}`));
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as { type: string; alert: Alert };
        if (msg.type !== 'alert') return;
        const { label, color } = ALERT_LEVEL[msg.alert.level];
        // В открытый алерт пришли новые данные — показываем уведомление заново, даже если врач его закрыл.
        if (msg.alert.updated_at) notifications.hide(msg.alert.id);
        notifications.show({
          id: msg.alert.id, // повторно присланный алерт не добавит второе уведомление
          title: `${label}: ${msg.alert.title}`,
          message: msg.alert.updated_at ? 'Новые данные — откройте карточку пациента' : 'Откройте карточку пациента',
          color,
          autoClose: msg.alert.level === 'critical' ? false : 10000,
        });
        qc.invalidateQueries({ queryKey: ['patients'] });
        qc.invalidateQueries({ queryKey: ['card', msg.alert.patient_id] });
      };
      ws.onclose = () => {
        if (!closed) retry = setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, [enabled, qc]);
}
