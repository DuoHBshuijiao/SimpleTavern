#![cfg_attr(windows, windows_subsystem = "windows")]
mod manager;
mod profile;
mod service;
mod updates;

use serde_json::{json, Value};
use std::sync::{mpsc, Arc, Mutex};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
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
fn reveal(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}
fn main() {
    velopack::VelopackApp::build()
        .set_auto_apply_on_startup(false)
        .run();
    let result = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| reveal(app)))
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![snapshot, action])
        .setup(|app| {
            let (tx, rx) = mpsc::channel();
            let view = Arc::new(Mutex::new(json!({"phase":"loading"})));
            app.manage(Desktop {
                view: view.clone(),
                tx: tx.clone(),
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
            if !std::env::args().any(|a| a == "--resume-hidden") {
                app.get_webview_window("main").unwrap().show()?;
            }
            std::thread::spawn(move || {
                if let Err(detail) =
                    manager::ManagerState::run(handle.clone(), view.clone(), tx, rx)
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
