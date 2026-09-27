#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::ffi::OsStr;
use std::fs::{self, OpenOptions};
use std::io::{Cursor, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Mutex,
};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

#[cfg(windows)]
use std::os::windows::ffi::OsStrExt;
#[cfg(windows)]
use windows_sys::Win32::Storage::FileSystem::{
    MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
};

use quick_xml::events::Event;
use quick_xml::Reader;
use serde::{Deserialize, Serialize};
use tauri::{
    AppHandle, Emitter, Manager, State, WebviewUrl, WebviewWindowBuilder, Window, WindowEvent,
};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use zip::ZipArchive;

const SIDECAR_NAME: &str = "agent-audit-sidecar";
const SIDECAR_HOST: &str = "127.0.0.1";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(30);
const PROBE_TIMEOUT: Duration = Duration::from_millis(600);
const MAX_DOCUMENT_IMPORT_ITEMS: usize = 50;
const MAX_DOCUMENT_SOURCE_BYTES: u64 = 20 * 1024 * 1024;
const MAX_DOCUMENT_TEXT_BYTES: usize = 2 * 1024 * 1024;
const MAX_DOCX_XML_BYTES: usize = 16 * 1024 * 1024;
const MAX_WORKSPACE_BACKUP_BYTES: u64 = 128 * 1024 * 1024;
const MAX_DIAGNOSTICS_ARCHIVE_BYTES: usize = 16 * 1024 * 1024;
const ACTIVE_WORKSPACE_FILENAME: &str = "active-workspace.json";
const WORKSPACE_DIRECTORY_NAME: &str = "workspaces";
const PROVIDER_CREDENTIAL_SERVICE: &str = "com.agent-audit.desktop";
const PROVIDER_CREDENTIAL_ACCOUNT: &str = "active-provider-api-key";
const PROVIDER_SECRET_ENV: &str = "AGENT_AUDIT_PROVIDER_API_KEY";

#[cfg(windows)]
const APP_DIRECTORY_NAME: &str = "AgentAudit";
#[cfg(not(windows))]
const APP_DIRECTORY_NAME: &str = "agent-audit";

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DocumentImportSource {
    source_id: String,
    display_name: String,
    relative_path: String,
    extension: String,
    size_bytes: u64,
    content: Option<String>,
    diagnostic: Option<String>,
    status: Option<String>,
    diagnostic_code: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SidecarLifecycleFile {
    status: String,
    host: String,
    port: Option<u16>,
    detail: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopRuntimeStatus {
    pub state: String,
    pub api_base: Option<String>,
    pub port: Option<u16>,
    pub process_id: Option<u32>,
    pub message: Option<String>,
}

impl DesktopRuntimeStatus {
    fn launching() -> Self {
        Self {
            state: "starting".to_string(),
            api_base: None,
            port: None,
            process_id: None,
            message: None,
        }
    }

    fn starting(port: u16) -> Self {
        Self {
            state: "starting".to_string(),
            api_base: None,
            port: Some(port),
            process_id: None,
            message: None,
        }
    }

    fn stopped() -> Self {
        Self {
            state: "stopped".to_string(),
            api_base: None,
            port: None,
            process_id: None,
            message: None,
        }
    }
}

#[derive(Debug)]
struct SidecarState {
    child: Mutex<Option<CommandChild>>,
    process_id: Mutex<Option<u32>>,
    status: Mutex<DesktopRuntimeStatus>,
    stderr: Mutex<String>,
    failure_reported: Mutex<bool>,
    credential_lock: Mutex<()>,
    shutdown_started: AtomicBool,
}

impl Default for SidecarState {
    fn default() -> Self {
        Self {
            child: Mutex::new(None),
            process_id: Mutex::new(None),
            // WebViews may begin loading before Tauri's setup hook runs. The
            // process is launching from construction onward; only an explicit
            // shutdown transitions this state to `stopped`.
            status: Mutex::new(DesktopRuntimeStatus::launching()),
            stderr: Mutex::new(String::new()),
            failure_reported: Mutex::new(false),
            credential_lock: Mutex::new(()),
            shutdown_started: AtomicBool::new(false),
        }
    }
}

#[derive(Debug)]
enum ProviderSecretLookup {
    Present(String),
    Missing,
    Unavailable,
}

#[cfg(any(windows, target_os = "linux"))]
fn read_provider_secret_from_store() -> ProviderSecretLookup {
    let entry = match keyring::Entry::new(PROVIDER_CREDENTIAL_SERVICE, PROVIDER_CREDENTIAL_ACCOUNT)
    {
        Ok(entry) => entry,
        Err(_) => return ProviderSecretLookup::Unavailable,
    };
    match entry.get_password() {
        Ok(secret) if !secret.is_empty() => ProviderSecretLookup::Present(secret),
        Ok(_) | Err(keyring::Error::NoEntry) => ProviderSecretLookup::Missing,
        Err(_) => ProviderSecretLookup::Unavailable,
    }
}

#[cfg(not(any(windows, target_os = "linux")))]
fn read_provider_secret_from_store() -> ProviderSecretLookup {
    // F-031 only promises the Windows and Linux system-store boundaries.  An
    // unsupported target must remain explicit rather than falling back to a
    // file or process-local secret cache.
    ProviderSecretLookup::Unavailable
}

#[cfg(any(windows, target_os = "linux"))]
fn write_provider_secret_to_store(secret: &str) -> Result<(), ()> {
    let entry = keyring::Entry::new(PROVIDER_CREDENTIAL_SERVICE, PROVIDER_CREDENTIAL_ACCOUNT)
        .map_err(|_| ())?;
    entry.set_password(secret).map_err(|_| ())
}

#[cfg(not(any(windows, target_os = "linux")))]
fn write_provider_secret_to_store(_secret: &str) -> Result<(), ()> {
    Err(())
}

#[cfg(any(windows, target_os = "linux"))]
fn remove_provider_secret_from_store() -> Result<(), ()> {
    let entry = keyring::Entry::new(PROVIDER_CREDENTIAL_SERVICE, PROVIDER_CREDENTIAL_ACCOUNT)
        .map_err(|_| ())?;
    match entry.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(_) => Err(()),
    }
}

#[cfg(not(any(windows, target_os = "linux")))]
fn remove_provider_secret_from_store() -> Result<(), ()> {
    Err(())
}

impl SidecarState {
    fn status(&self) -> DesktopRuntimeStatus {
        self.status
            .lock()
            .expect("sidecar status lock poisoned")
            .clone()
    }

    fn set_starting(&self, port: u16) -> bool {
        let mut status = self.status.lock().expect("sidecar status lock poisoned");
        if status.state == "stopped" {
            return false;
        }
        *status = DesktopRuntimeStatus::starting(port);
        drop(status);
        self.stderr
            .lock()
            .expect("sidecar stderr lock poisoned")
            .clear();
        true
    }

    fn set_launching(&self) {
        *self.status.lock().expect("sidecar status lock poisoned") =
            DesktopRuntimeStatus::launching();
        self.stderr
            .lock()
            .expect("sidecar stderr lock poisoned")
            .clear();
        *self
            .failure_reported
            .lock()
            .expect("sidecar failure lock poisoned") = false;
    }

    fn set_ready(&self, api_base: String, port: u16, process_id: u32) {
        *self.status.lock().expect("sidecar status lock poisoned") = DesktopRuntimeStatus {
            state: "ready".to_string(),
            api_base: Some(api_base),
            port: Some(port),
            process_id: Some(process_id),
            message: None,
        };
    }

    fn set_failed(&self, message: String) {
        let current = self.status();
        *self.status.lock().expect("sidecar status lock poisoned") = DesktopRuntimeStatus {
            state: "failed".to_string(),
            api_base: None,
            port: current.port,
            process_id: current.process_id,
            message: Some(message),
        };
    }

    fn set_stopped(&self) {
        *self.status.lock().expect("sidecar status lock poisoned") =
            DesktopRuntimeStatus::stopped();
    }

    fn append_stderr(&self, bytes: &[u8]) {
        let line = String::from_utf8_lossy(bytes);
        let mut stderr = self.stderr.lock().expect("sidecar stderr lock poisoned");
        stderr.push_str(line.trim());
        stderr.push('\n');
        if stderr.len() > 4_096 {
            let keep_from = stderr.len() - 4_096;
            stderr.drain(..keep_from);
        }
    }

    fn stderr(&self) -> String {
        self.stderr
            .lock()
            .expect("sidecar stderr lock poisoned")
            .trim()
            .to_string()
    }

    fn set_child(&self, child: CommandChild) -> u32 {
        let process_id = child.pid();
        *self
            .process_id
            .lock()
            .expect("sidecar process lock poisoned") = Some(process_id);
        *self.child.lock().expect("sidecar child lock poisoned") = Some(child);
        if let Ok(mut status) = self.status.lock() {
            status.process_id = Some(process_id);
        }
        process_id
    }

    fn clear_child_if(&self, process_id: u32) -> bool {
        let current = *self
            .process_id
            .lock()
            .expect("sidecar process lock poisoned");
        if current == Some(process_id) {
            self.child
                .lock()
                .expect("sidecar child lock poisoned")
                .take();
            *self
                .process_id
                .lock()
                .expect("sidecar process lock poisoned") = None;
            if let Ok(mut status) = self.status.lock() {
                status.process_id = None;
            }
            return true;
        }
        false
    }

    fn stop_child(&self) {
        let process_id = self
            .process_id
            .lock()
            .expect("sidecar process lock poisoned")
            .take();
        let child = self
            .child
            .lock()
            .expect("sidecar child lock poisoned")
            .take();
        self.set_stopped();
        if let Some(process_id) = process_id {
            terminate_process_tree(process_id);
        }
        if let Some(child) = child {
            let _ = child.kill();
        }
    }

    fn begin_shutdown(&self) -> bool {
        !self.shutdown_started.swap(true, Ordering::AcqRel)
    }

    fn is_failed_or_stopped(&self) -> bool {
        matches!(self.status().state.as_str(), "failed" | "stopped")
    }

    fn is_stopped(&self) -> bool {
        self.status().state == "stopped"
    }

    fn mark_failure_reported(&self) -> bool {
        let mut reported = self
            .failure_reported
            .lock()
            .expect("sidecar failure lock poisoned");
        if *reported {
            return false;
        }
        *reported = true;
        true
    }

    /// Read the active Provider credential without making keyring failures
    /// fatal to the Sidecar lifecycle.  The caller injects only `Present`; a
    /// missing or unavailable system store leaves the API running so the UI
    /// can report `credentialConfigured=false` and ask for a new value.
    fn provider_secret(&self) -> ProviderSecretLookup {
        let Ok(_guard) = self.credential_lock.lock() else {
            return ProviderSecretLookup::Unavailable;
        };
        read_provider_secret_from_store()
    }

    /// Store one Provider API Key in the platform keystore, never in app data.
    fn store_provider_secret(&self, secret: String) -> Result<(), String> {
        if secret.trim().is_empty() || secret.chars().any(|character| character.is_control()) {
            return Err("API Key 不能为空，且不能包含控制字符".to_string());
        }

        let _guard = self
            .credential_lock
            .lock()
            .map_err(|_| "系统凭据存储不可用".to_string())?;
        write_provider_secret_to_store(&secret)
            .map_err(|_| "系统凭据存储不可用，无法保存 API Key".to_string())
    }

    /// Remove the active Provider API Key from the platform keystore.
    fn delete_provider_secret(&self) -> Result<(), String> {
        let _guard = self
            .credential_lock
            .lock()
            .map_err(|_| "系统凭据存储不可用".to_string())?;
        remove_provider_secret_from_store()
            .map_err(|_| "系统凭据存储不可用，无法删除 API Key".to_string())
    }
}

/// Stop the complete process tree for a packaged Sidecar.
///
/// PyInstaller one-file executables keep a short-lived bootstrap process and
/// then run the Python payload in a child process. `CommandChild::kill()` only
/// owns the bootstrap PID, so closing just that PID can leave the API running.
/// The PID comes from the Sidecar child returned by Tauri; no user-supplied
/// command or target is involved here.
#[cfg(windows)]
fn terminate_process_tree(process_id: u32) {
    let Some(system_root) = std::env::var_os("SystemRoot") else {
        return;
    };
    let taskkill = PathBuf::from(system_root)
        .join("System32")
        .join("taskkill.exe");
    let _ = std::process::Command::new(taskkill)
        .args(["/PID", &process_id.to_string(), "/T", "/F"])
        .status();
}

#[cfg(target_os = "linux")]
fn terminate_process_tree(process_id: u32) {
    fn descendants(process_id: u32, result: &mut Vec<u32>) {
        let children_path = format!("/proc/{process_id}/task/{process_id}/children");
        let Ok(children) = fs::read_to_string(children_path) else {
            return;
        };
        for child in children
            .split_whitespace()
            .filter_map(|value| value.parse::<u32>().ok())
        {
            descendants(child, result);
            result.push(child);
        }
    }

    let mut children = Vec::new();
    descendants(process_id, &mut children);
    for child in children {
        let _ = std::process::Command::new("/bin/kill")
            .args(["-KILL", &child.to_string()])
            .status();
    }
    let _ = std::process::Command::new("/bin/kill")
        .args(["-KILL", &process_id.to_string()])
        .status();
}

#[cfg(all(not(windows), not(target_os = "linux")))]
fn terminate_process_tree(process_id: u32) {
    let _ = std::process::Command::new("kill")
        .args(["-KILL", &process_id.to_string()])
        .status();
}

#[tauri::command]
fn get_desktop_runtime_status(state: State<'_, SidecarState>) -> DesktopRuntimeStatus {
    state.status()
}

#[tauri::command]
fn get_api_base(state: State<'_, SidecarState>) -> Result<String, String> {
    let status = state.status();
    if status.state == "ready" {
        return status
            .api_base
            .ok_or_else(|| "桌面后台已就绪，但没有返回 API 地址".to_string());
    }

    Err(status
        .message
        .unwrap_or_else(|| format!("桌面后台尚未就绪（状态：{}）", status.state)))
}

/// Store a Provider API Key in the OS credential store. The command
/// returns only success/failure; the value never travels back to the WebView.
#[tauri::command]
fn store_provider_secret(state: State<'_, SidecarState>, secret: String) -> Result<(), String> {
    state.store_provider_secret(secret)
}

/// Delete the active Provider API Key from the OS credential store.
#[tauri::command]
fn delete_provider_secret(state: State<'_, SidecarState>) -> Result<(), String> {
    state.delete_provider_secret()
}

#[tauri::command]
async fn stop_sidecar(state: State<'_, SidecarState>) -> Result<(), String> {
    state.stop_child();
    Ok(())
}

#[tauri::command]
fn quit_application(app: AppHandle, state: State<'_, SidecarState>) {
    state.stop_child();
    app.exit(1);
}

/// Save the API-produced Workspace archive through the native file dialog.
/// The selected absolute path never crosses back into the renderer or API.
#[tauri::command]
async fn save_workspace_backup(
    window: Window,
    bytes: Vec<u8>,
    suggested_name: String,
) -> Result<bool, String> {
    if bytes.len() as u64 > MAX_WORKSPACE_BACKUP_BYTES {
        return Err("Workspace 备份超过 128 MiB 限制".to_string());
    }

    let mut dialog = window
        .dialog()
        .file()
        .set_title("保存 Workspace 备份")
        .add_filter("AgentAudit Workspace 备份", &["zip"]);
    if !suggested_name.trim().is_empty() {
        dialog = dialog.set_file_name(suggested_name.trim());
    }
    let Some(selected) = dialog.blocking_save_file() else {
        return Ok(false);
    };
    let path = selected
        .into_path()
        .map_err(|_| "备份保存位置不可用".to_string())?;
    fs::write(&path, bytes).map_err(|error| format!("无法保存 Workspace 备份：{error}"))?;
    Ok(true)
}

fn validated_diagnostics_filename(suggested_name: &str) -> Result<&str, String> {
    let name = suggested_name.trim();
    if name.is_empty()
        || name.chars().any(char::is_control)
        || Path::new(name).file_name() != Some(OsStr::new(name))
        || !Path::new(name)
            .extension()
            .and_then(OsStr::to_str)
            .is_some_and(|extension| extension.eq_ignore_ascii_case("zip"))
    {
        return Err("诊断包建议文件名必须是不含路径的 .zip 文件名".to_string());
    }
    Ok(name)
}

fn write_new_diagnostics_archive(target: &Path, bytes: &[u8]) -> Result<(), String> {
    if target.exists() {
        return Err("所选文件已存在，请换一个新文件名".to_string());
    }
    let parent = target
        .parent()
        .filter(|parent| parent.is_dir())
        .ok_or_else(|| "诊断包保存目录不可用".to_string())?;
    let target_name = target
        .file_name()
        .and_then(OsStr::to_str)
        .ok_or_else(|| "诊断包保存文件名不可用".to_string())?;
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "无法创建诊断包临时文件".to_string())?
        .as_nanos();

    let mut created = None;
    for attempt in 0..16_u8 {
        let temporary = parent.join(format!(
            ".{target_name}.agent-audit-{}-{nonce}-{attempt}.tmp",
            std::process::id()
        ));
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)
        {
            Ok(file) => {
                created = Some((temporary, file));
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(format!("无法创建诊断包临时文件：{error}")),
        }
    }
    let Some((temporary, mut file)) = created else {
        return Err("无法创建唯一的诊断包临时文件".to_string());
    };

    let result = (|| {
        file.write_all(bytes)
            .map_err(|error| format!("无法写入诊断包：{error}"))?;
        file.sync_all()
            .map_err(|error| format!("无法同步诊断包：{error}"))?;
        drop(file);
        fs::hard_link(&temporary, target)
            .map_err(|error| format!("无法完成诊断包保存：{error}"))?;
        fs::remove_file(&temporary)
            .map_err(|error| format!("诊断包已保存，但无法清理临时文件：{error}"))?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

/// Save a locally generated diagnostic ZIP through an explicit native dialog.
/// The renderer supplies only bytes and a basename; the selected absolute path
/// stays inside this command and existing files are never overwritten.
#[tauri::command]
async fn save_diagnostics_archive(
    window: Window,
    bytes: Vec<u8>,
    suggested_name: String,
) -> Result<bool, String> {
    if bytes.len() > MAX_DIAGNOSTICS_ARCHIVE_BYTES {
        return Err("诊断包超过 16 MiB 限制".to_string());
    }
    let suggested_name = validated_diagnostics_filename(&suggested_name)?;
    let Some(selected) = window
        .dialog()
        .file()
        .set_title("保存本地诊断包")
        .add_filter("AgentAudit 本地诊断包", &["zip"])
        .set_file_name(suggested_name)
        .blocking_save_file()
    else {
        return Ok(false);
    };
    let target = selected
        .into_path()
        .map_err(|_| "诊断包保存位置不可用".to_string())?;
    if !target
        .extension()
        .and_then(OsStr::to_str)
        .is_some_and(|extension| extension.eq_ignore_ascii_case("zip"))
    {
        return Err("诊断包必须保存为 .zip 文件".to_string());
    }
    write_new_diagnostics_archive(&target, &bytes)?;
    Ok(true)
}

/// Read a user-selected Workspace archive through the native file dialog.
/// The absolute source path is used only within this command.
#[tauri::command]
async fn select_workspace_backup(window: Window) -> Result<Option<Vec<u8>>, String> {
    let Some(selected) = window
        .dialog()
        .file()
        .set_title("选择 Workspace 备份")
        .add_filter("AgentAudit Workspace 备份", &["zip"])
        .blocking_pick_file()
    else {
        return Ok(None);
    };
    let path = selected
        .into_path()
        .map_err(|_| "备份文件路径不可用".to_string())?;
    let metadata = fs::metadata(&path).map_err(|error| format!("无法读取备份文件：{error}"))?;
    if metadata.len() > MAX_WORKSPACE_BACKUP_BYTES {
        return Err("Workspace 备份超过 128 MiB 限制".to_string());
    }
    fs::read(&path)
        .map(Some)
        .map_err(|error| format!("无法读取 Workspace 备份：{error}"))
}

/// Persist an API-returned relative Workspace and restart only this app's
/// Sidecar. The API remains the sole owner of Contract and Workspace data.
#[tauri::command]
fn activate_workspace(app: AppHandle, relative_directory: String) -> Result<(), String> {
    validated_workspace_path(&relative_directory)?;
    persist_active_workspace(&relative_directory)?;

    let state = app.state::<SidecarState>();
    state.stop_child();
    state.set_launching();
    std::thread::spawn(move || start_sidecar(app));
    Ok(())
}

fn document_extension(path: &Path) -> String {
    let extension = path
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if extension.is_empty() {
        ".unknown".to_string()
    } else {
        format!(".{extension}")
    }
}

fn relative_document_path(path: &Path, root: Option<&Path>) -> String {
    let relative = root
        .and_then(|root| path.strip_prefix(root).ok())
        .unwrap_or_else(|| path.file_name().map(Path::new).unwrap_or(path));
    relative.to_string_lossy().replace('\\', "/")
}

fn document_display_name(path: &Path) -> String {
    path.file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .filter(|name| !name.is_empty())
        .unwrap_or_else(|| "未命名资料".to_string())
}

fn document_source_with_status(
    source_id: String,
    display_name: String,
    relative_path: String,
    extension: String,
    size_bytes: u64,
    content: Option<String>,
    status: &str,
    diagnostic: Option<(&str, &str)>,
) -> DocumentImportSource {
    DocumentImportSource {
        source_id,
        display_name,
        relative_path,
        extension,
        size_bytes,
        content,
        diagnostic: diagnostic.map(|(_, message)| message.to_string()),
        status: Some(status.to_string()),
        diagnostic_code: diagnostic.map(|(code, _)| code.to_string()),
    }
}

fn normalized_document_text(content: String) -> Result<String, (&'static str, &'static str)> {
    if content.trim().is_empty() {
        return Err(("no_text", "文档不包含可提取文本"));
    }
    if content.len() > MAX_DOCUMENT_TEXT_BYTES {
        return Err(("too_large", "标准化文本超过 2 MiB 限制"));
    }
    Ok(content)
}

fn docx_xml_name(name: &[u8]) -> &[u8] {
    name.rsplit(|value| *value == b':').next().unwrap_or(name)
}

/// Extract only the main Word document text from a DOCX package.
///
/// DOCX is an OOXML ZIP package.  We deliberately open only
/// `word/document.xml`; relationships, macros and every other package part
/// are never followed or executed.  The main XML entry is bounded before it
/// is decompressed so a compressed package cannot allocate unbounded memory.
fn extract_docx_text(bytes: &[u8]) -> Result<String, (&'static str, &'static str)> {
    if bytes.starts_with(&[0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]) {
        return Err(("encrypted", "Office 文档已加密，当前版本无法读取"));
    }
    let mut archive =
        ZipArchive::new(Cursor::new(bytes)).map_err(|_| ("parse_failed", "DOCX 压缩包结构无效"))?;
    let document = archive
        .by_name("word/document.xml")
        .map_err(|_| ("parse_failed", "DOCX 缺少主文档内容"))?;
    if document.encrypted() {
        return Err(("encrypted", "文档已加密，当前版本无法读取"));
    }
    if document.size() > MAX_DOCX_XML_BYTES as u64 {
        return Err(("too_large", "DOCX 主文档 XML 解压后超过 16 MiB 限制"));
    }

    let mut xml = Vec::with_capacity(document.size() as usize);
    document
        .take((MAX_DOCX_XML_BYTES + 1) as u64)
        .read_to_end(&mut xml)
        .map_err(|_| ("parse_failed", "无法读取 DOCX 主文档内容"))?;
    if xml.len() > MAX_DOCX_XML_BYTES {
        return Err(("too_large", "DOCX 主文档 XML 解压后超过 16 MiB 限制"));
    }

    let mut reader = Reader::from_reader(xml.as_slice());
    reader.config_mut().trim_text(false);
    let mut buffer = Vec::new();
    let mut in_text = false;
    let mut content = String::new();
    loop {
        match reader.read_event_into(&mut buffer) {
            Ok(Event::Start(event)) if docx_xml_name(event.name().as_ref()) == b"t" => {
                in_text = true;
            }
            Ok(Event::Start(event)) => match docx_xml_name(event.name().as_ref()) {
                b"tab" => content.push('\t'),
                b"br" | b"cr" => content.push('\n'),
                _ => {}
            },
            Ok(Event::End(event)) if docx_xml_name(event.name().as_ref()) == b"t" => {
                in_text = false;
            }
            Ok(Event::Text(event)) if in_text => {
                let decoded = event
                    .decode()
                    .map_err(|_| ("parse_failed", "DOCX 文本编码解析失败"))?;
                let text = quick_xml::escape::unescape(decoded.as_ref())
                    .map_err(|_| ("parse_failed", "DOCX 文本实体解析失败"))?;
                content.push_str(text.as_ref());
            }
            Ok(Event::GeneralRef(event)) if in_text => {
                if event.is_char_ref() {
                    let character = event
                        .resolve_char_ref()
                        .map_err(|_| ("parse_failed", "DOCX 文本实体解析失败"))?
                        .ok_or(("parse_failed", "DOCX 文本实体解析失败"))?;
                    content.push(character);
                } else {
                    let decoded = event
                        .decode()
                        .map_err(|_| ("parse_failed", "DOCX 文本实体解析失败"))?;
                    let entity = quick_xml::escape::resolve_xml_entity(decoded.as_ref())
                        .ok_or(("parse_failed", "DOCX 文本实体解析失败"))?;
                    content.push_str(entity);
                }
            }
            Ok(Event::Empty(event)) => match docx_xml_name(event.name().as_ref()) {
                b"tab" => content.push('\t'),
                b"br" | b"cr" => content.push('\n'),
                _ => {}
            },
            Ok(Event::End(event)) if docx_xml_name(event.name().as_ref()) == b"p" => {
                if !content.ends_with('\n') {
                    content.push('\n');
                }
            }
            Ok(Event::Eof) => break,
            Err(_) => return Err(("parse_failed", "DOCX 主文档 XML 解析失败")),
            _ => {}
        }
        buffer.clear();
    }

    normalized_document_text(content)
}

fn extract_document_text(
    extension: &str,
    bytes: Vec<u8>,
) -> Result<String, (&'static str, &'static str)> {
    match extension {
        ".txt" | ".md" => {
            let content = String::from_utf8(bytes)
                .map_err(|_| ("invalid_utf8", "文件不是有效的 UTF-8 文本"))?;
            normalized_document_text(content)
        }
        ".docx" => extract_docx_text(&bytes),
        ".pdf" => {
            let document = pdf_extract::Document::load_mem(&bytes)
                .map_err(|_| ("parse_failed", "PDF 文本解析失败，请确认文件内容完整"))?;
            if document.is_encrypted() {
                return Err(("encrypted", "PDF 已加密，当前版本无法读取"));
            }
            let mut content = String::new();
            let mut output = pdf_extract::PlainTextOutput::new(&mut content);
            pdf_extract::output_doc(&document, &mut output)
                .map_err(|_| ("parse_failed", "PDF 文本解析失败，请确认文件内容完整"))?;
            normalized_document_text(content)
        }
        _ => Err(("unsupported_format", "当前版本不支持此文件格式")),
    }
}

fn read_document_source(
    path: &Path,
    root: Option<&Path>,
    source_id: String,
) -> DocumentImportSource {
    let extension = document_extension(path);
    let display_name = document_display_name(path);
    let relative_path = relative_document_path(path, root);
    let size_bytes = match fs::metadata(path) {
        Ok(metadata) => metadata.len(),
        Err(_) => {
            return document_source_with_status(
                source_id,
                display_name,
                relative_path,
                extension,
                0,
                None,
                "invalid",
                Some(("read_failed", "无法读取文件，请检查文件权限后重试")),
            )
        }
    };

    if !matches!(extension.as_str(), ".txt" | ".md" | ".pdf" | ".docx") {
        return document_source_with_status(
            source_id,
            display_name,
            relative_path,
            extension,
            size_bytes,
            None,
            "unsupported",
            Some((
                "unsupported_format",
                "当前版本支持 PDF、DOCX、UTF-8 .txt 和 .md",
            )),
        );
    }

    if size_bytes > MAX_DOCUMENT_SOURCE_BYTES {
        return document_source_with_status(
            source_id,
            display_name,
            relative_path,
            extension,
            size_bytes,
            None,
            "invalid",
            Some(("too_large", "原始文件超过 20 MiB 限制")),
        );
    }

    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(_) => {
            return document_source_with_status(
                source_id,
                display_name,
                relative_path,
                extension,
                size_bytes,
                None,
                "invalid",
                Some(("read_failed", "无法读取文件，请检查文件权限后重试")),
            )
        }
    };
    match extract_document_text(&extension, bytes) {
        Ok(content) => document_source_with_status(
            source_id,
            display_name,
            relative_path,
            extension,
            size_bytes,
            Some(content),
            "ready",
            None,
        ),
        Err(diagnostic) => document_source_with_status(
            source_id,
            display_name,
            relative_path,
            extension,
            size_bytes,
            None,
            "invalid",
            Some(diagnostic),
        ),
    }
}

fn collect_document_files(current: &Path, files: &mut Vec<PathBuf>) -> Result<(), String> {
    let mut entries = fs::read_dir(current)
        .map_err(|_| "无法读取所选资料文件夹，请检查文件夹权限".to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "无法读取所选资料文件夹，请检查文件夹权限".to_string())?;
    entries.sort_by_key(|entry| entry.file_name());

    for entry in entries {
        let path = entry.path();
        let file_type = fs::symlink_metadata(&path)
            .map_err(|_| "无法读取所选资料文件夹中的项目".to_string())?
            .file_type();
        if file_type.is_symlink() {
            continue;
        }
        if file_type.is_dir() {
            collect_document_files(&path, files)?;
        } else if file_type.is_file() {
            files.push(path);
            if files.len() > MAX_DOCUMENT_IMPORT_ITEMS {
                return Err("一次最多导入 50 项资料，请缩小所选范围".to_string());
            }
        }
    }

    Ok(())
}

fn read_selected_files(paths: Vec<PathBuf>) -> Vec<DocumentImportSource> {
    paths
        .into_iter()
        .enumerate()
        .map(|(index, path)| {
            read_document_source(&path, None, format!("document-file-{}", index + 1))
        })
        .collect()
}

fn read_selected_folder(path: PathBuf) -> Result<Vec<DocumentImportSource>, String> {
    let mut files = Vec::new();
    collect_document_files(&path, &mut files)?;
    Ok(files
        .into_iter()
        .enumerate()
        .map(|(index, file)| {
            read_document_source(&file, Some(&path), format!("document-folder-{}", index + 1))
        })
        .collect())
}

/// Open the native multi-file picker and read only the files the user selected.
/// Absolute paths remain inside this native boundary and are never returned.
#[tauri::command]
async fn select_document_files(window: Window) -> Result<Vec<DocumentImportSource>, String> {
    let selected = window
        .dialog()
        .file()
        .set_title("选择企业资料")
        .add_filter("业务文档", &["pdf", "docx", "txt", "md"])
        .add_filter("所有文件", &["*"])
        .blocking_pick_files();
    let Some(selected) = selected else {
        return Ok(Vec::new());
    };
    if selected.len() > MAX_DOCUMENT_IMPORT_ITEMS {
        return Err("一次最多导入 50 项资料，请缩小所选范围".to_string());
    }

    let paths = selected
        .into_iter()
        .map(|file| {
            file.into_path()
                .map_err(|_| "所选文件路径不可用".to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(read_selected_files(paths))
}

/// Open the native folder picker and recursively read its text documents.
/// The returned paths are relative to the selected folder.
#[tauri::command]
async fn select_document_folder(window: Window) -> Result<Vec<DocumentImportSource>, String> {
    let selected = window
        .dialog()
        .file()
        .set_title("选择企业资料文件夹")
        .blocking_pick_folder();
    let Some(selected) = selected else {
        return Ok(Vec::new());
    };
    let path = selected
        .into_path()
        .map_err(|_| "所选文件夹路径不可用".to_string())?;
    read_selected_folder(path)
}

fn resolve_app_home() -> PathBuf {
    if let Some(value) = configured_app_home() {
        return value;
    }

    #[cfg(windows)]
    if let Some(value) = std::env::var_os("LOCALAPPDATA") {
        return PathBuf::from(value).join(APP_DIRECTORY_NAME);
    }

    #[cfg(target_os = "linux")]
    if let Some(value) = std::env::var_os("XDG_DATA_HOME") {
        if !value.is_empty() {
            return PathBuf::from(value).join(APP_DIRECTORY_NAME);
        }
    }

    if let Some(value) = std::env::var_os("HOME") {
        return PathBuf::from(value)
            .join(".local")
            .join("share")
            .join(APP_DIRECTORY_NAME);
    }

    PathBuf::from(APP_DIRECTORY_NAME)
}

/// Resolve the explicit launcher/test root before platform-specific defaults.
/// Release evidence unsets this override so an installed Linux build follows
/// the user's XDG directories; explicit values remain useful for isolated
/// desktop smoke runs on every platform.
fn configured_app_home() -> Option<PathBuf> {
    std::env::var_os("AGENT_AUDIT_HOME")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
}

fn resolve_config_root() -> PathBuf {
    if let Some(home) = configured_app_home() {
        return home.join("config");
    }

    #[cfg(target_os = "linux")]
    {
        if let Some(value) = std::env::var_os("XDG_CONFIG_HOME") {
            if !value.is_empty() {
                return PathBuf::from(value).join(APP_DIRECTORY_NAME);
            }
        }
        if let Some(value) = std::env::var_os("HOME") {
            return PathBuf::from(value)
                .join(".config")
                .join(APP_DIRECTORY_NAME);
        }
    }

    resolve_app_home().join("config")
}

fn resolve_state_root() -> PathBuf {
    if let Some(home) = configured_app_home() {
        return home.join("logs");
    }

    #[cfg(target_os = "linux")]
    {
        if let Some(value) = std::env::var_os("XDG_STATE_HOME") {
            if !value.is_empty() {
                return PathBuf::from(value).join(APP_DIRECTORY_NAME);
            }
        }
        if let Some(value) = std::env::var_os("HOME") {
            return PathBuf::from(value)
                .join(".local")
                .join("state")
                .join(APP_DIRECTORY_NAME);
        }
    }

    resolve_app_home().join("logs")
}

fn resolve_runtime_data_root() -> PathBuf {
    if let Some(home) = configured_app_home() {
        return home.join("data");
    }
    #[cfg(target_os = "linux")]
    return resolve_state_root();
    #[cfg(not(target_os = "linux"))]
    return resolve_app_home();
}

fn default_workspace_path() -> PathBuf {
    resolve_app_home()
        .join(WORKSPACE_DIRECTORY_NAME)
        .join("default")
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ActiveWorkspacePointer {
    relative_directory: String,
}

fn workspaces_root() -> PathBuf {
    resolve_app_home().join(WORKSPACE_DIRECTORY_NAME)
}

fn active_workspace_pointer_path() -> PathBuf {
    resolve_config_root().join(ACTIVE_WORKSPACE_FILENAME)
}

fn workspace_relative_path(value: &str) -> Result<PathBuf, String> {
    let value = value.trim();
    if value.is_empty() || value.contains('\\') || value.starts_with('/') || value.contains(':') {
        return Err("Workspace 目录必须是 workspaces 下的相对目录".to_string());
    }
    let parts: Vec<&str> = value.split('/').collect();
    let name = match parts.as_slice() {
        [directory, name] if *directory == WORKSPACE_DIRECTORY_NAME => *name,
        [name] => *name,
        _ => return Err("Workspace 目录必须是 workspaces 下的单个子目录".to_string()),
    };
    if name.is_empty() || name == "." || name == ".." || name.contains('/') {
        return Err("Workspace 目录必须是 workspaces 下的单个子目录".to_string());
    }
    Ok(PathBuf::from(WORKSPACE_DIRECTORY_NAME).join(name))
}

fn validated_workspace_path(relative_directory: &str) -> Result<(PathBuf, String), String> {
    let relative_path = workspace_relative_path(relative_directory)?;
    let root = workspaces_root();
    let candidate = resolve_app_home().join(&relative_path);
    if !candidate.is_dir() || !candidate.join("agent-audit-workspace.json").is_file() {
        return Err("目标 Workspace 不存在或缺少有效 manifest".to_string());
    }
    let canonical_root = root
        .canonicalize()
        .map_err(|_| "应用 Workspace 目录不可用".to_string())?;
    let canonical_candidate = candidate
        .canonicalize()
        .map_err(|_| "目标 Workspace 目录不可用".to_string())?;
    if canonical_candidate.parent() != Some(canonical_root.as_path()) {
        return Err("目标 Workspace 必须是应用 workspaces 下的直接子目录".to_string());
    }
    Ok((
        canonical_candidate,
        relative_path.to_string_lossy().replace('\\', "/"),
    ))
}

fn startup_workspace_path() -> Result<PathBuf, String> {
    let pointer_path = active_workspace_pointer_path();
    if !pointer_path.is_file() {
        return Ok(default_workspace_path());
    }
    let payload = fs::read_to_string(&pointer_path)
        .map_err(|error| format!("无法读取当前 Workspace 指针：{error}"))?;
    let pointer: ActiveWorkspacePointer = serde_json::from_str(&payload)
        .map_err(|error| format!("当前 Workspace 指针格式无效：{error}"))?;
    validated_workspace_path(&pointer.relative_directory).map(|(path, _)| path)
}

fn persist_active_workspace(relative_directory: &str) -> Result<(), String> {
    let (_, normalized) = validated_workspace_path(relative_directory)?;
    let pointer_path = active_workspace_pointer_path();
    let parent = pointer_path
        .parent()
        .ok_or_else(|| "应用数据目录不可用".to_string())?;
    fs::create_dir_all(parent).map_err(|error| format!("无法创建应用指针目录：{error}"))?;
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "无法创建 Workspace 指针临时文件".to_string())?
        .as_nanos();
    let temporary_path = pointer_path.with_file_name(format!(
        ".active-workspace-{}-{nonce}.json.tmp",
        std::process::id()
    ));
    let payload = serde_json::to_vec_pretty(&ActiveWorkspacePointer {
        relative_directory: normalized,
    })
    .map_err(|error| format!("无法生成 Workspace 指针：{error}"))?;
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary_path)
            .map_err(|error| format!("无法创建 Workspace 指针临时文件：{error}"))?;
        file.write_all(&payload)
            .map_err(|error| format!("无法写入 Workspace 指针：{error}"))?;
        file.sync_all()
            .map_err(|error| format!("无法同步 Workspace 指针：{error}"))?;
        drop(file);
        replace_active_workspace_pointer(&temporary_path, &pointer_path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary_path);
    }
    result
}

#[cfg(windows)]
fn replace_active_workspace_pointer(source: &Path, target: &Path) -> Result<(), String> {
    let source_wide: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
    let target_wide: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
    let result = unsafe {
        MoveFileExW(
            source_wide.as_ptr(),
            target_wide.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if result == 0 {
        return Err(format!(
            "无法提交 Workspace 指针：{}",
            std::io::Error::last_os_error()
        ));
    }
    Ok(())
}

#[cfg(not(windows))]
fn replace_active_workspace_pointer(source: &Path, target: &Path) -> Result<(), String> {
    fs::rename(source, target).map_err(|error| format!("无法提交 Workspace 指针：{error}"))
}

fn sidecar_status_path() -> PathBuf {
    resolve_runtime_data_root().join("sidecar.status.json")
}

fn read_sidecar_lifecycle(path: &Path, expected_port: u16) -> Result<bool, String> {
    let payload =
        fs::read_to_string(path).map_err(|error| format!("尚未读取到本机后台状态：{error}"))?;
    let status: SidecarLifecycleFile =
        serde_json::from_str(&payload).map_err(|error| format!("本机后台状态格式无效：{error}"))?;
    if status.host != SIDECAR_HOST || status.port != Some(expected_port) {
        return Err("本机后台状态与本次启动端口不匹配".to_string());
    }
    match status.status.as_str() {
        "ready" => Ok(true),
        "starting" => Ok(false),
        "failed" => Err(status
            .detail
            .unwrap_or_else(|| "本机后台启动失败".to_string())),
        "stopped" => Err("本机后台已停止".to_string()),
        _ => Err("本机后台返回了未知生命周期状态".to_string()),
    }
}

fn ensure_local_directories(_workspace: &Path) -> Result<(), String> {
    let app_home = resolve_app_home();
    fs::create_dir_all(&app_home)
        .map_err(|error| format!("无法创建应用数据目录 {}：{error}", app_home.display()))?;
    fs::create_dir_all(resolve_runtime_data_root()).map_err(|error| {
        format!(
            "无法创建 Sidecar 状态目录 {}：{error}",
            resolve_runtime_data_root().display()
        )
    })?;
    fs::create_dir_all(resolve_config_root()).map_err(|error| {
        format!(
            "无法创建应用配置目录 {}：{error}",
            resolve_config_root().display()
        )
    })?;
    fs::create_dir_all(resolve_state_root()).map_err(|error| {
        format!(
            "无法创建应用状态目录 {}：{error}",
            resolve_state_root().display()
        )
    })?;
    Ok(())
}

fn reserve_local_port() -> Result<u16, String> {
    TcpListener::bind((SIDECAR_HOST, 0))
        .map_err(|error| format!("无法为本机后台分配端口：{error}"))
        .and_then(|listener| {
            listener
                .local_addr()
                .map(|address| address.port())
                .map_err(|error| format!("无法读取本机后台端口：{error}"))
        })
}

fn probe_api(port: u16) -> Result<(), String> {
    let address = format!("{SIDECAR_HOST}:{port}")
        .parse::<std::net::SocketAddr>()
        .map_err(|error| format!("本机地址无效：{error}"))?;
    let mut stream = TcpStream::connect_timeout(&address, PROBE_TIMEOUT)
        .map_err(|error| format!("连接本机后台失败：{error}"))?;
    stream
        .set_read_timeout(Some(PROBE_TIMEOUT))
        .map_err(|error| format!("设置本机后台探活超时失败：{error}"))?;
    stream
        .write_all(
            format!(
                "GET /api/health HTTP/1.1\r\nHost: {SIDECAR_HOST}:{port}\r\nConnection: close\r\n\r\n"
            )
            .as_bytes(),
        )
        .map_err(|error| format!("发送本机后台探活请求失败：{error}"))?;

    let mut response = Vec::new();
    stream
        .read_to_end(&mut response)
        .map_err(|error| format!("读取本机后台探活响应失败：{error}"))?;
    let response = String::from_utf8_lossy(&response);
    let status_line = response.lines().next().unwrap_or_default();
    if status_line.starts_with("HTTP/1.1 200 ") || status_line.starts_with("HTTP/1.0 200 ") {
        return Ok(());
    }

    Err(format!("本机后台未返回就绪响应（{status_line}）"))
}

fn startup_failure_message(state: &SidecarState, reason: impl AsRef<str>) -> String {
    let stderr = state.stderr();
    if stderr.is_empty() {
        format!(
            "{}。请检查安装包中的 API 后台文件和 Workspace 配置。",
            reason.as_ref()
        )
    } else {
        format!(
            "{}。后台输出：{}",
            reason.as_ref(),
            stderr.replace('\n', " ")
        )
    }
}

fn show_startup_failure(app: &tauri::AppHandle, message: String) {
    let _ = app
        .dialog()
        .message(message)
        .title("知盾 AgentAudit 无法启动")
        .kind(MessageDialogKind::Error)
        .buttons(MessageDialogButtons::Ok)
        .blocking_show();
}

fn report_startup_failure(app: &tauri::AppHandle, state: &SidecarState, message: String) {
    if state.mark_failure_reported() {
        show_startup_failure(app, message);
    }
}

fn start_sidecar(app: tauri::AppHandle) {
    let state = app.state::<SidecarState>();
    let workspace = match startup_workspace_path() {
        Ok(path) => path,
        Err(error) => {
            state.set_failed(error.clone());
            report_startup_failure(&app, &state, error);
            return;
        }
    };
    if let Err(error) = ensure_local_directories(&workspace) {
        state.set_failed(error.clone());
        report_startup_failure(&app, &state, error);
        return;
    }

    let port = match reserve_local_port() {
        Ok(port) => port,
        Err(error) => {
            state.set_failed(error.clone());
            report_startup_failure(&app, &state, error);
            return;
        }
    };
    if !state.set_starting(port) {
        return;
    }
    let ready_file = sidecar_status_path();
    let _ = fs::remove_file(&ready_file);

    let args = [
        "--host".to_string(),
        SIDECAR_HOST.to_string(),
        "--port".to_string(),
        port.to_string(),
        "--workspace".to_string(),
        workspace.to_string_lossy().into_owned(),
        "--ready-file".to_string(),
        ready_file.to_string_lossy().into_owned(),
    ];
    let mut command = match app.shell().sidecar(SIDECAR_NAME) {
        Ok(command) => command.args(args),
        Err(error) => {
            let message = startup_failure_message(&state, format!("找不到 API Sidecar：{error}"));
            state.set_failed(message.clone());
            report_startup_failure(&app, &state, message);
            return;
        }
    };
    if let ProviderSecretLookup::Present(secret) = state.provider_secret() {
        command = command.env(PROVIDER_SECRET_ENV, secret);
    }
    let (mut receiver, child) = match command.spawn() {
        Ok(result) => result,
        Err(error) => {
            let message = startup_failure_message(&state, format!("无法启动 API Sidecar：{error}"));
            state.set_failed(message.clone());
            report_startup_failure(&app, &state, message);
            return;
        }
    };
    let process_id = state.set_child(child);
    if state.is_stopped() {
        state.stop_child();
        return;
    }
    let watcher_app = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            match event {
                CommandEvent::Stderr(bytes) => {
                    watcher_app.state::<SidecarState>().append_stderr(&bytes)
                }
                CommandEvent::Error(error) => watcher_app
                    .state::<SidecarState>()
                    .append_stderr(error.as_bytes()),
                CommandEvent::Terminated(payload) => {
                    let watcher_state = watcher_app.state::<SidecarState>();
                    let was_current = watcher_state.clear_child_if(process_id);
                    if was_current && !watcher_state.is_failed_or_stopped() {
                        let code = payload
                            .code
                            .map_or_else(|| "无退出码".to_string(), |value| value.to_string());
                        let message = startup_failure_message(
                            &watcher_state,
                            format!("API Sidecar 意外退出（退出码：{code}）"),
                        );
                        watcher_state.set_failed(message.clone());
                        let _ = watcher_app.emit("desktop-runtime-failed", watcher_state.status());
                        report_startup_failure(&watcher_app, &watcher_state, message);
                    }
                    break;
                }
                CommandEvent::Stdout(_) => {}
                _ => {}
            }
        }
    });

    let deadline = Instant::now() + STARTUP_TIMEOUT;
    let api_base = format!("http://{SIDECAR_HOST}:{port}");
    let mut last_error = "尚未收到本机后台响应".to_string();
    while Instant::now() < deadline {
        if state.is_failed_or_stopped() {
            if state.status().state == "failed" {
                let message = state
                    .status()
                    .message
                    .unwrap_or_else(|| "API Sidecar 启动失败".to_string());
                report_startup_failure(&app, &state, message);
            }
            return;
        }
        match read_sidecar_lifecycle(&ready_file, port) {
            Ok(true) => match probe_api(port) {
                Ok(()) => {
                    state.set_ready(api_base.clone(), port, process_id);
                    let status = state.status();
                    let _ = app.emit("desktop-runtime-ready", status);
                    if let Some(splash) = app.get_webview_window("splashscreen") {
                        let _ = splash.close();
                    }
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                    return;
                }
                Err(error) => last_error = error,
            },
            Ok(false) => last_error = "本机后台仍在完成启动".to_string(),
            Err(error) => last_error = error,
        }
        std::thread::sleep(Duration::from_millis(100));
    }

    let message = startup_failure_message(
        &state,
        format!(
            "API Sidecar 在 {} 秒内未就绪：{last_error}",
            STARTUP_TIMEOUT.as_secs()
        ),
    );
    state.stop_child();
    state.set_failed(message.clone());
    report_startup_failure(&app, &state, message);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::OsString;
    use std::fs::{self, File};
    use std::io::Write;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static TEMP_FIXTURE_ID: AtomicUsize = AtomicUsize::new(0);
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    struct EnvironmentGuard {
        values: Vec<(&'static str, Option<OsString>)>,
    }

    impl EnvironmentGuard {
        fn capture(names: &[&'static str]) -> Self {
            Self {
                values: names
                    .iter()
                    .map(|name| (*name, std::env::var_os(name)))
                    .collect(),
            }
        }
    }

    impl Drop for EnvironmentGuard {
        fn drop(&mut self) {
            for (name, value) in &self.values {
                match value {
                    Some(value) => std::env::set_var(name, value),
                    None => std::env::remove_var(name),
                }
            }
        }
    }

    #[test]
    fn explicit_home_precedes_platform_data_roots_for_isolated_runs() {
        let _lock = ENV_LOCK.lock().unwrap();
        let _environment = EnvironmentGuard::capture(&[
            "AGENT_AUDIT_HOME",
            "LOCALAPPDATA",
            "XDG_DATA_HOME",
            "XDG_CONFIG_HOME",
            "XDG_STATE_HOME",
        ]);
        let root = temp_directory("explicit-home");
        std::env::set_var("AGENT_AUDIT_HOME", &root);
        std::env::set_var("LOCALAPPDATA", root.join("local-app-data"));
        std::env::set_var("XDG_DATA_HOME", root.join("xdg-data"));
        std::env::set_var("XDG_CONFIG_HOME", root.join("xdg-config"));
        std::env::set_var("XDG_STATE_HOME", root.join("xdg-state"));

        assert_eq!(resolve_app_home(), root);
        assert_eq!(
            active_workspace_pointer_path(),
            root.join("config").join(ACTIVE_WORKSPACE_FILENAME)
        );
        assert_eq!(
            sidecar_status_path(),
            root.join("data").join("sidecar.status.json")
        );
    }

    #[test]
    fn desktop_shutdown_can_only_start_once() {
        let state = SidecarState::default();

        assert!(state.begin_shutdown());
        assert!(!state.begin_shutdown());
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_uses_split_xdg_data_config_and_state_roots() {
        let _lock = ENV_LOCK.lock().unwrap();
        let _environment = EnvironmentGuard::capture(&[
            "AGENT_AUDIT_HOME",
            "XDG_DATA_HOME",
            "XDG_CONFIG_HOME",
            "XDG_STATE_HOME",
        ]);
        std::env::remove_var("AGENT_AUDIT_HOME");
        let root = temp_directory("xdg-roots");
        let data = root.join("data");
        let config = root.join("config");
        let state = root.join("state");
        std::env::set_var("XDG_DATA_HOME", &data);
        std::env::set_var("XDG_CONFIG_HOME", &config);
        std::env::set_var("XDG_STATE_HOME", &state);

        assert_eq!(resolve_app_home(), data.join(APP_DIRECTORY_NAME));
        assert_eq!(resolve_config_root(), config.join(APP_DIRECTORY_NAME));
        assert_eq!(resolve_state_root(), state.join(APP_DIRECTORY_NAME));
        assert_eq!(resolve_runtime_data_root(), state.join(APP_DIRECTORY_NAME));
        assert_eq!(
            active_workspace_pointer_path(),
            config
                .join(APP_DIRECTORY_NAME)
                .join(ACTIVE_WORKSPACE_FILENAME)
        );
        assert_eq!(
            sidecar_status_path(),
            state.join(APP_DIRECTORY_NAME).join("sidecar.status.json")
        );
    }

    fn minimal_pdf(text: &str) -> Vec<u8> {
        let stream = format!(
            "BT\n/F1 12 Tf\n72 720 Td\n({text}) Tj\nET\n",
            text = text.replace('(', "\\(").replace(')', "\\)"),
        );
        let objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>".to_vec(),
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>".to_vec(),
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>".to_vec(),
            format!(
                "<< /Length {} >>\nstream\n{}endstream",
                stream.len(), stream
            )
            .into_bytes(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>".to_vec(),
        ];

        let mut pdf = b"%PDF-1.4\n".to_vec();
        let mut offsets = vec![0usize];
        for (index, object) in objects.iter().enumerate() {
            offsets.push(pdf.len());
            write!(&mut pdf, "{} 0 obj\n", index + 1).unwrap();
            pdf.extend_from_slice(object);
            pdf.extend_from_slice(b"\nendobj\n");
        }

        let xref_offset = pdf.len();
        write!(&mut pdf, "xref\n0 {}\n", offsets.len()).unwrap();
        pdf.extend_from_slice(b"0000000000 65535 f \n");
        for offset in offsets.iter().skip(1) {
            write!(&mut pdf, "{offset:010} 00000 n \n").unwrap();
        }
        write!(
            &mut pdf,
            "trailer\n<< /Size {} /Root 1 0 R /ID [<0123456789ABCDEF0123456789ABCDEF> <0123456789ABCDEF0123456789ABCDEF>] >>\nstartxref\n{}\n%%EOF\n",
            offsets.len(),
            xref_offset
        )
        .unwrap();
        pdf
    }

    fn encrypted_pdf() -> Vec<u8> {
        let mut document = pdf_extract::Document::load_mem(&minimal_pdf("encrypted")).unwrap();
        let requested = pdf_extract::EncryptionVersion::V1 {
            document: &document,
            owner_password: "owner",
            user_password: "user",
            permissions: pdf_extract::Permissions::all(),
        };
        let state = pdf_extract::EncryptionState::try_from(requested).unwrap();
        document.encrypt(&state).unwrap();
        let mut bytes = Vec::new();
        document.save_to(&mut bytes).unwrap();
        bytes
    }

    fn minimal_docx(xml: &[u8]) -> Vec<u8> {
        let mut bytes = Cursor::new(Vec::new());
        {
            let mut writer = zip::ZipWriter::new(&mut bytes);
            let options = zip::write::SimpleFileOptions::default();
            writer.start_file("[Content_Types].xml", options).unwrap();
            writer
                .write_all(b"<?xml version=\"1.0\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>")
                .unwrap();
            writer.start_file("word/document.xml", options).unwrap();
            writer.write_all(xml).unwrap();
            writer.finish().unwrap();
        }
        bytes.into_inner()
    }

    fn temp_fixture(extension: &str, bytes: &[u8]) -> PathBuf {
        let id = TEMP_FIXTURE_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-audit-document-{id}-{}.{}",
            std::process::id(),
            extension.trim_start_matches('.')
        ));
        fs::write(&path, bytes).unwrap();
        path
    }

    fn temp_directory(label: &str) -> PathBuf {
        let id = TEMP_FIXTURE_ID.fetch_add(1, Ordering::Relaxed);
        let path =
            std::env::temp_dir().join(format!("agent-audit-{label}-{id}-{}", std::process::id()));
        fs::create_dir(&path).unwrap();
        path
    }

    fn diagnostics_temporary_files(directory: &Path) -> Vec<PathBuf> {
        fs::read_dir(directory)
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .filter(|path| {
                path.file_name()
                    .and_then(OsStr::to_str)
                    .is_some_and(|name| name.contains(".agent-audit-") && name.ends_with(".tmp"))
            })
            .collect()
    }

    #[test]
    fn diagnostics_archive_publishes_complete_bytes_without_temporary_files() {
        let directory = temp_directory("diagnostics-success");
        let target = directory.join("diagnostics.zip");
        let bytes = b"complete diagnostic archive";

        write_new_diagnostics_archive(&target, bytes).unwrap();

        assert_eq!(fs::read(&target).unwrap(), bytes);
        assert!(diagnostics_temporary_files(&directory).is_empty());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn diagnostics_archive_never_replaces_an_existing_target() {
        let directory = temp_directory("diagnostics-existing");
        let target = directory.join("diagnostics.zip");
        fs::write(&target, b"original archive").unwrap();

        assert!(write_new_diagnostics_archive(&target, b"replacement archive").is_err());

        assert_eq!(fs::read(&target).unwrap(), b"original archive");
        assert!(diagnostics_temporary_files(&directory).is_empty());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn diagnostics_filename_and_size_boundaries_are_explicit() {
        assert_eq!(
            validated_diagnostics_filename("agent-audit-diagnostics.zip").unwrap(),
            "agent-audit-diagnostics.zip"
        );
        assert!(validated_diagnostics_filename("../diagnostics.zip").is_err());
        assert!(validated_diagnostics_filename("diagnostics.json").is_err());
        assert!(validated_diagnostics_filename("diagnostics\n.zip").is_err());
        assert_eq!(MAX_DIAGNOSTICS_ARCHIVE_BYTES, 16 * 1024 * 1024);
    }

    #[test]
    fn sidecar_lifecycle_file_requires_current_loopback_port_and_ready_state() {
        let directory = temp_directory("sidecar-lifecycle");
        let status_file = directory.join("sidecar.status.json");

        assert!(read_sidecar_lifecycle(&status_file, 43123).is_err());

        fs::write(
            &status_file,
            r#"{"status":"starting","host":"127.0.0.1","port":43123,"detail":null}"#,
        )
        .unwrap();
        assert!(!read_sidecar_lifecycle(&status_file, 43123).unwrap());

        fs::write(
            &status_file,
            r#"{"status":"ready","host":"127.0.0.1","port":43124,"detail":null}"#,
        )
        .unwrap();
        assert!(read_sidecar_lifecycle(&status_file, 43123).is_err());

        fs::write(
            &status_file,
            r#"{"status":"failed","host":"127.0.0.1","port":43123,"detail":"fixture failure"}"#,
        )
        .unwrap();
        assert_eq!(
            read_sidecar_lifecycle(&status_file, 43123).unwrap_err(),
            "fixture failure"
        );

        fs::write(
            &status_file,
            r#"{"status":"ready","host":"127.0.0.1","port":43123,"detail":null}"#,
        )
        .unwrap();
        assert!(read_sidecar_lifecycle(&status_file, 43123).unwrap());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn active_workspace_pointer_replacement_is_complete_and_removes_source() {
        let directory = temp_directory("active-pointer");
        let target = directory.join("active-workspace.json");
        let source = directory.join(".active-workspace.fixture.json.tmp");
        fs::write(&target, b"old pointer").unwrap();
        fs::write(&source, b"new complete pointer").unwrap();

        replace_active_workspace_pointer(&source, &target).unwrap();

        assert_eq!(fs::read(&target).unwrap(), b"new complete pointer");
        assert!(!source.exists());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn extracts_pdf_text_and_reports_empty_or_corrupt_documents() {
        let text = extract_document_text(".pdf", minimal_pdf("Hello PDF")).unwrap();
        assert!(text.contains("Hello PDF"));

        assert_eq!(
            extract_document_text(".pdf", minimal_pdf(""))
                .unwrap_err()
                .0,
            "no_text"
        );
        assert_eq!(
            extract_document_text(".pdf", b"not a PDF".to_vec())
                .unwrap_err()
                .0,
            "parse_failed"
        );
    }

    #[test]
    fn extracts_docx_text_and_rejects_corrupt_or_ole_packages() {
        let xml = br#"<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello &amp; world</w:t></w:r><w:r><w:tab/><w:t>DOCX</w:t></w:r></w:p></w:body></w:document>"#;
        let text = extract_document_text(".docx", minimal_docx(xml)).unwrap();
        assert!(
            text.contains("Hello & world\tDOCX"),
            "extracted DOCX text: {text:?}"
        );
        assert_eq!(
            extract_document_text(".docx", b"not a DOCX".to_vec())
                .unwrap_err()
                .0,
            "parse_failed"
        );
        assert_eq!(
            extract_document_text(
                ".docx",
                vec![0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]
            )
            .unwrap_err()
            .0,
            "encrypted"
        );
        assert_eq!(
            extract_document_text(
                ".docx",
                minimal_docx(b"<w:document xmlns:w=\"urn:w\"><w:body/></w:document>")
            )
            .unwrap_err()
            .0,
            "no_text"
        );
    }

    #[test]
    fn reports_structured_pdf_encryption_and_enforces_text_limits() {
        assert_eq!(
            extract_document_text(".pdf", encrypted_pdf())
                .unwrap_err()
                .0,
            "encrypted"
        );
        assert!(normalized_document_text("x".repeat(MAX_DOCUMENT_TEXT_BYTES)).is_ok());
        assert_eq!(
            normalized_document_text("x".repeat(MAX_DOCUMENT_TEXT_BYTES + 1))
                .unwrap_err()
                .0,
            "too_large"
        );
    }

    #[test]
    fn enforces_raw_source_boundary_and_folder_skips_are_itemized() {
        let exact = temp_fixture("pdf", &vec![b'x'; MAX_DOCUMENT_SOURCE_BYTES as usize]);
        let exact_source = read_document_source(&exact, None, "exact".to_string());
        assert_ne!(exact_source.diagnostic_code.as_deref(), Some("too_large"));
        fs::remove_file(&exact).unwrap();

        let over = temp_fixture("pdf", &vec![b'x'; MAX_DOCUMENT_SOURCE_BYTES as usize + 1]);
        let over_source = read_document_source(&over, None, "over".to_string());
        assert_eq!(over_source.diagnostic_code.as_deref(), Some("too_large"));
        fs::remove_file(&over).unwrap();

        let folder = std::env::temp_dir().join(format!(
            "agent-audit-folder-{}-{}",
            std::process::id(),
            TEMP_FIXTURE_ID.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(folder.join("nested")).unwrap();
        fs::write(folder.join("readme.txt"), b"hello").unwrap();
        fs::write(folder.join("nested").join("notes.md"), b"notes").unwrap();
        let mut unrelated = File::create(folder.join("ignore.bin")).unwrap();
        unrelated.write_all(b"ignore").unwrap();
        let sources = read_selected_folder(folder.clone()).unwrap();
        assert_eq!(sources.len(), 3);
        assert_eq!(
            sources
                .iter()
                .find(|source| source.extension == ".bin")
                .and_then(|source| source.diagnostic_code.as_deref()),
            Some("unsupported_format")
        );
        fs::remove_dir_all(folder).unwrap();
    }
}

pub fn run() {
    tauri::Builder::default()
        .manage(SidecarState::default())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            get_api_base,
            get_desktop_runtime_status,
            store_provider_secret,
            delete_provider_secret,
            stop_sidecar,
            quit_application,
            save_workspace_backup,
            save_diagnostics_archive,
            select_workspace_backup,
            activate_workspace,
            select_document_files,
            select_document_folder
        ])
        .setup(|app| {
            app.state::<SidecarState>().set_launching();
            WebviewWindowBuilder::new(app, "splashscreen", WebviewUrl::App("splash.html".into()))
                .title("知盾 AgentAudit 正在启动")
                .inner_size(720.0, 440.0)
                .resizable(false)
                .decorations(false)
                .center()
                .build()?;
            let handle = app.handle().clone();
            std::thread::spawn(move || start_sidecar(handle));
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the short-lived splash is part of a successful startup;
            // only closing the real application window owns Sidecar shutdown.
            if window.label() == "main" {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let app = window.app_handle().clone();
                    let state = app.state::<SidecarState>();
                    let _ = window.hide();
                    if state.begin_shutdown() {
                        std::thread::spawn(move || {
                            app.state::<SidecarState>().stop_child();
                            app.exit(0);
                        });
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("知盾 AgentAudit 桌面端启动失败");
}
