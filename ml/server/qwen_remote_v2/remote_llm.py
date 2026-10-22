#!/usr/bin/env python3
"""Start/stop Ollama in a JupyterHub GPU session without SSH."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlparse

import requests
import websocket

BASE = os.getenv('JUPYTERHUB_URL', 'https://jupyterhub.example.com').rstrip('/')
USER = os.getenv('JUPYTERHUB_USER', 'your-login')
TOKEN_FILE = Path(os.getenv('JUPYTERHUB_TOKEN_FILE', str(Path.home() / '.config/qwen/token'))).expanduser()


def api_request(session, method, path, **kwargs):
    response = session.request(method, BASE + path, timeout=30, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f'{method} {path}: HTTP {response.status_code}: {response.text[:400]}')
    return response


def server_state(session):
    u = api_request(session, 'GET', f'/hub/api/users/{USER}').json()
    return u.get('servers', {}).get('', {})


def await_server(session, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = server_state(session)
        if state.get('ready') and not state.get('pending'):
            return
        if state.get('pending') not in (None, 'spawn', 'stop'):
            raise RuntimeError(f'Unexpected server state: {state}')
        time.sleep(3)
    raise TimeoutError('JupyterHub GPU server did not become ready')


def start_server(session):
    state = server_state(session)
    if state.get('ready') and not state.get('pending'):
        print('JupyterHub GPU session already running', flush=True)
        return
    if state.get('pending') == 'stop':
        print('Waiting for previous session to stop...', flush=True)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and server_state(session).get('pending') == 'stop':
            time.sleep(3)
        state = server_state(session)
    if state.get('pending') == 'spawn':
        print('GPU session already starting...', flush=True)
    elif not state.get('ready'):
        print('Starting GPU session...', flush=True)
        r = session.post(BASE + f'/hub/api/users/{USER}/server', json={'profile': 'gpu'}, timeout=60)
        if r.status_code not in (201, 202):
            raise RuntimeError(f'Session start HTTP {r.status_code}: {r.text[:400]}')
    await_server(session)
    print('GPU session ready', flush=True)


def remote_command(session, token, command, timeout=300):
    r = api_request(session, 'POST', f'/user/{USER}/api/terminals', json={})
    name = str(r.json()['name'])
    ws = None
    nonce = secrets.token_hex(12)
    marker = '__QWEN_REMOTE_EXIT_' + nonce + '__'
    # Encode command into python string to avoid shell quoting of command payload;
    # only fixed local shell commands are used here.
    remote = f'{command}; __rc=$?; printf "\\n{marker}%s\\n" "$__rc"\n'
    ws_url = BASE.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1) + f'/user/{USER}/terminals/websocket/{name}'
    try:
        ws = websocket.create_connection(
            ws_url,
            header={'Authorization': 'Bearer ' + token},
            origin=BASE,
            timeout=5,
        )
        ws.send(json.dumps(['stdin', remote + '\r']))
        deadline = time.monotonic() + timeout
        collected = ''
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            data = json.loads(raw)
            if not isinstance(data, list) or len(data) < 2 or data[0] != 'stdout':
                continue
            chunk = data[1]
            collected += chunk
            # ANSI escape sequences and CRs can split or interrupt marker.
            import re
            normalized = re.sub(r'\x1b\[[0-9;?]*[ -/]*[@-~]', '', collected).replace('\r', '')
            match = re.search(re.escape(marker) + r'(\d+)\s*(?:\n|$)', normalized)
            if match:
                preceding = normalized[:match.start()]
                # Display output, including command echo (useful for debugging).
                print(preceding, end='' if preceding.endswith('\n') else '\n', flush=True)
                return int(match.group(1))
        raise TimeoutError('Remote command timed out')
    finally:
        if ws is not None:
            ws.close()
        try:
            session.delete(BASE + f'/user/{USER}/api/terminals/{name}', timeout=10)
        except requests.RequestException:
            pass


def check_endpoint(session, suffix):
    r = session.get(BASE + f'/user/{USER}/proxy/11435{suffix}', timeout=15, allow_redirects=False)
    if r.status_code != 200:
        raise RuntimeError(f'{suffix}: HTTP {r.status_code} ({r.headers.get("Location", "")})')
    return r.json()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['start', 'stop'])
    p.add_argument('--session', action='store_true', help='Also stop JupyterHub session (stop only)')
    a = p.parse_args()
    if a.action == 'start' and a.session:
        p.error('--session is supported only for stop')
    token = TOKEN_FILE.read_text(encoding='utf-8').strip()
    if not token:
        raise RuntimeError('JupyterHub token is empty')
    session = requests.Session()
    session.headers.update({'Authorization': f'Bearer {token}'})
    if a.action == 'start':
        start_server(session)
        # Idempotent when both endpoints work, avoids restarting a working model.
        try:
            check_endpoint(session, '/api/tags')
            check_endpoint(session, '/v1/models')
            print('Ollama and OpenAI-compatible proxy already available', flush=True)
            return
        except (RuntimeError, requests.RequestException, ValueError):
            pass
        print('Starting Ollama and proxy on GPU node...', flush=True)
        rc = remote_command(session, token, 'bash "$HOME/start_qwen.sh"', timeout=300)
        if rc:
            raise RuntimeError(f'start_qwen.sh failed with exit code {rc}')
        check_endpoint(session, '/api/tags')
        check_endpoint(session, '/v1/models')
        print('SUCCESS: Ollama and OpenAI-compatible API are available', flush=True)
    else:
        state = server_state(session)
        if state.get('ready'):
            print('Stopping Ollama and proxy...', flush=True)
            rc = remote_command(session, token, 'bash "$HOME/stop_qwen.sh"', timeout=90)
            if rc:
                raise RuntimeError(f'stop_qwen.sh failed with exit code {rc}')
        else:
            print('JupyterHub session is not running', flush=True)
        if a.session:
            print('Stopping GPU session...', flush=True)
            r = session.delete(BASE + f'/hub/api/users/{USER}/server', timeout=30)
            if r.status_code not in (202, 204):
                raise RuntimeError(f'Session stop HTTP {r.status_code}: {r.text[:400]}')
            print('GPU session stop requested', flush=True)
        print('Stop completed', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, requests.RequestException, websocket.WebSocketException, TimeoutError, OSError, ValueError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
