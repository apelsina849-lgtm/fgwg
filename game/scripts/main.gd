extends Node

const VERSION := "0.1.0"
const LANGUAGE_CODES := ["en", "ru", "pl", "de", "es", "fr", "pt", "it", "tr", "uk"]
const LANGUAGE_NAMES := ["English", "Русский", "Polski", "Deutsch", "Español", "Français", "Português", "Italiano", "Türkçe", "Українська"]

const STRINGS := {
    "en": {
        "start": "START SHIFT", "settings": "SETTINGS", "exit": "EXIT",
        "settings_title": "SYSTEM SETTINGS", "language": "Language", "fullscreen": "Fullscreen",
        "vsync": "VSync", "volume": "Master volume", "shake": "Screen shake", "back": "BACK",
        "database": "PERSONNEL DATABASE / OFFLINE", "terminal": "INCIDENT TERMINAL",
        "visitor": "VISITOR", "shift": "SHIFT", "risk": "RISK", "scan": "[1] RUN DIAGNOSTIC",
        "allow": "[2] AUTHORIZE ENTRY", "deny": "[3] DENY ENTRY",
        "controls": "1 Diagnostic   2 Authorize   3 Deny   ESC Menu",
        "record": "PERSONNEL FILE", "statement": "STATEMENT",
        "scan_clean": "DIAGNOSTIC: identity markers consistent.",
        "scan_alert": "DIAGNOSTIC: anomaly detected. Manual judgment required.",
        "good": "PROTOCOL STABLE\nThe blackout continues, but the archive remains sealed.",
        "mid": "SHIFT COMPROMISED\nToo many uncertain calls. Command review initiated.",
        "bad": "CONTAINMENT BREACH\nThe terminal stops responding. Something entered with you.",
        "new_shift": "RESTART SHIFT"
    },
    "ru": {
        "start": "НАЧАТЬ СМЕНУ", "settings": "НАСТРОЙКИ", "exit": "ВЫХОД",
        "settings_title": "СИСТЕМНЫЕ НАСТРОЙКИ", "language": "Язык", "fullscreen": "Полный экран",
        "vsync": "Вертикальная синхронизация", "volume": "Общая громкость", "shake": "Тряска экрана", "back": "НАЗАД",
        "database": "БАЗА ПЕРСОНАЛА / НЕТ СВЯЗИ", "terminal": "ТЕРМИНАЛ ИНЦИДЕНТА",
        "visitor": "ПОСЕТИТЕЛЬ", "shift": "СМЕНА", "risk": "РИСК", "scan": "[1] ДИАГНОСТИКА",
        "allow": "[2] РАЗРЕШИТЬ ВХОД", "deny": "[3] ОТКАЗАТЬ",
        "controls": "1 Диагностика   2 Впустить   3 Отказать   ESC Меню",
        "record": "ЛИЧНОЕ ДЕЛО", "statement": "ЗАЯВЛЕНИЕ",
        "scan_clean": "ДИАГНОСТИКА: признаки личности совпадают.",
        "scan_alert": "ДИАГНОСТИКА: обнаружена аномалия. Решение за оператором.",
        "good": "ПРОТОКОЛ СТАБИЛЕН\nСвязи всё ещё нет, но архив изолирован.",
        "mid": "СМЕНА СКОМПРОМЕТИРОВАНА\nСлишком много сомнительных решений. Начата проверка.",
        "bad": "НАРУШЕНИЕ ИЗОЛЯЦИИ\nТерминал перестал отвечать. Что-то вошло вместе с вами.",
        "new_shift": "НАЧАТЬ ЗАНОВО"
    },
    "pl": {
        "start": "ROZPOCZNIJ ZMIANĘ", "settings": "USTAWIENIA", "exit": "WYJŚCIE",
        "settings_title": "USTAWIENIA SYSTEMU", "language": "Język", "fullscreen": "Pełny ekran",
        "vsync": "VSync", "volume": "Głośność", "shake": "Drgania ekranu", "back": "WSTECZ",
        "database": "BAZA PERSONELU / OFFLINE", "terminal": "TERMINAL INCYDENTU",
        "visitor": "GOŚĆ", "shift": "ZMIANA", "risk": "RYZYKO", "scan": "[1] DIAGNOSTYKA",
        "allow": "[2] ZEZWÓL NA WEJŚCIE", "deny": "[3] ODMÓW",
        "controls": "1 Diagnostyka   2 Zezwól   3 Odmów   ESC Menu",
        "record": "AKTA PERSONELU", "statement": "OŚWIADCZENIE",
        "scan_clean": "DIAGNOSTYKA: znaczniki tożsamości zgodne.",
        "scan_alert": "DIAGNOSTYKA: wykryto anomalię. Wymagana decyzja operatora.",
        "good": "PROTOKÓŁ STABILNY\nArchiwum pozostaje zamknięte.", "mid": "ZMIANA ZAGROŻONA\nRozpoczęto kontrolę.",
        "bad": "NARUSZENIE IZOLACJI\nTerminal przestał odpowiadać.", "new_shift": "NOWA ZMIANA"
    },
    "de": {
        "start": "SCHICHT STARTEN", "settings": "EINSTELLUNGEN", "exit": "BEENDEN",
        "settings_title": "SYSTEMEINSTELLUNGEN", "language": "Sprache", "fullscreen": "Vollbild",
        "vsync": "VSync", "volume": "Gesamtlautstärke", "shake": "Bildschirmzittern", "back": "ZURÜCK",
        "database": "PERSONALDATENBANK / OFFLINE", "terminal": "VORFALLTERMINAL",
        "visitor": "BESUCHER", "shift": "SCHICHT", "risk": "RISIKO", "scan": "[1] DIAGNOSE",
        "allow": "[2] ZUTRITT ERLAUBEN", "deny": "[3] ZUTRITT VERWEIGERN",
        "controls": "1 Diagnose   2 Erlauben   3 Verweigern   ESC Menü", "record": "PERSONALAKTE", "statement": "AUSSAGE",
        "scan_clean": "DIAGNOSE: Identitätsmerkmale stimmen überein.",
        "scan_alert": "DIAGNOSE: Anomalie erkannt. Manuelle Entscheidung nötig.",
        "good": "PROTOKOLL STABIL\nDas Archiv bleibt versiegelt.", "mid": "SCHICHT GEFÄHRDET\nÜberprüfung eingeleitet.",
        "bad": "EINDÄMMUNGSBRUCH\nDas Terminal antwortet nicht mehr.", "new_shift": "SCHICHT NEU STARTEN"
    },
    "es": {
        "start": "INICIAR TURNO", "settings": "AJUSTES", "exit": "SALIR",
        "settings_title": "AJUSTES DEL SISTEMA", "language": "Idioma", "fullscreen": "Pantalla completa",
        "vsync": "VSync", "volume": "Volumen general", "shake": "Sacudida de pantalla", "back": "VOLVER",
        "database": "BASE DE PERSONAL / SIN CONEXIÓN", "terminal": "TERMINAL DE INCIDENTE",
        "visitor": "VISITANTE", "shift": "TURNO", "risk": "RIESGO", "scan": "[1] DIAGNÓSTICO",
        "allow": "[2] AUTORIZAR ENTRADA", "deny": "[3] DENEGAR ENTRADA",
        "controls": "1 Diagnóstico   2 Autorizar   3 Denegar   ESC Menú", "record": "EXPEDIENTE", "statement": "DECLARACIÓN",
        "scan_clean": "DIAGNÓSTICO: identidad consistente.", "scan_alert": "DIAGNÓSTICO: anomalía detectada.",
        "good": "PROTOCOLO ESTABLE\nEl archivo permanece sellado.", "mid": "TURNO COMPROMETIDO\nRevisión iniciada.",
        "bad": "FALLO DE CONTENCIÓN\nEl terminal dejó de responder.", "new_shift": "REINICIAR TURNO"
    },
    "fr": {
        "start": "COMMENCER LE SERVICE", "settings": "PARAMÈTRES", "exit": "QUITTER",
        "settings_title": "PARAMÈTRES SYSTÈME", "language": "Langue", "fullscreen": "Plein écran",
        "vsync": "VSync", "volume": "Volume général", "shake": "Tremblement écran", "back": "RETOUR",
        "database": "BASE DU PERSONNEL / HORS LIGNE", "terminal": "TERMINAL D'INCIDENT",
        "visitor": "VISITEUR", "shift": "SERVICE", "risk": "RISQUE", "scan": "[1] DIAGNOSTIC",
        "allow": "[2] AUTORISER L'ENTRÉE", "deny": "[3] REFUSER L'ENTRÉE",
        "controls": "1 Diagnostic   2 Autoriser   3 Refuser   ESC Menu", "record": "DOSSIER", "statement": "DÉCLARATION",
        "scan_clean": "DIAGNOSTIC : identité cohérente.", "scan_alert": "DIAGNOSTIC : anomalie détectée.",
        "good": "PROTOCOLE STABLE\nLes archives restent scellées.", "mid": "SERVICE COMPROMIS\nRévision lancée.",
        "bad": "RUPTURE DE CONFINEMENT\nLe terminal ne répond plus.", "new_shift": "RECOMMENCER"
    },
    "pt": {
        "start": "INICIAR TURNO", "settings": "CONFIGURAÇÕES", "exit": "SAIR",
        "settings_title": "CONFIGURAÇÕES DO SISTEMA", "language": "Idioma", "fullscreen": "Tela cheia",
        "vsync": "VSync", "volume": "Volume geral", "shake": "Tremor da tela", "back": "VOLTAR",
        "database": "BANCO DE PESSOAL / OFFLINE", "terminal": "TERMINAL DE INCIDENTE",
        "visitor": "VISITANTE", "shift": "TURNO", "risk": "RISCO", "scan": "[1] DIAGNÓSTICO",
        "allow": "[2] AUTORIZAR ENTRADA", "deny": "[3] NEGAR ENTRADA",
        "controls": "1 Diagnóstico   2 Autorizar   3 Negar   ESC Menu", "record": "ARQUIVO PESSOAL", "statement": "DECLARAÇÃO",
        "scan_clean": "DIAGNÓSTICO: identidade consistente.", "scan_alert": "DIAGNÓSTICO: anomalia detectada.",
        "good": "PROTOCOLO ESTÁVEL\nO arquivo permanece selado.", "mid": "TURNO COMPROMETIDO\nRevisão iniciada.",
        "bad": "FALHA DE CONTENÇÃO\nO terminal parou de responder.", "new_shift": "REINICIAR TURNO"
    },
    "it": {
        "start": "INIZIA TURNO", "settings": "IMPOSTAZIONI", "exit": "ESCI",
        "settings_title": "IMPOSTAZIONI DI SISTEMA", "language": "Lingua", "fullscreen": "Schermo intero",
        "vsync": "VSync", "volume": "Volume generale", "shake": "Tremolio schermo", "back": "INDIETRO",
        "database": "DATABASE PERSONALE / OFFLINE", "terminal": "TERMINALE INCIDENTE",
        "visitor": "VISITATORE", "shift": "TURNO", "risk": "RISCHIO", "scan": "[1] DIAGNOSTICA",
        "allow": "[2] AUTORIZZA INGRESSO", "deny": "[3] NEGA INGRESSO",
        "controls": "1 Diagnostica   2 Autorizza   3 Nega   ESC Menu", "record": "FASCICOLO", "statement": "DICHIARAZIONE",
        "scan_clean": "DIAGNOSTICA: identità coerente.", "scan_alert": "DIAGNOSTICA: anomalia rilevata.",
        "good": "PROTOCOLLO STABILE\nL'archivio resta sigillato.", "mid": "TURNO COMPROMESSO\nRevisione avviata.",
        "bad": "VIOLAZIONE DEL CONTENIMENTO\nIl terminale non risponde.", "new_shift": "RIAVVIA TURNO"
    },
    "tr": {
        "start": "VARDİYAYI BAŞLAT", "settings": "AYARLAR", "exit": "ÇIKIŞ",
        "settings_title": "SİSTEM AYARLARI", "language": "Dil", "fullscreen": "Tam ekran",
        "vsync": "VSync", "volume": "Ana ses", "shake": "Ekran sarsıntısı", "back": "GERİ",
        "database": "PERSONEL VERİTABANI / ÇEVRİMDIŞI", "terminal": "OLAY TERMİNALİ",
        "visitor": "ZİYARETÇİ", "shift": "VARDİYA", "risk": "RİSK", "scan": "[1] TANI",
        "allow": "[2] GİRİŞE İZİN VER", "deny": "[3] GİRİŞİ REDDET",
        "controls": "1 Tanı   2 İzin ver   3 Reddet   ESC Menü", "record": "PERSONEL DOSYASI", "statement": "İFADE",
        "scan_clean": "TANI: kimlik işaretleri tutarlı.", "scan_alert": "TANI: anomali tespit edildi.",
        "good": "PROTOKOL KARARLI\nArşiv mühürlü kaldı.", "mid": "VARDİYA RİSKLİ\nİnceleme başlatıldı.",
        "bad": "MUHAFAZA İHLALİ\nTerminal yanıt vermiyor.", "new_shift": "VARDİYAYI YENİDEN BAŞLAT"
    },
    "uk": {
        "start": "ПОЧАТИ ЗМІНУ", "settings": "НАЛАШТУВАННЯ", "exit": "ВИХІД",
        "settings_title": "СИСТЕМНІ НАЛАШТУВАННЯ", "language": "Мова", "fullscreen": "Повний екран",
        "vsync": "VSync", "volume": "Загальна гучність", "shake": "Тремтіння екрана", "back": "НАЗАД",
        "database": "БАЗА ПЕРСОНАЛУ / ОФЛАЙН", "terminal": "ТЕРМІНАЛ ІНЦИДЕНТУ",
        "visitor": "ВІДВІДУВАЧ", "shift": "ЗМІНА", "risk": "РИЗИК", "scan": "[1] ДІАГНОСТИКА",
        "allow": "[2] ДОЗВОЛИТИ ВХІД", "deny": "[3] ВІДМОВИТИ",
        "controls": "1 Діагностика   2 Дозволити   3 Відмовити   ESC Меню", "record": "ОСОБОВА СПРАВА", "statement": "ЗАЯВА",
        "scan_clean": "ДІАГНОСТИКА: ознаки особи збігаються.", "scan_alert": "ДІАГНОСТИКА: виявлено аномалію.",
        "good": "ПРОТОКОЛ СТАБІЛЬНИЙ\nАрхів залишається закритим.", "mid": "ЗМІНА СКОМПРОМЕТОВАНА\nРозпочато перевірку.",
        "bad": "ПОРУШЕННЯ ІЗОЛЯЦІЇ\nТермінал більше не відповідає.", "new_shift": "ПОЧАТИ ЗНОВУ"
    }
}

var visitors := [
    {
        "name": "MARA VOSS", "id": "A-104", "division": "ARCHIVE", "allow": false, "anomaly": true,
        "statement": {"en": "Personnel file matches. Claims the blackout locked her outside Sector C.", "ru": "Личное дело совпадает. Утверждает, что отключение света заперло её вне сектора C."}
    },
    {
        "name": "JONAH REED", "id": "M-221", "division": "MAINTENANCE", "allow": true, "anomaly": false,
        "statement": {"en": "Carries a sealed repair order for the ventilation grid. Badge is visibly damaged.", "ru": "Несёт запечатанный наряд на ремонт вентиляции. Пропуск заметно повреждён."}
    },
    {
        "name": "DR. SERA VALE", "id": "R-019", "division": "RESEARCH", "allow": false, "anomaly": true,
        "statement": {"en": "Requests emergency access to cold storage. No matching shift is present in the offline roster.", "ru": "Просит аварийный доступ к холодильному хранилищу. В офлайн-графике её смены нет."}
    },
    {
        "name": "LEON MERCER", "id": "S-077", "division": "SECURITY", "allow": true, "anomaly": false,
        "statement": {"en": "Security officer returning from the east checkpoint. Knows the current challenge phrase.", "ru": "Охранник возвращается с восточного поста. Знает текущую контрольную фразу."}
    },
    {
        "name": "NAOMI KADE", "id": "L-313", "division": "LOGISTICS", "allow": true, "anomaly": false,
        "statement": {"en": "Delivery supervisor with a manual manifest. Requests shelter until power returns.", "ru": "Начальник доставки с бумажной ведомостью. Просит укрытие до восстановления питания."}
    },
    {
        "name": "CIPHER-0", "id": "NO RECORD", "division": "UNKNOWN", "allow": false, "anomaly": true,
        "statement": {"en": "The camera sees a person. The microphone records your own breathing.", "ru": "Камера видит человека. Микрофон записывает ваше собственное дыхание."}
    }
]

var language_code := "en"
var current := 0
var score := 0
var risk := 0
var scan_used := false
var shake_enabled := true
var shake_time := 0.0

var camera: Camera3D
var camera_base := Vector3(0.0, 1.55, 5.2)
var main_light: OmniLight3D
var terminal_root: Control
var menu_root: Control
var settings_root: Control
var loading_root: Control
var database_title: Label
var terminal_title: Label
var record_label: Label
var statement_label: Label
var scan_label: Label
var progress_label: Label
var risk_bar: ProgressBar
var scan_button: Button
var allow_button: Button
var deny_button: Button
var menu_start_button: Button
var menu_settings_button: Button
var menu_exit_button: Button
var settings_title_label: Label
var language_label: Label
var fullscreen_check: CheckBox
var vsync_check: CheckBox
var volume_label: Label
var shake_check: CheckBox
var back_button: Button
var language_option: OptionButton

func _ready() -> void:
    randomize()
    _load_settings()
    _build_world()
    _build_ui()
    _apply_settings()
    await _run_boot()

func _process(_delta: float) -> void:
    if main_light:
        var pulse := sin(Time.get_ticks_msec() / 83.0) * 0.06
        main_light.light_energy = 0.92 + pulse + randf_range(-0.025, 0.025)
    if camera:
        if shake_time > 0.0 and shake_enabled:
            shake_time = maxf(0.0, shake_time - _delta)
            camera.position = camera_base + Vector3(randf_range(-0.025, 0.025), randf_range(-0.018, 0.018), 0.0)
        else:
            camera.position = camera_base

func _build_world() -> void:
    var world := Node3D.new()
    world.name = "Corridor"
    add_child(world)

    camera = Camera3D.new()
    camera.position = camera_base
    camera.fov = 58.0
    world.add_child(camera)
    camera.look_at(Vector3(0.0, 1.35, -7.0), Vector3.UP)

    _box(world, Vector3(0.0, -0.18, -4.0), Vector3(5.6, 0.25, 18.0), Color(0.055, 0.065, 0.06), 0.82)
    _box(world, Vector3(-2.9, 1.35, -4.0), Vector3(0.22, 3.1, 18.0), Color(0.06, 0.085, 0.07), 0.9)
    _box(world, Vector3(2.9, 1.35, -4.0), Vector3(0.22, 3.1, 18.0), Color(0.06, 0.085, 0.07), 0.9)
    _box(world, Vector3(0.0, 2.95, -4.0), Vector3(5.8, 0.18, 18.0), Color(0.035, 0.045, 0.04), 0.92)

    for z in [-1.5, -4.5, -7.5, -10.5]:
        _box(world, Vector3(0.0, 2.72, z), Vector3(3.1, 0.08, 0.14), Color(0.22, 0.34, 0.27), 0.45)

    _box(world, Vector3(0.0, 1.25, -12.3), Vector3(2.4, 2.5, 0.22), Color(0.03, 0.05, 0.04), 0.86)
    _box(world, Vector3(0.0, 2.12, -12.15), Vector3(1.15, 0.06, 0.08), Color(0.22, 0.55, 0.35), 0.25)

    main_light = OmniLight3D.new()
    main_light.position = Vector3(0.0, 2.45, 0.5)
    main_light.light_color = Color(0.42, 0.82, 0.58)
    main_light.light_energy = 0.95
    main_light.omni_range = 10.0
    main_light.shadow_enabled = true
    world.add_child(main_light)

    var far_light := OmniLight3D.new()
    far_light.position = Vector3(0.0, 2.2, -9.0)
    far_light.light_color = Color(0.18, 0.38, 0.27)
    far_light.light_energy = 0.6
    far_light.omni_range = 7.0
    far_light.shadow_enabled = true
    world.add_child(far_light)

func _box(parent: Node, pos: Vector3, size: Vector3, color: Color, roughness: float) -> void:
    var node := MeshInstance3D.new()
    var mesh := BoxMesh.new()
    mesh.size = size
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.roughness = roughness
    mesh.material = material
    node.mesh = mesh
    node.position = pos
    parent.add_child(node)

func _build_ui() -> void:
    var canvas := CanvasLayer.new()
    canvas.layer = 10
    add_child(canvas)

    var tint := ColorRect.new()
    tint.color = Color(0.01, 0.035, 0.025, 0.36)
    tint.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    tint.mouse_filter = Control.MOUSE_FILTER_IGNORE
    canvas.add_child(tint)

    terminal_root = Control.new()
    terminal_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    terminal_root.visible = false
    canvas.add_child(terminal_root)
    _build_terminal(terminal_root)

    menu_root = ColorRect.new()
    menu_root.color = Color(0.01, 0.025, 0.018, 0.73)
    menu_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    menu_root.visible = false
    canvas.add_child(menu_root)
    _build_menu(menu_root)

    settings_root = ColorRect.new()
    settings_root.color = Color(0.005, 0.016, 0.012, 0.94)
    settings_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    settings_root.visible = false
    canvas.add_child(settings_root)
    _build_settings(settings_root)

    loading_root = ColorRect.new()
    loading_root.color = Color(0.004, 0.01, 0.008, 1.0)
    loading_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    canvas.add_child(loading_root)
    _build_loading(loading_root)

func _build_loading(root: Control) -> void:
    var center := VBoxContainer.new()
    center.anchor_left = 0.24
    center.anchor_right = 0.76
    center.anchor_top = 0.28
    center.anchor_bottom = 0.72
    center.alignment = BoxContainer.ALIGNMENT_CENTER
    center.add_theme_constant_override("separation", 10)
    root.add_child(center)

    var company := Label.new()
    company.text = "WLzar Company"
    company.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    company.add_theme_font_size_override("font_size", 18)
    company.add_theme_color_override("font_color", Color(0.55, 0.72, 0.61))
    center.add_child(company)

    var line := HSeparator.new()
    center.add_child(line)

    var title := Label.new()
    title.text = "NIGHT PROTOCOL"
    title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    title.add_theme_font_size_override("font_size", 34)
    title.add_theme_color_override("font_color", Color(0.75, 0.96, 0.82))
    center.add_child(title)

    var sub := Label.new()
    sub.text = "INCIDENT CONTROL SYSTEM // v" + VERSION
    sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    sub.add_theme_font_size_override("font_size", 10)
    sub.add_theme_color_override("font_color", Color(0.35, 0.56, 0.43))
    center.add_child(sub)

    var progress := ProgressBar.new()
    progress.name = "BootProgress"
    progress.min_value = 0
    progress.max_value = 100
    progress.value = 0
    progress.show_percentage = false
    center.add_child(progress)

    var phase := Label.new()
    phase.name = "BootPhase"
    phase.text = "INITIALIZING..."
    phase.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    phase.add_theme_font_size_override("font_size", 10)
    phase.add_theme_color_override("font_color", Color(0.42, 0.7, 0.52))
    center.add_child(phase)

func _run_boot() -> void:
    var progress: ProgressBar = loading_root.get_node("VBoxContainer/BootProgress") if loading_root.has_node("VBoxContainer/BootProgress") else _find_named(loading_root, "BootProgress")
    var phase: Label = _find_named(loading_root, "BootPhase")
    var phases := ["BOOTING INCIDENT CORE", "VERIFYING PERSONNEL CACHE", "RESTORING CAMERA LINK", "SEALING ARCHIVE DOOR", "READY"]
    for i in range(101):
        if progress:
            progress.value = i
        if phase:
            phase.text = phases[min(i / 20, phases.size() - 1)] + "  " + str(i) + "%"
        await get_tree().create_timer(0.045).timeout
    var tween := create_tween()
    tween.tween_property(loading_root, "modulate:a", 0.0, 0.45)
    await tween.finished
    loading_root.visible = false
    menu_root.visible = true
    _refresh_texts()

func _find_named(node: Node, wanted: String) -> Node:
    if node.name == wanted:
        return node
    for child in node.get_children():
        var result := _find_named(child, wanted)
        if result:
            return result
    return null

func _build_menu(root: Control) -> void:
    var card := VBoxContainer.new()
    card.anchor_left = 0.33
    card.anchor_right = 0.67
    card.anchor_top = 0.22
    card.anchor_bottom = 0.8
    card.alignment = BoxContainer.ALIGNMENT_CENTER
    card.add_theme_constant_override("separation", 9)
    root.add_child(card)

    var company := Label.new()
    company.text = "WLzar Company"
    company.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    company.add_theme_font_size_override("font_size", 12)
    company.add_theme_color_override("font_color", Color(0.43, 0.63, 0.49))
    card.add_child(company)

    var title := Label.new()
    title.text = "NIGHT PROTOCOL"
    title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    title.add_theme_font_size_override("font_size", 30)
    title.add_theme_color_override("font_color", Color(0.74, 0.95, 0.8))
    card.add_child(title)

    var version := Label.new()
    version.text = "ALPHA " + VERSION
    version.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    version.add_theme_font_size_override("font_size", 9)
    version.add_theme_color_override("font_color", Color(0.34, 0.52, 0.4))
    card.add_child(version)

    menu_start_button = _button(card, "", Callable(self, "_start_shift"))
    menu_settings_button = _button(card, "", Callable(self, "_open_settings"))
    menu_exit_button = _button(card, "", Callable(self, "_quit_game"))

func _build_terminal(root: Control) -> void:
    var top := ColorRect.new()
    top.color = Color(0.015, 0.04, 0.028, 0.9)
    top.anchor_right = 1.0
    top.offset_bottom = 30
    root.add_child(top)

    progress_label = Label.new()
    progress_label.position = Vector2(12, 7)
    progress_label.add_theme_font_size_override("font_size", 10)
    progress_label.add_theme_color_override("font_color", Color(0.49, 0.76, 0.57))
    top.add_child(progress_label)

    risk_bar = ProgressBar.new()
    risk_bar.min_value = 0
    risk_bar.max_value = 100
    risk_bar.show_percentage = false
    risk_bar.anchor_left = 0.72
    risk_bar.anchor_right = 0.98
    risk_bar.offset_top = 8
    risk_bar.offset_bottom = 21
    top.add_child(risk_bar)

    var left := PanelContainer.new()
    left.anchor_left = 0.05
    left.anchor_right = 0.47
    left.anchor_top = 0.16
    left.anchor_bottom = 0.82
    left.add_theme_stylebox_override("panel", _panel_style())
    root.add_child(left)

    var lm := MarginContainer.new()
    lm.add_theme_constant_override("margin_left", 12)
    lm.add_theme_constant_override("margin_right", 12)
    lm.add_theme_constant_override("margin_top", 10)
    lm.add_theme_constant_override("margin_bottom", 10)
    left.add_child(lm)

    var lv := VBoxContainer.new()
    lv.add_theme_constant_override("separation", 7)
    lm.add_child(lv)

    database_title = _label(lv, "", 11, Color(0.45, 0.78, 0.56))
    record_label = _label(lv, "", 15, Color(0.8, 0.93, 0.83))
    record_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    statement_label = _label(lv, "", 11, Color(0.56, 0.73, 0.62))
    statement_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

    var right := PanelContainer.new()
    right.anchor_left = 0.53
    right.anchor_right = 0.95
    right.anchor_top = 0.16
    right.anchor_bottom = 0.82
    right.add_theme_stylebox_override("panel", _panel_style())
    root.add_child(right)

    var rm := MarginContainer.new()
    rm.add_theme_constant_override("margin_left", 12)
    rm.add_theme_constant_override("margin_right", 12)
    rm.add_theme_constant_override("margin_top", 10)
    rm.add_theme_constant_override("margin_bottom", 10)
    right.add_child(rm)

    var rv := VBoxContainer.new()
    rv.add_theme_constant_override("separation", 8)
    rm.add_child(rv)

    terminal_title = _label(rv, "", 14, Color(0.72, 0.94, 0.78))
    scan_label = _label(rv, "", 10, Color(0.45, 0.7, 0.53))
    scan_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    scan_button = _button(rv, "", Callable(self, "_run_scan"))
    allow_button = _button(rv, "", Callable(self, "_authorize"))
    deny_button = _button(rv, "", Callable(self, "_deny"))

    var hint := Label.new()
    hint.name = "ControlsHint"
    hint.anchor_left = 0.05
    hint.anchor_right = 0.95
    hint.anchor_top = 0.87
    hint.anchor_bottom = 0.96
    hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    hint.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    hint.add_theme_font_size_override("font_size", 9)
    hint.add_theme_color_override("font_color", Color(0.32, 0.54, 0.4))
    root.add_child(hint)

func _build_settings(root: Control) -> void:
    var card := VBoxContainer.new()
    card.anchor_left = 0.28
    card.anchor_right = 0.72
    card.anchor_top = 0.13
    card.anchor_bottom = 0.87
    card.add_theme_constant_override("separation", 8)
    root.add_child(card)

    settings_title_label = _label(card, "", 20, Color(0.72, 0.94, 0.78))
    settings_title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

    var lang_row := HBoxContainer.new()
    card.add_child(lang_row)
    language_label = _label(lang_row, "", 11, Color(0.54, 0.76, 0.6))
    language_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    language_option = OptionButton.new()
    language_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    for language_name in LANGUAGE_NAMES:
        language_option.add_item(language_name)
    language_option.selected = maxi(0, LANGUAGE_CODES.find(language_code))
    language_option.item_selected.connect(_on_language_selected)
    lang_row.add_child(language_option)

    fullscreen_check = CheckBox.new()
    fullscreen_check.toggled.connect(_on_fullscreen_toggled)
    card.add_child(fullscreen_check)

    vsync_check = CheckBox.new()
    vsync_check.toggled.connect(_on_vsync_toggled)
    card.add_child(vsync_check)

    volume_label = _label(card, "", 11, Color(0.54, 0.76, 0.6))
    var volume_slider := HSlider.new()
    volume_slider.name = "VolumeSlider"
    volume_slider.min_value = 0.0
    volume_slider.max_value = 1.0
    volume_slider.step = 0.05
    volume_slider.value = 0.8
    volume_slider.value_changed.connect(_on_volume_changed)
    card.add_child(volume_slider)

    shake_check = CheckBox.new()
    shake_check.button_pressed = shake_enabled
    shake_check.toggled.connect(_on_shake_toggled)
    card.add_child(shake_check)

    back_button = _button(card, "", Callable(self, "_close_settings"))

func _label(parent: Node, text_value: String, font_size: int, color: Color) -> Label:
    var label := Label.new()
    label.text = text_value
    label.add_theme_font_size_override("font_size", font_size)
    label.add_theme_color_override("font_color", color)
    parent.add_child(label)
    return label

func _button(parent: Node, text_value: String, callback: Callable) -> Button:
    var button := Button.new()
    button.text = text_value
    button.custom_minimum_size = Vector2(0, 32)
    button.add_theme_font_size_override("font_size", 11)
    button.add_theme_color_override("font_color", Color(0.68, 0.9, 0.75))
    button.add_theme_color_override("font_hover_color", Color(0.9, 1.0, 0.93))
    button.add_theme_stylebox_override("normal", _button_style(Color(0.03, 0.085, 0.055, 0.92)))
    button.add_theme_stylebox_override("hover", _button_style(Color(0.055, 0.15, 0.09, 0.96)))
    button.add_theme_stylebox_override("pressed", _button_style(Color(0.02, 0.06, 0.04, 1.0)))
    button.pressed.connect(callback)
    parent.add_child(button)
    return button

func _panel_style() -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = Color(0.018, 0.055, 0.037, 0.9)
    style.border_color = Color(0.18, 0.42, 0.26, 0.9)
    style.set_border_width_all(1)
    style.set_corner_radius_all(4)
    return style

func _button_style(color: Color) -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = color
    style.border_color = Color(0.18, 0.42, 0.26, 0.8)
    style.set_border_width_all(1)
    style.set_corner_radius_all(3)
    return style

func _start_shift() -> void:
    current = 0
    score = 0
    risk = 0
    scan_used = false
    menu_root.visible = false
    settings_root.visible = false
    terminal_root.visible = true
    _show_visitor()

func _show_visitor() -> void:
    if current >= visitors.size():
        _show_ending()
        return
    var v: Dictionary = visitors[current]
    record_label.text = _t("record") + "\n\n" + v["name"] + "\nID: " + v["id"] + "\nDIVISION: " + v["division"]
    var statements: Dictionary = v["statement"]
    statement_label.text = _t("statement") + "\n\n" + str(statements.get(language_code, statements.get("en", "")))
    terminal_title.text = _t("terminal") + "\n" + _t("visitor") + " " + str(current + 1).pad_zeros(2) + " / " + str(visitors.size()).pad_zeros(2)
    scan_label.text = "..."
    scan_used = false
    scan_button.disabled = false
    allow_button.disabled = false
    deny_button.disabled = false
    _update_status()

func _run_scan() -> void:
    if current >= visitors.size() or scan_used:
        return
    scan_used = true
    scan_button.disabled = true
    risk = mini(100, risk + 8)
    scan_label.text = "SCANNING..."
    _update_status()
    await get_tree().create_timer(0.75).timeout
    var v: Dictionary = visitors[current]
    scan_label.text = _t("scan_alert") if bool(v["anomaly"]) else _t("scan_clean")
    if bool(v["anomaly"]):
        shake_time = 0.18

func _authorize() -> void:
    _decide(true)

func _deny() -> void:
    _decide(false)

func _decide(allow_entry: bool) -> void:
    if current >= visitors.size():
        _start_shift()
        return
    var v: Dictionary = visitors[current]
    if allow_entry == bool(v["allow"]):
        score += 1
        risk = mini(100, risk + 3)
    else:
        risk = mini(100, risk + 22)
        shake_time = 0.35
    current += 1
    _show_visitor()

func _show_ending() -> void:
    scan_button.disabled = true
    allow_button.disabled = true
    deny_button.disabled = true
    scan_button.text = _t("new_shift")
    scan_button.disabled = false
    if score >= 5 and risk < 60:
        statement_label.text = _t("good")
        scan_label.text = "RESULT: " + str(score) + "/6"
    elif risk >= 85 or score <= 2:
        statement_label.text = _t("bad")
        scan_label.text = "RESULT: " + str(score) + "/6"
        shake_time = 1.0
    else:
        statement_label.text = _t("mid")
        scan_label.text = "RESULT: " + str(score) + "/6"
    record_label.text = "SHIFT CLOSED\n\nOPERATOR DECISIONS: " + str(score) + "/6"
    terminal_title.text = "NIGHT PROTOCOL // END OF SHIFT"
    scan_button.pressed.disconnect(Callable(self, "_run_scan")) if scan_button.pressed.is_connected(Callable(self, "_run_scan")) else null
    if not scan_button.pressed.is_connected(Callable(self, "_start_shift")):
        scan_button.pressed.connect(Callable(self, "_start_shift"))
    _update_status()

func _update_status() -> void:
    progress_label.text = _t("shift") + " 01  //  " + str(mini(current + 1, visitors.size())) + "/" + str(visitors.size()) + "  //  " + _t("risk") + " " + str(risk) + "%"
    risk_bar.value = risk

func _open_settings() -> void:
    settings_root.visible = true
    menu_root.visible = false
    _refresh_texts()

func _close_settings() -> void:
    settings_root.visible = false
    menu_root.visible = true
    _save_settings()

func _quit_game() -> void:
    get_tree().quit()

func _on_language_selected(index: int) -> void:
    language_code = LANGUAGE_CODES[clampi(index, 0, LANGUAGE_CODES.size() - 1)]
    _refresh_texts()
    _save_settings()

func _on_fullscreen_toggled(enabled: bool) -> void:
    DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if enabled else DisplayServer.WINDOW_MODE_WINDOWED)
    _save_settings()

func _on_vsync_toggled(enabled: bool) -> void:
    DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if enabled else DisplayServer.VSYNC_DISABLED)
    _save_settings()

func _on_volume_changed(value: float) -> void:
    AudioServer.set_bus_volume_db(0, linear_to_db(maxf(value, 0.001)))
    _save_settings()

func _on_shake_toggled(enabled: bool) -> void:
    shake_enabled = enabled
    _save_settings()

func _apply_settings() -> void:
    var cfg := ConfigFile.new()
    cfg.load("user://night_protocol.cfg")
    var fullscreen := bool(cfg.get_value("video", "fullscreen", false))
    var vsync := bool(cfg.get_value("video", "vsync", true))
    var volume := float(cfg.get_value("audio", "volume", 0.8))
    shake_enabled = bool(cfg.get_value("gameplay", "shake", true))
    if fullscreen_check:
        fullscreen_check.button_pressed = fullscreen
    if vsync_check:
        vsync_check.button_pressed = vsync
    if shake_check:
        shake_check.button_pressed = shake_enabled
    var slider: HSlider = _find_named(settings_root, "VolumeSlider")
    if slider:
        slider.value = volume
    DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if fullscreen else DisplayServer.WINDOW_MODE_WINDOWED)
    DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if vsync else DisplayServer.VSYNC_DISABLED)
    AudioServer.set_bus_volume_db(0, linear_to_db(maxf(volume, 0.001)))

func _load_settings() -> void:
    var cfg := ConfigFile.new()
    if cfg.load("user://night_protocol.cfg") == OK:
        language_code = str(cfg.get_value("general", "language", "en"))
        shake_enabled = bool(cfg.get_value("gameplay", "shake", true))
    if not LANGUAGE_CODES.has(language_code):
        language_code = "en"

func _save_settings() -> void:
    var cfg := ConfigFile.new()
    cfg.set_value("general", "language", language_code)
    cfg.set_value("video", "fullscreen", DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN)
    cfg.set_value("video", "vsync", DisplayServer.window_get_vsync_mode() != DisplayServer.VSYNC_DISABLED)
    var slider: HSlider = _find_named(settings_root, "VolumeSlider")
    cfg.set_value("audio", "volume", slider.value if slider else 0.8)
    cfg.set_value("gameplay", "shake", shake_enabled)
    cfg.save("user://night_protocol.cfg")

func _t(key: String) -> String:
    var lang: Dictionary = STRINGS.get(language_code, STRINGS["en"])
    return str(lang.get(key, STRINGS["en"].get(key, key)))

func _refresh_texts() -> void:
    if menu_start_button:
        menu_start_button.text = _t("start")
        menu_settings_button.text = _t("settings")
        menu_exit_button.text = _t("exit")
    if settings_title_label:
        settings_title_label.text = _t("settings_title")
        language_label.text = _t("language")
        fullscreen_check.text = _t("fullscreen")
        vsync_check.text = _t("vsync")
        volume_label.text = _t("volume")
        shake_check.text = _t("shake")
        back_button.text = _t("back")
        language_option.selected = maxi(0, LANGUAGE_CODES.find(language_code))
    if database_title:
        database_title.text = _t("database")
        scan_button.text = _t("scan")
        allow_button.text = _t("allow")
        deny_button.text = _t("deny")
        var hint: Label = _find_named(terminal_root, "ControlsHint")
        if hint:
            hint.text = _t("controls")
        if terminal_root.visible and current < visitors.size():
            _show_visitor()

func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
        if event.keycode == KEY_ESCAPE:
            if settings_root.visible:
                _close_settings()
            elif terminal_root.visible:
                terminal_root.visible = false
                menu_root.visible = true
            elif menu_root.visible:
                _quit_game()
            return
        if terminal_root.visible and not settings_root.visible:
            if event.keycode == KEY_1:
                _run_scan()
            elif event.keycode == KEY_2:
                _authorize()
            elif event.keycode == KEY_3:
                _deny()
