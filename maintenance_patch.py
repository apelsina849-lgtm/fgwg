from pathlib import Path
import ast
APP=Path('/app/app.py'); BOT=Path('/app/bot.py')
app=APP.read_text(encoding='utf-8')
if '# DBS_MAINTENANCE_V519' not in app:
    addon=r"""
# DBS_MAINTENANCE_V519
import json as _mjson
from pathlib import Path as _MPath
from fastapi import Request as _MRequest, Header as _MHeader, HTTPException as _MHTTPException
from fastapi.responses import JSONResponse as _MJSON
_MFILE=_MPath(os.getenv('DATA_DIR','/app/data'))/'maintenance_mode.json'
_MFILE.parent.mkdir(parents=True,exist_ok=True)
def _mstate():
    try:
        x=_mjson.loads(_MFILE.read_text(encoding='utf-8'))
        return {'enabled':bool(x.get('enabled')),'message':str(x.get('message') or 'Мы обновляем Digital Bot Studio и скоро вернёмся.')}
    except Exception: return {'enabled':False,'message':'Мы обновляем Digital Bot Studio и скоро вернёмся.'}
def _msave(enabled,message=None):
    x=_mstate(); x['enabled']=bool(enabled)
    if message is not None: x['message']=str(message).strip()[:240] or x['message']
    _MFILE.write_text(_mjson.dumps(x,ensure_ascii=False),encoding='utf-8'); return x
@app.get('/api/maintenance')
def _m_public(): return {'ok':True,**_mstate()}
@app.get('/api/admin/maintenance')
def _m_get(x_telegram_init_data: str|None=_MHeader(default=None)):
    u=_user_from_header(x_telegram_init_data); _require_admin(u); return {'ok':True,**_mstate()}
@app.post('/api/admin/maintenance')
def _m_set(body: dict,x_telegram_init_data: str|None=_MHeader(default=None)):
    u=_user_from_header(x_telegram_init_data); _require_admin(u)
    if str(u.get('id')) != str(os.getenv('OWNER_ID','')).strip(): raise _MHTTPException(403,'Только владелец может включать технические работы')
    return {'ok':True,**_msave(body.get('enabled'),body.get('message'))}
@app.middleware('http')
async def _m_gate(request: _MRequest,call_next):
    x=_mstate(); p=request.url.path
    if x['enabled'] and p.startswith('/api/') and p not in ('/api/maintenance','/api/bootstrap','/api/admin/maintenance'):
        try: u=_user_from_header(request.headers.get('x-telegram-init-data'))
        except Exception: u=None
        if not u or not db.is_admin(int(u.get('id'))): return _MJSON({'detail':'Технические работы','maintenance':True,'message':x['message']},status_code=503)
    return await call_next(request)
"""
    app += addon
    js=r"""
(()=>{let shown=false;const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function check(){try{const r=await fetch('/api/maintenance',{cache:'no-store'}),x=await r.json(),admin=window.state?.data?.is_admin;if(x.enabled&&!admin&&!shown){shown=true;document.body.innerHTML='<main class="dbs519-maintenance"><div class="dbs519-orbit"><b>DB</b><i></i><i></i><i></i></div><small>DIGITAL BOT STUDIO · LIVE UPDATE</small><h1>Технические работы</h1><p>'+esc(x.message)+'</p><span>✦ ОБНОВЛЯЕМ СЕРВИС ✦ СКОРО ВЕРНЁМСЯ ✦</span></main>'}if(!x.enabled&&shown)location.reload()}catch(_){}}check();setInterval(check,12000)})();
"""
    APP.write_text(app,encoding='utf-8')
    p=Path('/app/static/app.js')
    if p.exists(): p.write_text(p.read_text(encoding='utf-8')+'\n'+js,encoding='utf-8')
    s=Path('/app/static/styles.css')
    if s.exists(): s.write_text(s.read_text(encoding='utf-8')+'.dbs519-maintenance{min-height:100vh;display:grid;place-items:center;align-content:center;gap:14px;padding:28px;text-align:center;color:#f5f7ff;background:radial-gradient(circle,#243a6a,#070a16 65%)}.dbs519-maintenance h1{font-size:clamp(30px,8vw,54px);margin:0}.dbs519-maintenance p{max-width:440px;color:#b7c5e8;line-height:1.5}.dbs519-maintenance span{font-size:11px;letter-spacing:.15em;color:#67e8f9;white-space:nowrap;animation:mTicker 8s linear infinite}.dbs519-orbit{width:110px;height:110px;display:grid;place-items:center;position:relative;margin:auto;border:1px solid #67e8f966;border-radius:50%;box-shadow:0 0 46px #38bdf833}.dbs519-orbit i{position:absolute;inset:10px;border:2px solid #67e8f9;border-radius:50%;animation:mSpin 4s linear infinite}.dbs519-orbit i:nth-child(2){inset:22px;border-color:#c084fc;animation-duration:2.8s}.dbs519-orbit i:nth-child(3){inset:34px;border-color:#fbbf24;animation-duration:2s}@keyframes mSpin{to{transform:rotate(360deg)}}@keyframes mTicker{to{transform:translateX(-12%)}}',encoding='utf-8')
bot=BOT.read_text(encoding='utf-8')
if '# DBS_MAINTENANCE_V519' not in bot:
    gate=r"""
# DBS_MAINTENANCE_V519
def _mstate():
    try:
        import json
        from pathlib import Path
        x=json.loads((Path(DATA_DIR)/'maintenance_mode.json').read_text(encoding='utf-8'))
        return bool(x.get('enabled')),str(x.get('message') or 'Мы обновляем Digital Bot Studio и скоро вернёмся.')
    except Exception: return False,'Мы обновляем Digital Bot Studio и скоро вернёмся.'
"""
    bot=bot.replace('def handle_message(msg):',gate+'\ndef handle_message(msg):',1)
    bot=bot.replace('def handle_message(msg):\n','def handle_message(msg):\n    _on,_notice=_mstate()\n    _uid=(msg.get("from") or {}).get("id")\n    if _on and not db.is_admin(int(_uid or 0)):\n        send(msg.get("chat",{}).get("id"), "<b>🛠 Технические работы</b>\\n\\n"+e(_notice))\n        return\n',1)
    BOT.write_text(bot,encoding='utf-8')
ast.parse(APP.read_text(encoding='utf-8')); ast.parse(BOT.read_text(encoding='utf-8'))
print('maintenance patch ready')
