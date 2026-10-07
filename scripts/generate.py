#!/usr/bin/env python3
"""Commit Farm. Python 3.10+, somente biblioteca padrão; nenhum token no SVG."""
import argparse
from datetime import date, datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import random
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ['NONE', 'FIRST_QUARTILE', 'SECOND_QUARTILE', 'THIRD_QUARTILE', 'FOURTH_QUARTILE']
MONTHS = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ']
QUERY = '''query Farm($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount contributionLevel } }
      }
    }
  }
}'''


def bounds(today):
    """365 dias, inclusive hoje; inclui fevereiro bissexto sem ajustar datas."""
    return today - timedelta(days=364), today


def fetch_calendar(username, token, today):
    if not token:
        raise ValueError('Token ausente. No Actions, use GH_TOKEN; localmente, exporte GH_TOKEN antes de executar.')
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})', username):
        raise ValueError('Informe um username válido em config.json ou FARM_USERNAME.')
    start, end = bounds(today)
    body = json.dumps({'query': QUERY, 'variables': {
        'login': username, 'from': f'{start}T00:00:00Z', 'to': f'{end}T23:59:59Z'
    }}).encode()
    request = Request('https://api.github.com/graphql', data=body, headers={
        'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
        'User-Agent': 'commit-farm-mvp', 'Accept': 'application/vnd.github+json'
    })
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise ValueError(f'GitHub retornou HTTP {exc.code}. Confira validade/permissões do token e o limite da API.') from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise ValueError('Não foi possível ler o GitHub. Tente novamente; o SVG anterior será preservado.') from None
    if result.get('errors'):
        # Não registrar payloads remotos ou tokens em logs públicos.
        raise ValueError('A consulta GraphQL falhou. Confira usuário, permissões e limite de consultas; tente GH_READ_TOKEN com read:user.')
    user = result.get('data', {}).get('user')
    if not user:
        raise ValueError('Usuário não encontrado no GitHub. Confira FARM_USERNAME/config.json.')
    try:
        return user['contributionsCollection']['contributionCalendar']
    except (KeyError, TypeError):
        raise ValueError('Resposta incompleta do GitHub; o SVG anterior será preservado.') from None


def normalize(calendar, today):
    """Falhar antes da escrita se dias estiverem ausentes, repetidos ou inválidos."""
    start, end = bounds(today)
    by_date = {}
    for week in calendar['weeks']:
        for raw in week['contributionDays']:
            day = date.fromisoformat(raw['date'])
            if not start <= day <= end:
                continue
            count = raw['contributionCount']
            level = raw['contributionLevel']
            weekday = (day.weekday() + 1) % 7
            if day in by_date or type(count) is not int or count < 0:
                raise ValueError('Calendário inválido: data repetida ou contagem inválida.')
            if level not in LEVELS or raw['weekday'] != weekday:
                raise ValueError('Calendário inválido: nível ou dia da semana inesperado.')
            if (count == 0) != (level == 'NONE'):
                raise ValueError('Calendário inválido: atividade incompatível com seu nível.')
            by_date[day] = {'date': day.isoformat(), 'count': count, 'level': LEVELS.index(level), 'weekday': weekday}
    if len(by_date) != 365:
        raise ValueError(f'Calendário incompleto: recebidos {len(by_date)} de 365 dias. Tente novamente.')
    return [by_date[day] for day in sorted(by_date)]


def demo_calendar(today):
    rng = random.Random(2026)
    start, end = bounds(today)
    days = []
    for i in range(365):
        d = start + timedelta(days=i)
        level = rng.choices(range(5), [25, 18, 23, 20, 14])[0]
        if d.weekday() in (5, 6) and rng.random() < .55:
            level = 0
        count = [0, 1, 4, 8, 14][level] + (rng.randrange(3) if level else 0)
        days.append({'date': d.isoformat(), 'weekday': (d.weekday()+1) % 7,
                     'contributionCount': count, 'contributionLevel': LEVELS[level]})
    return {'weeks': [{'contributionDays': days}], 'totalContributions': sum(d['contributionCount'] for d in days)}


class Drawing:
    def __init__(self):
        self.parts = []

    def rect(self, x, y, w, h, color):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>')

    def text(self, x, y, value, size=12, color='#485744', extra=''):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" {extra}>{escape(str(value))}</text>')

    def group(self, x, y, scale=1):
        self.parts.append(f'<g transform="translate({x} {y}) scale({scale})">')

    def end(self):
        self.parts.append('</g>')

    def sprite(self, x, y, rows, palette, scale=3):
        self.group(x, y, scale)
        for row, line in enumerate(rows):
            for col, char in enumerate(line):
                if char in palette:
                    self.rect(col, row, 1, 1, palette[char])
        self.end()


def tree(s, x, y, scale=3):
    s.sprite(x, y, [
        '....aaaa....', '..aabbbbaa..', '.abbbccbbba.', 'abbccccbbbba',
        'abbccccbbbba', 'abbbbccbbbba', '.abbbbbbbba.', '..aaabbaa...',
        '....ttt.....', '....tlt.....', '....tlt.....', '...ttttt....'],
        {'a':'#3f6847','b':'#5e8c4e','c':'#85a955','t':'#79573e','l':'#ad8050'}, scale)


def chicken(s, x, y, scale=3):
    s.sprite(x, y, ['.....rr.', '....www.', 'w..wwkwo', 'wwwwwww.', '.wwcww..', '..wwww..', '..o.o...'],
             {'r':'#c35c3d','w':'#fff7da','k':'#39402e','o':'#d79d43','c':'#dfd8b7'}, scale)


def house(s, x, y):
    s.group(x, y, 2)
    s.rect(1, 45, 67, 4, '#9bae70')
    s.rect(9, 15, 52, 32, '#946643')
    s.rect(11, 15, 48, 30, '#e2b66e')
    for yy in (23, 31, 39):
        s.rect(11, yy, 48, 1, '#c9995b')
    s.rect(47, 0, 7, 12, '#876858')
    for yy, xx, ww in [(1,24,23),(4,18,35),(7,12,47),(10,6,59),(13,2,67)]:
        s.rect(xx, yy, ww, 4, '#874b3d')
        s.rect(xx+1, yy, ww-2, 2, '#bc6b48')
    s.rect(2, 17, 67, 2, '#754a36')
    for xx in (16, 44):
        s.rect(xx, 24, 11, 12, '#79513c')
        s.rect(xx+1, 25, 9, 9, '#97bdad')
        s.rect(xx+5, 25, 1, 9, '#e5c690')
        s.rect(xx+1, 29, 9, 1, '#e5c690')
        s.rect(xx-1, 36, 13, 2, '#80563c')
    s.rect(31, 27, 10, 20, '#77523c')
    s.rect(33, 29, 6, 17, '#ad7950')
    s.rect(37, 37, 1, 2, '#f1ce77')
    s.rect(27, 47, 18, 3, '#ddc697')
    s.end()


def fence(s, x, y, width):
    s.rect(x, y+4, width, 3, '#b88b54')
    s.rect(x, y+10, width, 3, '#bb925d')
    for xx in range(x, x+width, 22):
        s.rect(xx, y+1, 4, 17, '#8d6947')
        s.rect(xx, y, 3, 15, '#d7b77d')


def plot(s, x, y, level):
    s.group(x, y)
    s.rect(0, 0, 18, 18, '#805c40')
    s.rect(1, 1, 16, 15, '#a4774f')
    for yy in (4, 9, 14):
        s.rect(2, yy, 14, 1, '#8d633f')
    if level == 0:
        s.rect(4, 3, 2, 1, '#c29a67')
        s.rect(13, 11, 2, 1, '#c29a67')
    else:
        for xx, yy in [(5, 6), (12, 12)]:
            s.rect(xx, yy, 2, 4, '#526d34')
            s.rect(xx-2, yy-1, 3, 2, '#91b651')
            s.rect(xx+1, yy-2, 3, 2, '#aacb5c')
            if level >= 2:
                s.rect(xx-3, yy+1, 3, 2, '#73973f')
                s.rect(xx+1, yy, 4, 2, '#87b24c')
            if level >= 3:
                s.rect(xx-1, yy+3, 4, 3, '#e39b43')
                s.rect(xx, yy+6, 2, 1, '#d67932')
            if level >= 4:
                s.rect(xx-1, yy+2, 4, 4, '#f7bc56')
                s.rect(xx-1, yy+3, 1, 2, '#ffe192')
                s.rect(xx+1, yy-3, 2, 2, '#c2d97a')
    s.end()


def render(days, username, title, today, demo=False):
    s = Drawing()
    total = sum(d['count'] for d in days)
    active = sum(d['count'] > 0 for d in days)
    first = date.fromisoformat(days[0]['date'])
    sunday = first - timedelta(days=(first.weekday()+1) % 7)
    weeks = ((today-sunday).days // 7) + 1
    x0, y0, step = 108, 254, 20
    s.parts.append('<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="540" viewBox="0 0 1280 540" role="img" aria-labelledby="title desc">')
    s.parts.append(f'<title id="title">{escape(title)} — @{escape(username)}</title>')
    s.parts.append(f'<desc id="desc">Fazendinha com 365 dias: {total} contribuições e {active} dias ativos. Colunas são semanas; linhas de domingo a sábado. '+('Dados fictícios de demonstração.' if demo else 'Dados do calendário de contribuições do GitHub.')+'</desc>')
    s.parts.append('<style>text{font-family:ui-monospace,monospace} .day:hover{filter:brightness(1.2)}</style>')
    s.rect(0, 0, 1280, 540, '#f5f1e5')
    s.text(36, 30, 'COMMIT FARM', 11, '#74825c', 'letter-spacing="3"')
    s.text(36, 60, title, 25, '#354c38', 'font-weight="bold"')
    status = 'DEMO · DADOS FICTÍCIOS' if demo else f'@{username} · últimos 365 dias'
    s.text(36, 82, status, 11, '#73816a')
    s.text(944, 43, f'{total:,}'.replace(',', '.'), 26, '#426346', 'font-weight="bold"')
    s.text(944, 63, 'contribuições', 11, '#73816a')
    s.text(1120, 43, active, 26, '#426346', 'font-weight="bold"')
    s.text(1120, 63, 'dias ativos', 11, '#73816a')
    s.parts.append('<g shape-rendering="crispEdges">')
    s.rect(24, 102, 1232, 380, '#d7e3b4')
    s.rect(24, 472, 1232, 10, '#b5c687')
    s.rect(24, 102, 1232, 8, '#e4eccd')
    # Grama esparsa, com posições fixas para evitar mudanças sem novos dados.
    rng = random.Random(8)
    for _ in range(270):
        x, y = rng.randrange(32, 1244), rng.randrange(114, 469)
        s.rect(x, y, 3, 2, rng.choice(['#c4d599','#ccdaa5','#bccc8c']))
    s.rect(305, 175, 484, 21, '#e5d2a1')
    s.rect(785, 177, 24, 56, '#e5d2a1')
    s.rect(323, 194, 12, 33, '#e5d2a1')
    house(s, 186, 113)
    tree(s, 84, 126, 5)
    tree(s, 352, 115, 4)
    tree(s, 414, 137, 3)
    tree(s, 1200, 150, 3)
    # Lago em degraus e pequenos reflexos.
    s.rect(1060, 131, 109, 65, '#b2c48b')
    s.rect(1048, 143, 133, 41, '#b2c48b')
    s.rect(1066, 137, 97, 53, '#75aea6')
    s.rect(1054, 149, 121, 29, '#75aea6')
    s.rect(1072, 140, 81, 4, '#a4cebf')
    s.rect(1058, 151, 4, 22, '#a4cebf')
    s.rect(1101, 161, 28, 3, '#b2ddd0')
    s.rect(1136, 177, 22, 3, '#94c7b8')
    s.rect(1074, 174, 13, 6, '#658e53')
    s.rect(1078, 172, 5, 4, '#efd2bf')
    # Pequeno personagem de chapéu.
    s.sprite(810, 142, ['..hhh...', '.hhhhh..','hhhhhhh.','..sss...','..sks...','..bbb...','.sbbbs..','..bbb...','..p.p...','..t.t...'],
             {'h':'#d9b464','s':'#e9b184','k':'#5c493c','b':'#668f9b','p':'#5c6650','t':'#795b42'}, 4)
    chicken(s, 530, 151, 3)
    if total >= 100:
        chicken(s, 607, 168, 3)
    if total >= 500:
        chicken(s, 898, 157, 3)
    # Placa do jardim.
    s.rect(688, 145, 4, 26, '#98714b')
    s.rect(666, 130, 51, 25, '#9c754b')
    s.rect(668, 132, 47, 20, '#ecd3a0')
    s.text(675, 146, 'HORTA', 10, '#79573b')
    # Base da plantação e marcação dos meses.
    s.rect(x0-9, y0-10, weeks*step+16, 158, '#b3c485')
    s.rect(x0-5, y0-5, weeks*step+6, 148, '#c9b17c')
    fence(s, x0-9, y0+153, weeks*step+16)
    last_month = None
    for col in range(weeks):
        week_start = sunday + timedelta(days=col*7)
        visible = max(week_start, first)
        month_key = (visible.year, visible.month)
        if month_key != last_month:
            if col < weeks-2:
                s.text(x0+col*step, y0-20, MONTHS[visible.month-1], 10, '#647552')
            last_month = month_key
    for i, name in enumerate(['D', 'S', 'T', 'Q', 'Q', 'S', 'S']):
        s.text(x0-29, y0+i*step+13, name, 10, '#647552')
    for d in days:
        offset = (date.fromisoformat(d['date'])-sunday).days
        x, y = x0+(offset//7)*step, y0+d['weekday']*step
        label = f"{date.fromisoformat(d['date']).strftime('%d/%m/%Y')} · {d['count']} contribuições"
        s.parts.append(f'<g class="day" data-date="{d["date"]}" data-count="{d["count"]}" data-level="{d["level"]}"><title>{escape(label)}</title>')
        plot(s, x, y, d['level'])
        if d['date'] == today.isoformat():
            s.parts.append(f'<rect x="{x-1}" y="{y-1}" width="20" height="20" fill="none" stroke="#fff5cf" stroke-width="2"/>')
        s.end()
    # Canteiro de flores, fardos de feno e galinha no primeiro plano.
    for x in range(121, 234, 20):
        s.rect(x, 448, 3, 12, '#70934b')
        s.rect(x-3, 448, 9, 5, '#e8b998' if x % 3 else '#f4df92')
        s.rect(x, 449, 3, 3, '#af874a')
    for x in (1002, 1032):
        s.rect(x, 438, 26, 22, '#b5914f')
        s.rect(x+2, 438, 22, 18, '#e2c274')
        s.rect(x+6, 438, 3, 18, '#b99c5a')
        s.rect(x+18, 438, 3, 18, '#b99c5a')
    chicken(s, 1112, 437, 3)
    s.text(473, 454, 'CULTIVE UM POUQUINHO A CADA DIA', 11, '#71814e', 'letter-spacing="1"')
    s.end()
    s.text(36, 515, 'terra', 11, '#73816a')
    for level in range(5):
        plot(s, 89+level*25, 501, level)
    s.text(220, 515, 'colheita', 11, '#73816a')
    s.text(430, 515, '1 canteiro = 1 dia  ·  borda clara = hoje', 11, '#73816a')
    s.text(1067, 515, today.strftime('%d/%m/%Y')+' · UTC', 11, '#73816a')
    s.parts.append('</svg>')
    return '\n'.join(s.parts)+'\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='Gera dados fictícios, sem token ou rede.')
    parser.add_argument('--date', type=date.fromisoformat, help='Data final somente no modo demo (AAAA-MM-DD).')
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/farm.svg')
    args = parser.parse_args(argv)
    if args.date and not args.demo:
        parser.error('--date só pode ser usado junto com --demo.')
    today = args.date or datetime.now(timezone.utc).date()
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    username = (os.environ.get('FARM_USERNAME') or config.get('username') or '').strip()
    title = config.get('title', 'Meu cantinho de código')
    if not isinstance(title, str) or not 1 <= len(title) <= 40:
        raise ValueError('O título precisa ter entre 1 e 40 caracteres.')
    if args.demo:
        calendar, username = demo_calendar(today), username or 'demo'
    else:
        calendar = fetch_calendar(username, os.environ.get('GH_TOKEN', ''), today)
    days = normalize(calendar, today)
    svg = render(days, username, title, today, args.demo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Só substituir a imagem depois de consultar, validar e renderizar tudo.
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(svg, encoding='utf-8')
    temporary.replace(args.output)
    print(f'SVG gerado: {len(days)} dias; {sum(d["count"] for d in days)} contribuições.' + (' DEMONSTRAÇÃO.' if args.demo else ''))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        sys.exit(1)
