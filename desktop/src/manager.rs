use crate::{profile, service::Service, updates, Event, Shared};
use serde_json::{json, Value};
use std::{
    collections::VecDeque,
    fs,
    path::PathBuf,
    sync::mpsc::{Receiver, Sender},
    thread,
};
use tauri::{AppHandle, Manager};
use tauri_plugin_opener::OpenerExt;
use velopack::UpdateInfo;

#[derive(Clone, Copy, PartialEq)]
enum End {
    Stop,
    RestartService,
    Quit,
    Upgrade,
}

pub struct ManagerState {
    app: AppHandle,
    shared: Shared,
    tx: Sender<Event>,
    content: PathBuf,
    profile: PathBuf,
    settings: profile::Settings,
    service: Option<Service>,
    phase: &'static str,
    detail: String,
    auto_open: bool,
    logs: VecDeque<Value>,
    log_id: u64,
    voices: Value,
    version: String,
    update: Value,
    found: Option<UpdateInfo>,
    end: Option<End>,
    committed: bool,
    tray_tip: bool,
}
impl ManagerState {
    pub fn run(
        app: AppHandle,
        shared: Shared,
        tx: Sender<Event>,
        rx: Receiver<Event>,
        content: PathBuf,
        profile: PathBuf,
    ) -> Result<(), String> {
        let settings = profile::read(&profile).map_err(|e| format!("管理器配置读取失败：{e}"))?;
        let version = updates::manager()
            .map(|m| m.get_current_version_as_string())
            .unwrap_or_else(|_| env!("CARGO_PKG_VERSION").into());
        let mut m = Self {
            app,
            shared,
            tx,
            content,
            profile,
            settings,
            service: None,
            phase: "first",
            detail: "聊天会在默认浏览器中打开。已有旧版数据时，可先导入。".into(),
            auto_open: !std::env::args().any(|a| a.starts_with("--resume")),
            logs: VecDeque::new(),
            log_id: 0,
            voices: json!([]),
            update: json!({}),
            version,
            found: None,
            end: None,
            committed: false,
            tray_tip: false,
        };
        if updates::manager()
            .ok()
            .and_then(|u| u.get_update_pending_restart())
            .is_some()
        {
            m.update_state("ready", "已就绪，退出时更新");
        } else {
            m.update_state("idle", "");
        }
        if m.profile.join("data/settings.json").exists() {
            m.start();
        }
        if m.update["phase"] == "idle" {
            m.action("check", &Value::Null);
        }
        m.publish();
        for event in rx {
            match event {
                Event::Action(action, opts) => m.action(&action, &opts),
                Event::Service(v) => m.signal(&v),
                Event::Exited(ok) => m.exited(ok),
                Event::Checked(result) => match result {
                    Ok(Some(info)) => {
                        let note = format!("发现新版 {}", info.TargetFullRelease.Version);
                        m.found = Some(info);
                        m.update_state("available", &note);
                    }
                    Ok(None) => m.update_state("idle", "当前已是最新版本"),
                    Err(e) => m.update_state("error", &e),
                },
                Event::Progress(n) => m.update_state("downloading", &format!("正在下载更新 {n}%")),
                Event::Downloaded(result) => match result {
                    Ok(()) => {
                        m.update_state("ready", "已就绪，退出时更新");
                        if m.end == Some(End::Quit) {
                            m.drain(End::Quit);
                        }
                    }
                    Err(e) => {
                        m.end = None;
                        m.detail.clear();
                        m.log("更新", "错误", &e);
                        m.update_state("available", &e);
                    }
                },
                Event::Imported(result) => {
                    m.phase = "first";
                    m.detail = "聊天会在默认浏览器中打开。已有旧版数据时，可先导入。".into();
                    match result {
                        Ok(true) => {
                            crate::refresh_appearance(&m.app, false);
                            m.start();
                        }
                        Ok(false) => {}
                        Err(e) => m.detail = e,
                    }
                }
                Event::Notice(note) => m.log("桌面端", "信息", &note),
            }
            m.publish();
        }
        Ok(())
    }

    fn publish(&self) {
        *self.shared.lock().unwrap() = json!({"phase":self.phase, "detail":self.detail, "url":self.url(),
            "port":self.settings.port, "apiPort":self.settings.api_port, "logs":self.logs, "voices":self.voices,
            "update":self.update, "trayTip":self.tray_tip, "waiting":self.end.is_some() && !self.committed});
    }
    fn log(&mut self, source: &str, level: &str, text: &str) {
        self.log_id += 1;
        if self.logs.len() == 500 {
            self.logs.pop_front();
        }
        self.logs.push_back(
            json!({"id":self.log_id,"time":chrono::Local::now().format("%H:%M:%S").to_string(),
            "source":source,"level":level,"text":text}),
        );
    }
    fn url(&self) -> String {
        format!("http://127.0.0.1:{}", self.settings.port)
    }
    fn pipe(&mut self, msg: Value) {
        if let Some(service) = self.service.as_mut() {
            let _ = service.send(msg);
        }
    }
    fn update_state(&mut self, phase: &str, message: &str) {
        self.update = json!({"phase":phase,"message":message,"version":self.version});
        self.pipe(json!({"action":"update_state","state":self.update}));
        if phase == "error" || phase == "ready" {
            self.log(
                "更新",
                if phase == "error" { "错误" } else { "信息" },
                message,
            );
        }
    }
    fn start(&mut self) {
        if self.service.is_some() {
            return;
        }
        self.detail.clear();
        let result = profile::write(&self.profile, &self.settings).and_then(|_| {
            Service::spawn(
                &self.content,
                &self.profile,
                self.settings.port,
                self.settings.api_port,
                &self.version,
                self.tx.clone(),
            )
        });
        match result {
            Ok(service) => {
                self.service = Some(service);
                self.phase = "starting";
                self.log("聊天服务", "信息", "正在启动本地服务");
            }
            Err(e) => self.failed(&format!("启动失败：{e}")),
        }
    }
    fn failed(&mut self, message: &str) {
        self.phase = "failed";
        self.detail = message.into();
        self.log("聊天服务", "错误", message);
    }
    fn open(&mut self) {
        if self.phase == "running" {
            if self
                .app
                .opener()
                .open_url(self.url(), None::<&str>)
                .is_err()
            {
                self.detail = "打开浏览器失败，请复制聊天地址".into();
            }
        }
    }
    fn drain(&mut self, end: End) {
        if self.committed {
            return;
        }
        self.end = Some(end);
        if end == End::Quit && self.update["phase"] == "downloading" {
            self.detail = "下载完成后退出".into();
            return;
        }
        if self.service.is_none() {
            self.finish(end);
            return;
        }
        self.phase = "waiting";
        self.detail = "正在等待生成和写入完成，可取消".into();
        if end == End::Upgrade {
            self.update_state("waiting", "正在等待当前任务完成");
        }
        self.pipe(json!({"action":"drain"}));
    }
    fn finish(&mut self, end: End) {
        self.end = None;
        self.committed = false;
        self.phase = "stopped";
        self.detail.clear();
        if end == End::RestartService {
            self.start();
            return;
        }
        if end == End::Stop {
            return;
        }
        let result = (|| {
            let m = updates::manager()?;
            if let Some(pkg) = m.get_update_pending_restart() {
                let hidden = self
                    .app
                    .get_webview_window("main")
                    .is_some_and(|w| !w.is_visible().unwrap_or(true));
                let arg = if hidden {
                    "--resume-hidden"
                } else {
                    "--resume"
                };
                m.wait_exit_then_apply_updates(pkg, true, end == End::Upgrade, [arg])?;
            }
            Ok::<(), velopack::Error>(())
        })();
        if result.is_err()
            && (end == End::Upgrade
                || self.update["phase"] == "ready"
                || self.update["phase"] == "waiting")
        {
            self.update_state("ready", "更新未应用，请检查目录权限后重试");
            self.start();
            return;
        }
        self.app.exit(0);
    }
    fn exited(&mut self, ok: bool) {
        self.service = None;
        self.voices = json!([]);
        if let Some(end) = self.end {
            if ok && self.committed {
                self.finish(end);
                return;
            }
            self.end = None;
            self.committed = false;
            if self.update["phase"] == "waiting" {
                self.update_state("ready", "已就绪，退出时更新");
            }
        }
        if self.phase != "failed" {
            self.failed("本地服务已意外退出，可重新启动");
        }
    }
    fn signal(&mut self, v: &Value) {
        match v["event"].as_str() {
            Some("ready") => {
                self.phase = "running";
                self.log("聊天服务", "信息", "已就绪，正在接受请求");
                self.pipe(json!({"action":"update_state","state":self.update}));
                self.pipe(json!({"action":"voices"}));
                if let Some(end) = self.end {
                    self.drain(end);
                } else if self.auto_open {
                    self.open();
                }
                self.auto_open = false;
            }
            Some("drained") if self.end.is_some() => {
                self.committed = true;
                self.phase = "stopping";
                self.detail = "正在关闭本地服务".into();
                self.pipe(json!({"action":"shutdown"}));
            }
            Some("port_error") => self.failed(&format!(
                "端口 {} 无法绑定，请检查占用或更换端口",
                v["port"]
            )),
            Some("failed") if self.phase != "failed" => self.failed(&format!(
                "服务启动失败（{}）",
                v["kind"].as_str().unwrap_or("异常")
            )),
            Some("voices") => self.voices = v["rows"].clone(),
            Some("appearance_changed") => {
                crate::refresh_appearance(&self.app, v["wallpaperRemoved"].as_bool() == Some(true));
            }
            Some("request") => {
                let code = v["status"].as_u64().unwrap_or(500);
                let category = v["category"].as_str().unwrap_or("本地服务");
                self.log(
                    if category == "语音" {
                        "语音"
                    } else {
                        "聊天服务"
                    },
                    if code >= 400 { "错误" } else { "信息" },
                    &format!("{category}请求 · HTTP {code}"),
                );
            }
            Some("voice_result") => {
                let note = match (v["op"].as_str(), v["state"].as_str()) {
                    (Some("health"), Some("unreachable")) => "网关连接失败",
                    (Some("health"), _) => "网关连接正常",
                    (Some("stop"), _) => "受管网关已停止",
                    (Some("start"), _) => "语音网关已就绪",
                    _ => return,
                };
                self.log(
                    "语音",
                    if v["state"] == "unreachable" {
                        "错误"
                    } else {
                        "信息"
                    },
                    note,
                );
            }
            Some("voice_error") => self.log(
                "语音",
                "错误",
                "语音操作失败，请检查网关路径、端口和运行环境",
            ),
            Some("update_action") => self.action(v["action"].as_str().unwrap_or(""), &Value::Null),
            _ => {}
        }
    }
    fn action(&mut self, name: &str, opts: &Value) {
        match name {
            "open" => self.open(),
            "start" if matches!(self.phase, "first" | "failed" | "stopped") => self.start(),
            "stop" if self.phase == "running" => self.drain(End::Stop),
            "restart_service" if self.phase == "running" => self.drain(End::RestartService),
            "quit" if self.phase != "importing" => self.drain(End::Quit),
            "restart" if self.update["phase"] == "ready" => self.drain(End::Upgrade),
            "cancel" if self.end.is_some() && !self.committed => {
                self.end = None;
                self.detail.clear();
                self.phase = if self.service.is_some() {
                    "running"
                } else {
                    "stopped"
                };
                self.pipe(json!({"action":"cancel"}));
                if self.update["phase"] == "waiting" {
                    self.update_state("ready", "已就绪，退出时更新");
                }
            }
            "ports" if self.service.is_none() && self.phase != "importing" => {
                let valid = |v: &Value| {
                    v.as_u64()
                        .and_then(|p| u16::try_from(p).ok())
                        .filter(|p| *p > 0)
                };
                if let (Some(p), Some(a)) = (valid(&opts["port"]), valid(&opts["apiPort"])) {
                    self.settings.port = p;
                    self.settings.api_port = a;
                    self.start();
                } else {
                    self.detail = "端口须为 1 至 65535 的整数".into();
                }
            }
            "voices" if self.phase == "running" => self.pipe(json!({"action":"voices"})),
            "voice" if self.phase == "running" => {
                self.pipe(json!({"action":"voice","op":opts["op"],"id":opts["id"]}))
            }
            "check"
                if matches!(
                    self.update["phase"].as_str(),
                    Some("idle" | "available" | "error")
                ) =>
            {
                self.update_state("checking", "正在检查更新");
                updates::check(self.tx.clone());
            }
            "download" if self.update["phase"] == "available" => {
                if let Some(info) = self.found.clone() {
                    self.update_state("downloading", "准备下载更新");
                    updates::download(info, self.tx.clone());
                }
            }
            "import" if self.phase == "first" => {
                self.phase = "importing";
                self.detail.clear();
                let dir = self.profile.clone();
                let tx = self.tx.clone();
                thread::spawn(move || {
                    let result = rfd::FileDialog::new()
                        .set_title("选择旧版 data 目录")
                        .pick_folder()
                        .map(|p| profile::import(&p, &dir).map(|_| true))
                        .transpose()
                        .map(|v| v.unwrap_or(false))
                        .map_err(|e| e.to_string());
                    let _ = tx.send(Event::Imported(result));
                });
            }
            "export" => {
                let logs = self.logs.clone();
                let tx = self.tx.clone();
                thread::spawn(move || {
                    if let Some(p) = rfd::FileDialog::new()
                        .set_file_name("SimpleTavern.log")
                        .save_file()
                    {
                        let lines = logs
                            .iter()
                            .map(|v| {
                                ["time", "source", "level", "text"]
                                    .map(|k| v[k].as_str().unwrap_or(""))
                                    .join("  ")
                            })
                            .collect::<Vec<_>>()
                            .join("\r\n");
                        let note = if fs::write(p, lines).is_ok() {
                            "已导出运行日志"
                        } else {
                            "日志导出失败"
                        };
                        let _ = tx.send(Event::Notice(note.into()));
                    }
                });
            }
            "close" => {
                if self.settings.tray_tip_seen {
                    if let Some(w) = self.app.get_webview_window("main") {
                        let _ = w.hide();
                    }
                } else {
                    self.tray_tip = true;
                }
            }
            "hide" => {
                self.settings.tray_tip_seen = true;
                self.tray_tip = false;
                if let Err(e) = profile::write(&self.profile, &self.settings) {
                    self.detail = e.to_string();
                }
                if let Some(w) = self.app.get_webview_window("main") {
                    let _ = w.hide();
                }
            }
            _ => {}
        }
    }
}
