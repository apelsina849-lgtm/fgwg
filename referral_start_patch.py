from pathlib import Path
import ast
import textwrap

p = Path('/app/bot.py')
code = p.read_text(encoding='utf-8')
marker = '# === DBS REFERRAL START MIDDLEWARE V5.10 ==='
if marker in code:
    print('referral middleware v5.10 already installed')
    raise SystemExit(0)

tree = ast.parse(code)
target = None
var_name = None

for node in ast.walk(tree):
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        continue
    value = getattr(node, 'value', None)
    if not isinstance(value, ast.Call):
        continue
    func = value.func
    func_name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else '')
    if func_name != 'Dispatcher':
        continue
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        var_name = node.targets[0].id
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        var_name = node.target.id
    if var_name:
        target = node
        break

if target is None or not var_name:
    raise RuntimeError('Could not locate aiogram Dispatcher assignment in /app/bot.py')

indent = ' ' * int(getattr(target, 'col_offset', 0))
block = r'''
# === DBS REFERRAL START MIDDLEWARE V5.10 ===
import os as _dbs_ref_os
import re as _dbs_ref_re
import json as _dbs_ref_json
import asyncio as _dbs_ref_asyncio
import urllib.request as _dbs_ref_urllib
try:
    from aiogram import BaseMiddleware as _DBSRefBaseMiddleware
except Exception:
    from aiogram.dispatcher.middlewares.base import BaseMiddleware as _DBSRefBaseMiddleware


def _dbs_ref_post_sync(code, user):
    url = (_dbs_ref_os.getenv('REFERRAL_API_URL') or 'https://digitalstudio-robot-24x7-production.up.railway.app/api/referral/v510/bot-start').strip()
    token = (_dbs_ref_os.getenv('BOT_TOKEN') or '').strip()
    if not url or not token:
        return None
    body = _dbs_ref_json.dumps({'code': code, 'user': user}, ensure_ascii=False).encode('utf-8')
    req = _dbs_ref_urllib.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json', 'X-DBS-Bot-Token': token},
        method='POST',
    )
    with _dbs_ref_urllib.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode('utf-8', 'replace')
        return _dbs_ref_json.loads(raw) if raw else None


class _DBSReferralStartMiddleware(_DBSRefBaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            text = str(getattr(event, 'text', '') or '').strip()
            match = _dbs_ref_re.fullmatch(r'/start(?:@\w+)?\s+(ref_\d{5,})', text)
            user = getattr(event, 'from_user', None)
            if match and user and getattr(user, 'id', None):
                payload = {
                    'id': int(user.id),
                    'username': getattr(user, 'username', None),
                    'first_name': getattr(user, 'first_name', None),
                    'last_name': getattr(user, 'last_name', None),
                }
                try:
                    await _dbs_ref_asyncio.to_thread(_dbs_ref_post_sync, match.group(1), payload)
                except Exception as exc:
                    print('DBS referral Start warning:', type(exc).__name__, str(exc)[:180])
        except Exception as exc:
            print('DBS referral middleware warning:', type(exc).__name__, str(exc)[:180])
        return await handler(event, data)

__DBS_DP__.message.outer_middleware(_DBSReferralStartMiddleware())
'''.replace('__DBS_DP__', var_name)

lines = code.splitlines(keepends=True)
insert_at = int(target.end_lineno)
indented = textwrap.indent(block.strip('\n') + '\n', indent)
lines.insert(insert_at, indented)
p.write_text(''.join(lines), encoding='utf-8')

# Validate patched source immediately; fail the image build instead of shipping a broken bot.
ast.parse(p.read_text(encoding='utf-8'))
print(f'referral middleware v5.10 installed on dispatcher {var_name}')
