
(() => {
"use strict";

const VERSION = "0.1.0";
const LANGS = ["en","ru","pl","de","es","fr","pt","it","tr","uk"];
const NAMES = {en:"English",ru:"Русский",pl:"Polski",de:"Deutsch",es:"Español",fr:"Français",pt:"Português",it:"Italiano",tr:"Türkçe",uk:"Українська"};
const T = {
en:{start:"START SHIFT",cont:"CONTINUE",settings:"SETTINGS",credits:"CREDITS",exit:"EXIT",back:"BACK",title:"INCIDENT TERMINAL",db:"PERSONNEL DATABASE / OFFLINE",scan:"RUN DIAGNOSTIC",allow:"AUTHORIZE ENTRY",deny:"DENY ENTRY",risk:"RISK",shift:"SHIFT",language:"Language",volume:"Master volume",crt:"CRT intensity",grain:"Film grain",shake:"Screen shake",contrast:"High contrast",fullscreen:"Fullscreen",save:"Settings saved",newshift:"NEW SHIFT",result:"SHIFT RESULT"},
ru:{start:"НАЧАТЬ СМЕНУ",cont:"ПРОДОЛЖИТЬ",settings:"НАСТРОЙКИ",credits:"АВТОРЫ",exit:"ВЫХОД",back:"НАЗАД",title:"ТЕРМИНАЛ ИНЦИДЕНТА",db:"БАЗА ПЕРСОНАЛА / НЕТ СВЯЗИ",scan:"ДИАГНОСТИКА",allow:"РАЗРЕШИТЬ ВХОД",deny:"ОТКАЗАТЬ",risk:"РИСК",shift:"СМЕНА",language:"Язык",volume:"Общая громкость",crt:"Эффект CRT",grain:"Шум плёнки",shake:"Тряска экрана",contrast:"Высокий контраст",fullscreen:"Полный экран",save:"Настройки сохранены",newshift:"НОВАЯ СМЕНА",result:"ИТОГ СМЕНЫ"},
pl:{start:"ROZPOCZNIJ ZMIANĘ",cont:"KONTYNUUJ",settings:"USTAWIENIA",credits:"AUTORZY",exit:"WYJŚCIE",back:"WSTECZ",title:"TERMINAL INCYDENTU",db:"BAZA PERSONELU / OFFLINE",scan:"DIAGNOSTYKA",allow:"ZEZWÓL NA WEJŚCIE",deny:"ODMÓW",risk:"RYZYKO",shift:"ZMIANA",language:"Język",volume:"Głośność",crt:"Efekt CRT",grain:"Ziarno",shake:"Drgania",contrast:"Wysoki kontrast",fullscreen:"Pełny ekran",save:"Zapisano",newshift:"NOWA ZMIANA",result:"WYNIK"},
de:{start:"SCHICHT STARTEN",cont:"FORTSETZEN",settings:"EINSTELLUNGEN",credits:"CREDITS",exit:"BEENDEN",back:"ZURÜCK",title:"VORFALLTERMINAL",db:"PERSONALDATENBANK / OFFLINE",scan:"DIAGNOSE",allow:"ZUTRITT ERLAUBEN",deny:"ZUTRITT VERWEIGERN",risk:"RISIKO",shift:"SCHICHT",language:"Sprache",volume:"Lautstärke",crt:"CRT-Stärke",grain:"Filmkorn",shake:"Bildschirmzittern",contrast:"Hoher Kontrast",fullscreen:"Vollbild",save:"Gespeichert",newshift:"NEUE SCHICHT",result:"ERGEBNIS"},
es:{start:"INICIAR TURNO",cont:"CONTINUAR",settings:"AJUSTES",credits:"CRÉDITOS",exit:"SALIR",back:"VOLVER",title:"TERMINAL DE INCIDENTE",db:"BASE DE PERSONAL / SIN CONEXIÓN",scan:"DIAGNÓSTICO",allow:"AUTORIZAR ENTRADA",deny:"DENEGAR ENTRADA",risk:"RIESGO",shift:"TURNO",language:"Idioma",volume:"Volumen",crt:"Intensidad CRT",grain:"Grano",shake:"Sacudida",contrast:"Alto contraste",fullscreen:"Pantalla completa",save:"Guardado",newshift:"NUEVO TURNO",result:"RESULTADO"},
fr:{start:"COMMENCER LE SERVICE",cont:"CONTINUER",settings:"PARAMÈTRES",credits:"CRÉDITS",exit:"QUITTER",back:"RETOUR",title:"TERMINAL D'INCIDENT",db:"BASE DU PERSONNEL / HORS LIGNE",scan:"DIAGNOSTIC",allow:"AUTORISER L'ENTRÉE",deny:"REFUSER",risk:"RISQUE",shift:"SERVICE",language:"Langue",volume:"Volume",crt:"Intensité CRT",grain:"Grain",shake:"Tremblement",contrast:"Contraste élevé",fullscreen:"Plein écran",save:"Enregistré",newshift:"NOUVEAU SERVICE",result:"RÉSULTAT"},
pt:{start:"INICIAR TURNO",cont:"CONTINUAR",settings:"CONFIGURAÇÕES",credits:"CRÉDITOS",exit:"SAIR",back:"VOLTAR",title:"TERMINAL DE INCIDENTE",db:"BANCO DE PESSOAL / OFFLINE",scan:"DIAGNÓSTICO",allow:"AUTORIZAR ENTRADA",deny:"NEGAR ENTRADA",risk:"RISCO",shift:"TURNO",language:"Idioma",volume:"Volume",crt:"Intensidade CRT",grain:"Grão",shake:"Tremor",contrast:"Alto contraste",fullscreen:"Tela cheia",save:"Salvo",newshift:"NOVO TURNO",result:"RESULTADO"},
it:{start:"INIZIA TURNO",cont:"CONTINUA",settings:"IMPOSTAZIONI",credits:"CREDITI",exit:"ESCI",back:"INDIETRO",title:"TERMINALE INCIDENTE",db:"DATABASE PERSONALE / OFFLINE",scan:"DIAGNOSTICA",allow:"AUTORIZZA INGRESSO",deny:"NEGA INGRESSO",risk:"RISCHIO",shift:"TURNO",language:"Lingua",volume:"Volume",crt:"Intensità CRT",grain:"Grana",shake:"Tremolio",contrast:"Alto contrasto",fullscreen:"Schermo intero",save:"Salvato",newshift:"NUOVO TURNO",result:"RISULTATO"},
tr:{start:"VARDİYAYI BAŞLAT",cont:"DEVAM ET",settings:"AYARLAR",credits:"KREDİLER",exit:"ÇIKIŞ",back:"GERİ",title:"OLAY TERMİNALİ",db:"PERSONEL VERİTABANI / ÇEVRİMDIŞI",scan:"TANI",allow:"GİRİŞE İZİN VER",deny:"GİRİŞİ REDDET",risk:"RİSK",shift:"VARDİYA",language:"Dil",volume:"Ses",crt:"CRT yoğunluğu",grain:"Film gren",shake:"Ekran sarsıntısı",contrast:"Yüksek kontrast",fullscreen:"Tam ekran",save:"Kaydedildi",newshift:"YENİ VARDİYA",result:"SONUÇ"},
uk:{start:"ПОЧАТИ ЗМІНУ",cont:"ПРОДОВЖИТИ",settings:"НАЛАШТУВАННЯ",credits:"АВТОРИ",exit:"ВИХІД",back:"НАЗАД",title:"ТЕРМІНАЛ ІНЦИДЕНТУ",db:"БАЗА ПЕРСОНАЛУ / ОФЛАЙН",scan:"ДІАГНОСТИКА",allow:"ДОЗВОЛИТИ ВХІД",deny:"ВІДМОВИТИ",risk:"РИЗИК",shift:"ЗМІНА",language:"Мова",volume:"Гучність",crt:"Ефект CRT",grain:"Шум",shake:"Тремтіння",contrast:"Високий контраст",fullscreen:"Повний екран",save:"Збережено",newshift:"НОВА ЗМІНА",result:"ПІДСУМОК"}
};

const visitors = [
{name:"MARA VOSS",id:"A-104",division:"ARCHIVE",allow:false,anomaly:true,statement:"Personnel file matches. Claims the blackout locked her outside Sector C."},
{name:"JONAH REED",id:"M-221",division:"MAINTENANCE",allow:true,anomaly:false,statement:"Carries a sealed repair order for the ventilation grid. Badge is visibly damaged."},
{name:"DR. SERA VALE",id:"R-019",division:"RESEARCH",allow:false,anomaly:true,statement:"Requests emergency access to cold storage. No matching shift is present in the offline roster."},
{name:"LEON MERCER",id:"S-077",division:"SECURITY",allow:true,anomaly:false,statement:"Security officer returning from the east checkpoint. Knows the current challenge phrase."},
{name:"NAOMI KADE",id:"L-313",division:"LOGISTICS",allow:true,anomaly:false,statement:"Delivery supervisor with a manual manifest. Requests shelter until power returns."},
{name:"CIPHER-0",id:"NO RECORD",division:"UNKNOWN",allow:false,anomaly:true,statement:"The camera sees a person. The microphone records your own breathing."}
];

const $ = s => document.querySelector(s);
const state = {lang:"en",index:0,score:0,risk:0,scan:false,ended:false};
const settings = Object.assign({volume:.8,crt:.65,grain:.45,shake:true,contrast:false}, JSON.parse(localStorage.getItem("np_settings")||"{}"));
state.lang = settings.lang || "en";

function t(k){ return (T[state.lang]||T.en)[k] || T.en[k] || k; }
function saveState(){ localStorage.setItem("np_save", JSON.stringify(state)); }
function saveSettings(){ settings.lang=state.lang; localStorage.setItem("np_settings",JSON.stringify(settings)); }

function setScreen(id){
  document.querySelectorAll(".screen").forEach(x=>x.classList.remove("active"));
  $("#"+id).classList.add("active");
}
function beep(freq=440,d=.04,g=.025){
  if(!window.AudioContext && !window.webkitAudioContext) return;
  const C=window.AudioContext||window.webkitAudioContext;
  if(!beep.ctx) beep.ctx=new C();
  const ctx=beep.ctx,o=ctx.createOscillator(),gain=ctx.createGain();
  o.frequency.value=freq; o.type="square"; gain.gain.value=g*settings.volume;
  o.connect(gain); gain.connect(ctx.destination); o.start(); o.stop(ctx.currentTime+d);
}
function flash(cls="hit"){
  document.body.classList.add(cls);
  setTimeout(()=>document.body.classList.remove(cls),160);
}
function updateI18n(){
  document.querySelectorAll("[data-i18n]").forEach(el=>el.textContent=t(el.dataset.i18n));
  $("#langSelect").innerHTML=LANGS.map(x=>'<option value="'+x+'">'+NAMES[x]+'</option>').join("");
  $("#langSelect").value=state.lang;
}
function applySettings(){
  document.documentElement.style.setProperty("--crt", settings.crt);
  document.documentElement.style.setProperty("--grain", settings.grain);
  document.body.classList.toggle("contrast",!!settings.contrast);
  $("#volume").value=settings.volume;
  $("#crt").value=settings.crt;
  $("#grain").value=settings.grain;
  $("#shake").checked=!!settings.shake;
  $("#contrast").checked=!!settings.contrast;
}
function showMenu(){
  updateI18n(); applySettings();
  $("#continueBtn").disabled=!localStorage.getItem("np_save");
  setScreen("menu");
}
function newShift(){
  Object.assign(state,{index:0,score:0,risk:0,scan:false,ended:false});
  saveState(); showVisitor();
}
function continueShift(){
  const s=JSON.parse(localStorage.getItem("np_save")||"null");
  if(s) Object.assign(state,s);
  showVisitor();
}
function showVisitor(){
  if(state.index>=visitors.length){ showEnding(); return; }
  state.ended=false; state.scan=false;
  const v=visitors[state.index];
  $("#dbTitle").textContent=t("db");
  $("#termTitle").textContent=t("title");
  $("#visitorCount").textContent=String(state.index+1).padStart(2,"0")+" / 06";
  $("#name").textContent=v.name;
  $("#pid").textContent="ID: "+v.id;
  $("#division").textContent="DIVISION: "+v.division;
  $("#statement").textContent=v.statement;
  $("#scanResult").textContent="...";
  $("#scanBtn").disabled=false;
  $("#allowBtn").disabled=false;
  $("#denyBtn").disabled=false;
  $("#scanBtn").textContent=t("scan");
  $("#allowBtn").textContent=t("allow");
  $("#denyBtn").textContent=t("deny");
  updateHud(); setScreen("game");
}
function updateHud(){
  $("#hud").textContent=t("shift")+" 01   //   "+Math.min(state.index+1,6)+"/6   //   "+t("risk")+" "+state.risk+"%";
  $("#riskFill").style.width=Math.min(100,state.risk)+"%";
}
function scan(){
  if(state.ended){newShift();return;}
  if(state.scan) return;
  state.scan=true; state.risk=Math.min(100,state.risk+8); updateHud();
  $("#scanBtn").disabled=true; $("#scanResult").textContent="SCANNING...";
  beep(260,.08,.035);
  setTimeout(()=>{
    const v=visitors[state.index];
    $("#scanResult").textContent=v.anomaly?"DIAGNOSTIC: ANOMALY DETECTED. MANUAL JUDGMENT REQUIRED.":"DIAGNOSTIC: IDENTITY MARKERS CONSISTENT.";
    if(v.anomaly) flash("glitch");
  },650);
}
function decide(allow){
  if(state.ended) return;
  const v=visitors[state.index];
  const correct=allow===v.allow;
  if(correct){state.score++;state.risk=Math.min(100,state.risk+3);beep(610,.05,.025);}
  else {state.risk=Math.min(100,state.risk+22);beep(120,.12,.05);flash("glitch"); if(settings.shake) document.body.classList.add("shake"),setTimeout(()=>document.body.classList.remove("shake"),280);}
  state.index++; saveState(); setTimeout(showVisitor,180);
}
function showEnding(){
  state.ended=true; saveState();
  const good=state.score>=5&&state.risk<60, bad=state.risk>=85||state.score<=2;
  $("#endTitle").textContent=t("result")+" // "+state.score+"/6";
  $("#endText").textContent=good?"PROTOCOL STABLE — The blackout continues, but the archive remains sealed.":bad?"CONTAINMENT BREACH — The terminal stops responding. Something entered with you.":"SHIFT COMPROMISED — Too many uncertain calls. Command review initiated.";
  $("#newShiftBtn").textContent=t("newshift");
  setScreen("ending");
}
function openSettings(){
  updateI18n();applySettings();setScreen("settings");
}
function openCredits(){setScreen("credits");}
function toggleFullscreen(){
  if(!document.fullscreenElement) document.documentElement.requestFullscreen?.(); else document.exitFullscreen?.();
}
function bind(){
  $("#startBtn").onclick=newShift;
  $("#continueBtn").onclick=continueShift;
  $("#settingsBtn").onclick=openSettings;
  $("#creditsBtn").onclick=openCredits;
  $("#exitBtn").onclick=()=>window.close();
  $("#scanBtn").onclick=scan;
  $("#allowBtn").onclick=()=>decide(true);
  $("#denyBtn").onclick=()=>decide(false);
  $("#gameMenuBtn").onclick=showMenu;
  $("#settingsBack").onclick=()=>{saveSettings();showMenu();};
  $("#creditsBack").onclick=showMenu;
  $("#newShiftBtn").onclick=newShift;
  $("#endMenuBtn").onclick=showMenu;
  $("#fullscreenBtn").onclick=toggleFullscreen;
  $("#langSelect").onchange=e=>{state.lang=e.target.value;settings.lang=state.lang;saveSettings();updateI18n();};
  ["volume","crt","grain"].forEach(id=>$("#"+id).oninput=e=>{settings[id]=+e.target.value;applySettings();saveSettings();});
  ["shake","contrast"].forEach(id=>$("#"+id).onchange=e=>{settings[id]=e.target.checked;applySettings();saveSettings();});
  document.addEventListener("keydown",e=>{
    if($("#game").classList.contains("active")){
      if(e.key==="1")scan(); if(e.key==="2")decide(true); if(e.key==="3")decide(false); if(e.key==="Escape")showMenu();
    } else if(e.key==="Escape") showMenu();
  });
  document.querySelectorAll("button").forEach(b=>b.addEventListener("mouseenter",()=>beep(320,.018,.008)));
}
function boot(){
  updateI18n();applySettings();bind();
  let p=0;
  const phases=["BOOTING INCIDENT CORE","VERIFYING PERSONNEL CACHE","RESTORING CAMERA LINK","SEALING ARCHIVE DOOR","READY"];
  const timer=setInterval(()=>{
    p=Math.min(100,p+1+Math.floor(Math.random()*3));
    $("#bootFill").style.width=p+"%";
    $("#bootPct").textContent=p+"%";
    $("#bootPhase").textContent=phases[Math.min(phases.length-1,Math.floor(p/21))];
    if(p>=100){clearInterval(timer);setTimeout(()=>{document.body.classList.add("boot-done");showMenu();},350);}
  },42);
}
window.addEventListener("load",boot);
})();