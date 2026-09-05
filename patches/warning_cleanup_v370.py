from pathlib import Path

p = Path('server/source/include/oldsamprp/arizona_factions_pro.inc')
s = p.read_text(encoding='utf-8')
s = s.replace('new FG_PendingTarget[MAX_PLAYERS] = { INVALID_PLAYER_ID, ... };\n', '')
p.write_text(s, encoding='utf-8', newline='\n')

p = Path('server/source/include/oldsamprp/v350_rework.inc')
s = p.read_text(encoding='utf-8')
for line in (
    'new gV350_RecruitActor = INVALID_ACTOR_ID;\n',
    'new gV350_LastTick;\n',
    '    gV350_RecruitActor=INVALID_ACTOR_ID;\n',
):
    s = s.replace(line, '')
p.write_text(s, encoding='utf-8', newline='\n')
print('warning cleanup applied')
