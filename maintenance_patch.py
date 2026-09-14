from pathlib import Path
import ast
APP=Path('/app/app.py')
BOT=Path('/app/bot.py')

app=APP.read_text(encoding='utf-8')
if '# === DBS MAINTENANCE MODE V5.19 ===' not in app:
    addon=r'''
# === DBS MAINTENANCE MODE V5.19 ===
import json as _dbs519_json
from pathlib import Path as _DBS519Path
from fastapi import Request as _DBS519Request
from fastapi.responses import JSONResponse as _DBS519JSONResponse
_DBS519_FILE = _DBS519Path(_dbs_os.getenv('DATA_DIR','/app/data')) / 'maintenance_mode.json'
_DBS519_FILE.parent.mkdir(parents=True, exist_ok=True)

def _dbs519_state():
    try:
        data=_dbs519_json.loads(_DBS519_FILE.read_text(encoding='utf-8'))
        return {'enabled':bool(data.get('enabled')), 'message':str(data.get('message') or 'Мы обновляем Digital Bot Studio и скоро вернёмся.')}
    except Exception:
        return {'enabled':False,'message':'Мы обновляем Digital Bot Studio и скоро вернёмся.'}

def _dbs519_save(enabled,message=None):
    state=_dbs519_state()
    state['enabled']=bool(enabled)
    if message is not None: state['message']=str(message).strip()[:240] or state['message']
    tmp=_DBS519_FILE.with_suffix('.tmp')
    tmp.write_text(_dbs519_json.dumps(state,ensure_ascii=False),encoding='utf-8')
    tmp.replace(_DBS519_FILE)
    return state

@app.get('/api/maintenance')
def _dbs519_public():
    return {'ok':True, **_dbs519_state()}

@app.get('/api/admin/maintenance')
def _dbs519_admin_get(x_telegram_init_data: str|None = Header(default=None)):
    user=_user_from_header(x_telegram_init_data)
    _require_admin(user)
    return {'ok':True, **_dbs519_state(), 'is_owner':str(user.get('id'))==str(os.getenv('OWNER_ID','')).strip()}

@app.post('/api/admin/maintenance')
def _dbs519_admin_set(body: dict, x_telegram_init_data: str|None = Header(default=None)):
    user=_user_from_header(x_telegram_init_data)
    _require_admin(user)
    if str(user.get('id')) != str(os.getenv('OWNER_ID','')).strip():
        raise HTTPException(status_code=403, detail='Только владелец может включать технические работы')
    return {'ok':True, **_dbs519_save(bool(body.get('enabled')),body.get('message'))}

@app.middleware('http')
async def _dbs519_gate(request: _DBS519Request, call_next):
    state=_dbs519_state()
    path=request.url.path
    if state['enabled'] and path.startswith('/api/') and path not in ('/api/bootstrap','/api/maintenance','/api/admin/maintenance'):
        try:
            user=_user_from_header(request.headers.get('x-telegram-init-data'))
            if not user or not db.is_admin(int(user.get('id'))):
                return _DBS519JSONResponse({'detail':'Технические работы','maintenance':True,'message':state['message']},status_code=503,headers={'Retry-After':'60'})
        except Exception:
            return _DBS519JSONResponse({'detail':'Технические работы','maintenance':True,'message':state['message']},status_code=503,headers={'Retry-After':'60'})
    return await call_next(request)

# Maintenance screen is injected into the existing static app without changing its API.
_js=r'''
(()=>{const M='/api/maintenance',esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));let shown=false;
async function check(){try{const r=await fetch(M,{cache:'no-store'}),x=await r.json();const admin=window.state?.data?.is_admin;if(x.enabled&&!admin){if(!shown){shown=true;document.body.innerHTML='<main class="dbs519-maintenance"><div class="dbs519-orbit"><i></i><i></i><i></i><b>DB</b></div><p class="dbs519-kicker">DIGITAL BOT STUDIO · LIVE UPDATE</p><h1>Технические работы</h1><p>'+esc(x.message)+'</p><span class="dbs519-ticker">✦ ОБНОВЛЯЕМ СЕРВИС ✦ ПОЛИРУЕМ ДЕТАЛИ ✦ СКОРО ВЕРНЁМСЯ ✦</span><small>Мы сохраняем ваши данные и уведомим, когда всё будет готово.</small></main>';}}else if(shown)location.reload()}catch(_){}}check();setInterval(check,12000)})();
\\n(()=>{let last=\'\';async function add(){const h=[...document.querySelectorAll(\'h1,h2,h3\')].find(x=>/управлен|настройк/i.test(x.textContent||\'\'));if(!h||document.querySelector(\'[data-dbs519-admin]\'))return;try{const r=await fetch(\'/api/admin/maintenance\'),x=await r.json();const b=document.createElement(\'div\');b.dataset.dbs519Admin=\'1\';b.style.cssText=\'margin:12px 0;padding:16px;border:1px solid #ffffff22;border-radius:20px;background:#ffffff0d\';b.innerHTML=\'<strong>🛠 Технический режим</strong><p style="margin:7px 0;color:#9aa7c7;font-size:13px">Оставляет доступ владельцу и администраторам.</p><button type="button" style="padding:10px 14px;border:0;border-radius:12px;background:#6ee7ff;color:#07111f;font-weight:700">\'+(x.enabled?\'Выключить техработы\':\'Включить техработы\')+\'</button>\';b.querySelector(\'button\').onclick=async()=>{const q=await fetch(\'/api/admin/maintenance\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({enabled:!x.enabled})});if(q.ok)location.reload();};h.insertAdjacentElement(\'afterend\',b)}catch(_){}}setInterval(add,700);add()})();\\n'''
if 'dbs519-maintenance' not in app:
    app += addon
    app=app.replace("Path('/app/static/app.js').", "Path('/app/static/app.js').") if False else app
    APP.write_text(app,encoding='utf-8')
    js=Path('/app/static/app.js')
    if js.exists(): js.write_text(js.read_text(encoding='utf-8')+'\n'+_js,encoding='utf-8')
    css=Path('/app/static/styles.css')
    if css.exists(): css.write_text(css.read_text(encoding='utf-8')+r'''
.dbs519-maintenance{min-height:100vh;display:grid;place-items:center;align-content:center;gap:14px;padding:30px;text-align:center;color:#f5f7ff;background:radial-gradient(circle at 50% 20%,#243a6a 0,#0b1022 42%,#050712 100%);overflow:hidden}.dbs519-maintenance h1{margin:0;font-size:clamp(30px,8vw,54px);letter-spacing:-.04em}.dbs519-maintenance p{max-width:440px;margin:0;color:#b7c5e8;font-size:16px;line-height:1.5}.dbs519-kicker{font-size:11px!important;letter-spacing:.18em;color:#67e8f9!important}.dbs519-maintenance small{color:#7180a8}.dbs519-ticker{max-width:100%;overflow:hidden;color:#7dd3fc;font-size:11px;letter-spacing:.16em;white-space:nowrap;animation:dbs519ticker 8s linear infinite}.dbs519-orbit{position:relative;width:110px;height:110px;display:grid;place-items:center;margin-bottom:8px;border:1px solid #67e8f966;border-radius:50%;box-shadow:0 0 46px #38bdf833;animation:dbs519float 3s ease-in-out infinite}.dbs519-orbit b{font-size:27px;color:#fff;text-shadow:0 0 18px #67e8f9}.dbs519-orbit i{position:absolute;inset:8px;border:2px solid #67e8f9;border-radius:50%;animation:dbs519spin 4s linear infinite}.dbs519-orbit i:nth-child(2){inset:18px;border-color:#c084fc;animation-duration:3s;animation-direction:reverse}.dbs519-orbit i:nth-child(3){inset:28px;border-color:#fbbf24;animation-duration:2s}@keyframes dbs519spin{to{transform:rotate(360deg)}}@keyframes dbs519float{50%{transform:translateY(-7px)}}@keyframes dbs519ticker{to{transform:translateX(-12%)}}''',encoding='utf-8')
else: print('app patch exists')

bot=BOT.read_text(encoding='utf-8')
if '# === DBS MAINTENANCE MODE V5.19 ===' not in bot:
    marker='def handle_message(msg):'
    gate=r'''def _dbs519_state():
    try:
        import json as _j
        from pathlib import Path as _P
        p=_P(DATA_DIR)/'maintenance_mode.json'
        x=_j.loads(p.read_text(encoding='utf-8'))
        return bool(x.get('enabled')), str(x.get('message') or 'Мы обновляем Digital Bot Studio и скоро вернёмся.')
    except Exception:
        return False, 'Мы обновляем Digital Bot Studio и скоро вернёмся.'

def _dbs519_allowed(user_id):
    try: return bool(db.is_admin(int(user_id)))
    except Exception: return str(user_id)==str(OWNER_ID)

# === DBS MAINTENANCE MODE V5.19 ===
'''
    if marker not in bot: raise RuntimeError('handle_message marker not found')
    bot=bot.replace(marker,gate+marker,1)
    old="def handle_message(msg):
"
    new=old+"    _on,_notice=_dbs519_state()\n    _uid=((msg.get('from') or {}).get('id'))\n    if _on and not _dbs519_allowed(_uid):\n        send(msg.get('chat',{}).get('id'), '<b>🛠 Технические работы</b>\\n\\n'+e(_notice)+'\\n\\n<i>Попробуйте открыть бот позже.</i>')\n        return\n"
    bot=bot.replace(old,new,1)
    BOT.write_text(bot,encoding='utf-8')
else: print('bot patch exists')
ast.parse(BOT.read_text(encoding='utf-8'));ast.parse(APP.read_text(encoding='utf-8'))
print('maintenance patch ready')
