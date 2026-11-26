#![cfg_attr(windows, windows_subsystem = "windows")]
mod appearance;
mod manager;
mod profile;
mod service;
mod updates;

use appearance::{Appearance, Mode};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    path::PathBuf,
    sync::{mpsc, Arc, Mutex},
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    window::Color,
    Emitter, Manager, Theme, WebviewWindow, WindowEvent,
};

type Shared = Arc<Mutex<Value>>;
enum Event {
    Action(String, Value),
    Service(Value),
    Exited(bool),
    Checked(Result<Option<velopack::UpdateInfo>, String>),
    Progress(i16),
    Downloaded(Result<(), String>),
    Imported(Result<bool, String>),
    Notice(String),
}
struct Desktop {
    view: Shared,
    tx: mpsc::Sender<Event>,
    profile: Option<PathBuf>,
    appearance: Mutex<WindowAppearance>,
}

#[derive(Clone, Serialize)]
struct AppearanceSnapshot {
    revision: u64,
    #[serde(flatten)]
    settings: Appearance,
}

struct WindowAppearance {
    current: AppearanceSnapshot,
    applied: Option<u64>,
    reveal_pending: bool,
}

#[derive(Deserialize)]
#[serde(rename_all = "lowercase")]
enum Scheme {
    Light,
    Dark,
}

fn refresh_appearance(app: &tauri::AppHandle, changed_wallpaper: bool) {
    let state = app.state::<Desktop>();
    let Some(settings) = state
        .profile
        .as_deref()
        .and_then(|path| Appearance::read(path).ok())
    else {
        return;
    };
    let next = {
        let mut appearance = state.appearance.lock().unwrap();
        if appearance.current.settings == settings
            && !(changed_wallpaper && settings.wallpaper.is_some())
        {
            return;
        }
        appearance.current = AppearanceSnapshot {
            revision: appearance.current.revision + 1,
            settings,
        };
        appearance.current.clone()
    };
    let _ = app.emit_to("main", "manager-appearance-changed", next);
}

#[tauri::command]
fn manager_appearance(state: tauri::State<Desktop>) -> AppearanceSnapshot {
    state.appearance.lock().unwrap().current.clone()
}

#[tauri::command]
async fn manager_wallpaper(
    state: tauri::State<'_, Desktop>,
    revision: u64,
) -> Result<tauri::ipc::Response, String> {
    let profile = state.profile.clone().ok_or("无可用的背景图片")?;
    let name = {
        let appearance = state.appearance.lock().unwrap();
        if appearance.current.revision != revision {
            return Err("外观设置已变更".into());
        }
        appearance
            .current
            .settings
            .wallpaper
            .clone()
            .ok_or("无可用的背景图片")?
    };
    tauri::async_runtime::spawn_blocking(move || {
        appearance::read_wallpaper(&profile, &name)
            .map(tauri::ipc::Response::new)
            .map_err(|_| "无法读取背景图片".into())
    })
    .await
    .map_err(|_| "无法读取背景图片".to_owned())?
}

#[tauri::command]
fn manager_system_scheme(
    window: WebviewWindow,
    state: tauri::State<Desktop>,
    revision: u64,
) -> Result<bool, String> {
    {
        let appearance = state.appearance.lock().unwrap();
        if appearance.current.revision != revision
            || appearance.current.settings.mode != Mode::System
        {
            return Err("外观设置已变更".into());
        }
    }
    window.set_theme(None).map_err(|err| err.to_string())?;
    window
        .theme()
        .map(|theme| theme == Theme::Light)
        .map_err(|err| err.to_string())
}

#[tauri::command]
fn manager_appearance_applied(
    window: WebviewWindow,
    state: tauri::State<Desktop>,
    revision: u64,
    scheme: Scheme,
    background: [u8; 3],
) -> Result<bool, String> {
    let mode = {
        let appearance = state.appearance.lock().unwrap();
        if appearance.current.revision != revision {
            return Ok(false);
        }
        appearance.current.settings.mode
    };
    if mode != Mode::System {
        let theme = match scheme {
            Scheme::Light => Theme::Light,
            Scheme::Dark => Theme::Dark,
        };
        let _ = window.set_theme(Some(theme));
    }
    let [r, g, b] = background;
    let _ = window.set_background_color(Some(Color(r, g, b, 255)));
    let show = {
        let mut appearance = state.appearance.lock().unwrap();
        if appearance.current.revision != revision {
            return Ok(false);
        }
        appearance.applied = Some(revision);
        std::mem::take(&mut appearance.reveal_pending)
    };
    if show {
        show_manager(&window);
    }
    Ok(true)
}

#[tauri::command]
fn snapshot(state: tauri::State<Desktop>) -> Value {
    state.view.lock().unwrap().clone()
}
#[tauri::command]
fn action(
    state: tauri::State<Desktop>,
    name: String,
    options: Option<Value>,
) -> Result<(), String> {
    state
        .tx
        .send(Event::Action(name, options.unwrap_or(Value::Null)))
        .map_err(|_| "管理器已停止".into())
}
fn show_manager(window: &WebviewWindow) {
    let _ = window.unminimize();
    let _ = window.show();
    let _ = window.set_focus();
}
fn reveal(app: &tauri::AppHandle) {
    if let (Some(window), Some(state)) =
        (app.get_webview_window("main"), app.try_state::<Desktop>())
    {
        {
            let mut appearance = state.appearance.lock().unwrap();
            if appearance.applied != Some(appearance.current.revision) {
                appearance.reveal_pending = true;
                return;
            }
        }
        show_manager(&window);
    }
}
fn main() {
    velopack::VelopackApp::build()
        .set_auto_apply_on_startup(false)
        .run();
    let result = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| reveal(app)))
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            snapshot,
            action,
            manager_appearance,
            manager_wallpaper,
            manager_system_scheme,
            manager_appearance_applied
        ])
        .setup(|app| {
            let (tx, rx) = mpsc::channel();
            let view = Arc::new(Mutex::new(json!({"phase":"loading"})));
            let location = profile::current_location();
            let profile = location.as_ref().ok().map(|(_, profile)| profile.clone());
            let settings = profile
                .as_deref()
                .and_then(|path| Appearance::read(path).ok())
                .unwrap_or_default();
            app.manage(Desktop {
                view: view.clone(),
                tx: tx.clone(),
                profile,
                appearance: Mutex::new(WindowAppearance {
                    current: AppearanceSnapshot {
                        revision: 0,
                        settings,
                    },
                    applied: None,
                    reveal_pending: !std::env::args().any(|a| a == "--resume-hidden"),
                }),
            });
            let show = MenuItem::with_id(app, "show", "显示管理器", true, None::<&str>)?;
            let open = MenuItem::with_id(app, "open", "打开聊天", true, None::<&str>)?;
            let exit = MenuItem::with_id(app, "quit", "退出并停止服务", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &open, &exit])?;
            TrayIconBuilder::new()
                .tooltip("SimpleTavern 服务管理器")
                .menu(&menu)
                .icon(tauri::image::Image::from_bytes(include_bytes!(
                    "../icons/icon.png"
                ))?)
                .show_menu_on_left_click(false)
                .on_tray_icon_event(|tray, e| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = e
                    {
                        reveal(tray.app_handle());
                    }
                })
                .on_menu_event(|app, e| {
                    let id = e.id.as_ref();
                    if id == "show" {
                        reveal(app);
                    } else {
                        if id == "quit" {
                            reveal(app);
                        }
                        if app
                            .state::<Desktop>()
                            .tx
                            .send(Event::Action(id.into(), Value::Null))
                            .is_err()
                            && id == "quit"
                        {
                            app.exit(0);
                        }
                    }
                })
                .build(app)?;
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                if let Err(detail) =
                    location
                        .map_err(|err| err.to_string())
                        .and_then(|(content, profile)| {
                            manager::ManagerState::run(
                                handle.clone(),
                                view.clone(),
                                tx,
                                rx,
                                content,
                                profile,
                            )
                        })
                {
                    *view.lock().unwrap() = json!({"phase":"fatal","detail":detail});
                    reveal(&handle);
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                if window
                    .state::<Desktop>()
                    .tx
                    .send(Event::Action("close".into(), Value::Null))
                    .is_err()
                {
                    window.app_handle().exit(0);
                }
            }
        })
        .run(tauri::generate_context!());
    if let Err(error) = result {
        rfd::MessageDialog::new()
            .set_title("无法打开 SimpleTavern 服务管理器")
            .set_level(rfd::MessageLevel::Error)
            .set_description(format!(
                "请检查程序目录是否已完整解压。免安装版需要 Microsoft Edge WebView2 Runtime，也可以运行 SimpleTavern 安装版补齐运行时。\n\n{error}"
            ))
            .show();
        std::process::exit(1);
    }
}
