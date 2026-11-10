extends Node

const VERSION := "0.1.0"
const MANIFEST_URL := "https://raw.githubusercontent.com/apelsina849-lgtm/fgwg/night-protocol-release/manifest.json"
const UPDATE_ZIP := "user://night_protocol_update.zip"

var status_label: Label
var play_button: Button
var update_button: Button
var progress: ProgressBar
var manifest_request: HTTPRequest
var download_request: HTTPRequest
var remote_manifest: Dictionary = {}

func _ready() -> void:
    _build_ui()
    manifest_request = HTTPRequest.new()
    manifest_request.timeout = 12.0
    manifest_request.request_completed.connect(_on_manifest_completed)
    add_child(manifest_request)

    download_request = HTTPRequest.new()
    download_request.timeout = 180.0
    download_request.download_file = UPDATE_ZIP
    download_request.request_completed.connect(_on_download_completed)
    add_child(download_request)

    await get_tree().create_timer(0.7).timeout
    _check_update(false)

func _build_ui() -> void:
    var canvas := CanvasLayer.new()
    add_child(canvas)

    var bg := ColorRect.new()
    bg.color = Color(0.012, 0.026, 0.02, 1.0)
    bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    canvas.add_child(bg)

    var header := ColorRect.new()
    header.color = Color(0.02, 0.055, 0.038, 1.0)
    header.anchor_right = 1.0
    header.offset_bottom = 48
    canvas.add_child(header)

    var company := Label.new()
    company.text = "WLzar Company"
    company.position = Vector2(22, 13)
    company.add_theme_font_size_override("font_size", 16)
    company.add_theme_color_override("font_color", Color(0.62, 0.86, 0.69))
    header.add_child(company)

    var version := Label.new()
    version.text = "LAUNCHER " + VERSION
    version.anchor_left = 0.82
    version.anchor_right = 0.98
    version.offset_top = 16
    version.offset_bottom = 38
    version.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    version.add_theme_font_size_override("font_size", 10)
    version.add_theme_color_override("font_color", Color(0.34, 0.57, 0.42))
    header.add_child(version)

    var preview_panel := PanelContainer.new()
    preview_panel.anchor_left = 0.045
    preview_panel.anchor_right = 0.62
    preview_panel.anchor_top = 0.13
    preview_panel.anchor_bottom = 0.82
    preview_panel.add_theme_stylebox_override("panel", _panel_style(Color(0.015, 0.04, 0.029, 1.0)))
    canvas.add_child(preview_panel)

    var preview_margin := MarginContainer.new()
    preview_margin.add_theme_constant_override("margin_left", 8)
    preview_margin.add_theme_constant_override("margin_right", 8)
    preview_margin.add_theme_constant_override("margin_top", 8)
    preview_margin.add_theme_constant_override("margin_bottom", 8)
    preview_panel.add_child(preview_margin)

    var preview := TextureRect.new()
    preview.texture = load("res://assets/preview.svg")
    preview.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
    preview.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
    preview_margin.add_child(preview)

    var info := VBoxContainer.new()
    info.anchor_left = 0.66
    info.anchor_right = 0.955
    info.anchor_top = 0.13
    info.anchor_bottom = 0.82
    info.add_theme_constant_override("separation", 9)
    canvas.add_child(info)

    var title := Label.new()
    title.text = "NIGHT\nPROTOCOL"
    title.add_theme_font_size_override("font_size", 31)
    title.add_theme_color_override("font_color", Color(0.72, 0.95, 0.79))
    info.add_child(title)

    var build := Label.new()
    build.text = "ALPHA " + VERSION + "  //  WINDOWS x64"
    build.add_theme_font_size_override("font_size", 10)
    build.add_theme_color_override("font_color", Color(0.36, 0.61, 0.45))
    info.add_child(build)

    var description := Label.new()
    description.text = "Incident control horror.\nSix visitors. One sealed archive.\nTrust the terminal — until it lies."
    description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    description.add_theme_font_size_override("font_size", 11)
    description.add_theme_color_override("font_color", Color(0.55, 0.72, 0.61))
    info.add_child(description)

    var spacer := Control.new()
    spacer.custom_minimum_size = Vector2(0, 18)
    info.add_child(spacer)

    play_button = _button(info, "PLAY", Callable(self, "_play"))
    update_button = _button(info, "CHECK FOR UPDATE", Callable(self, "_check_update").bind(true))
    _button(info, "VERIFY GAME", Callable(self, "_verify_game"))
    _button(info, "OPEN GAME FOLDER", Callable(self, "_open_folder"))
    _button(info, "EXIT", Callable(self, "_exit"))

    progress = ProgressBar.new()
    progress.min_value = 0
    progress.max_value = 100
    progress.value = 0
    progress.show_percentage = false
    progress.visible = false
    info.add_child(progress)

    status_label = Label.new()
    status_label.text = "READY"
    status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    status_label.add_theme_font_size_override("font_size", 9)
    status_label.add_theme_color_override("font_color", Color(0.42, 0.68, 0.5))
    info.add_child(status_label)

    var footer := Label.new()
    footer.text = "Preview: INCIDENT TERMINAL / MARA VOSS    •    Update channel: ALPHA"
    footer.anchor_left = 0.045
    footer.anchor_right = 0.955
    footer.anchor_top = 0.87
    footer.anchor_bottom = 0.94
    footer.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    footer.add_theme_font_size_override("font_size", 9)
    footer.add_theme_color_override("font_color", Color(0.26, 0.46, 0.34))
    canvas.add_child(footer)

func _panel_style(color: Color) -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = color
    style.border_color = Color(0.16, 0.4, 0.25, 0.9)
    style.set_border_width_all(1)
    style.set_corner_radius_all(5)
    return style

func _button(parent: Node, title: String, callback: Callable) -> Button:
    var button := Button.new()
    button.text = title
    button.custom_minimum_size = Vector2(0, 40)
    button.add_theme_font_size_override("font_size", 12)
    button.add_theme_color_override("font_color", Color(0.68, 0.9, 0.75))
    button.add_theme_color_override("font_hover_color", Color(0.9, 1.0, 0.92))
    button.add_theme_stylebox_override("normal", _button_style(Color(0.025, 0.075, 0.05, 1.0)))
    button.add_theme_stylebox_override("hover", _button_style(Color(0.05, 0.14, 0.085, 1.0)))
    button.add_theme_stylebox_override("pressed", _button_style(Color(0.015, 0.05, 0.033, 1.0)))
    button.pressed.connect(callback)
    parent.add_child(button)
    return button

func _button_style(color: Color) -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = color
    style.border_color = Color(0.17, 0.43, 0.27, 0.95)
    style.set_border_width_all(1)
    style.set_corner_radius_all(3)
    return style

func _base_dir() -> String:
    return OS.get_executable_path().get_base_dir()

func _game_path() -> String:
    return _base_dir().path_join("game").path_join("NIGHT_PROTOCOL.exe")

func _play() -> void:
    var game := _game_path()
    if not FileAccess.file_exists(game):
        status_label.text = "GAME FILE MISSING. Use CHECK FOR UPDATE to repair."
        return
    status_label.text = "LAUNCHING NIGHT PROTOCOL..."
    var pid := OS.create_process(game, PackedStringArray())
    if pid <= 0:
        status_label.text = "FAILED TO START GAME. Try VERIFY GAME."
    else:
        await get_tree().create_timer(0.4).timeout
        get_tree().quit()

func _verify_game() -> void:
    var game := _game_path()
    if FileAccess.file_exists(game):
        var file := FileAccess.open(game, FileAccess.READ)
        var bytes := file.get_length() if file else 0
        if bytes > 1000000:
            status_label.text = "GAME VERIFIED // " + _human_size(bytes)
        else:
            status_label.text = "GAME FILE LOOKS INCOMPLETE. Run update."
    else:
        status_label.text = "GAME NOT INSTALLED. Run update."

func _check_update(show_current: bool = true) -> void:
    if manifest_request.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
        return
    status_label.text = "CONTACTING UPDATE CHANNEL..."
    update_button.disabled = true
    var error := manifest_request.request(MANIFEST_URL)
    if error != OK:
        update_button.disabled = false
        status_label.text = "UPDATE SERVER UNAVAILABLE. You can still play offline."

func _on_manifest_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    update_button.disabled = false
    if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
        status_label.text = "UPDATE CHECK FAILED. Offline play is available."
        return
    var parsed = JSON.parse_string(body.get_string_from_utf8())
    if typeof(parsed) != TYPE_DICTIONARY:
        status_label.text = "INVALID UPDATE MANIFEST."
        return
    remote_manifest = parsed
    var remote_version := str(remote_manifest.get("version", VERSION))
    if _version_newer(remote_version, VERSION) or not FileAccess.file_exists(_game_path()):
        status_label.text = "UPDATE " + remote_version + " AVAILABLE."
        _download_update()
    else:
        status_label.text = "UP TO DATE // " + VERSION

func _download_update() -> void:
    var url := str(remote_manifest.get("url", ""))
    if url.is_empty():
        status_label.text = "UPDATE URL MISSING."
        return
    progress.visible = true
    progress.value = 8
    play_button.disabled = true
    update_button.disabled = true
    status_label.text = "DOWNLOADING UPDATE..."
    download_request.download_file = UPDATE_ZIP
    var error := download_request.request(url)
    if error != OK:
        progress.visible = false
        play_button.disabled = false
        update_button.disabled = false
        status_label.text = "DOWNLOAD COULD NOT START."

func _on_download_completed(result: int, response_code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
    if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
        progress.visible = false
        play_button.disabled = false
        update_button.disabled = false
        status_label.text = "UPDATE DOWNLOAD FAILED."
        return
    progress.value = 65
    status_label.text = "INSTALLING UPDATE..."
    await get_tree().process_frame
    var ok := _extract_update()
    progress.value = 100 if ok else 0
    progress.visible = not ok
    play_button.disabled = false
    update_button.disabled = false
    status_label.text = "UPDATE INSTALLED. READY TO PLAY." if ok else "UPDATE INSTALL FAILED. Check folder permissions."

func _extract_update() -> bool:
    var zip := ZIPReader.new()
    var zip_path := ProjectSettings.globalize_path(UPDATE_ZIP)
    if zip.open(zip_path) != OK:
        return false
    var base := _base_dir()
    for entry in zip.get_files():
        var safe := entry.replace("\\", "/")
        if safe.contains("..") or safe.begins_with("/"):
            continue
        var target := base.path_join(safe)
        if safe.ends_with("/"):
            DirAccess.make_dir_recursive_absolute(target)
            continue
        DirAccess.make_dir_recursive_absolute(target.get_base_dir())
        var output := FileAccess.open(target, FileAccess.WRITE)
        if output == null:
            zip.close()
            return false
        output.store_buffer(zip.read_file(entry))
        output.close()
    zip.close()
    DirAccess.remove_absolute(zip_path)
    return FileAccess.file_exists(_game_path())

func _version_newer(remote: String, local: String) -> bool:
    var r := remote.split(".")
    var l := local.split(".")
    for i in range(3):
        var rv := int(r[i]) if i < r.size() else 0
        var lv := int(l[i]) if i < l.size() else 0
        if rv > lv:
            return true
        if rv < lv:
            return false
    return false

func _human_size(bytes: int) -> String:
    if bytes > 1024 * 1024:
        return "%.1f MB" % (float(bytes) / 1024.0 / 1024.0)
    if bytes > 1024:
        return "%.1f KB" % (float(bytes) / 1024.0)
    return str(bytes) + " B"

func _open_folder() -> void:
    OS.shell_open(_base_dir())

func _exit() -> void:
    get_tree().quit()
