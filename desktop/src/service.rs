use crate::Event;
use serde_json::Value;
use std::{
    io::{BufRead, BufReader, Write},
    os::windows::process::CommandExt,
    path::Path,
    process::{ChildStdin, Command, Stdio},
    sync::mpsc::Sender,
    thread,
};

use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use windows_sys::Win32::System::JobObjects::*;

fn process_job(child: &std::process::Child) -> std::io::Result<OwnedHandle> {
    // The manager alone owns this handle. Closing it also reaps nested voice workers.
    unsafe {
        let raw = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if raw.is_null() {
            return Err(std::io::Error::last_os_error());
        }
        let job = OwnedHandle::from_raw_handle(raw);
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if SetInformationJobObject(
            raw,
            JobObjectExtendedLimitInformation,
            (&info as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
            std::mem::size_of_val(&info) as u32,
        ) == 0
            || AssignProcessToJobObject(raw, child.as_raw_handle()) == 0
        {
            return Err(std::io::Error::last_os_error());
        }
        Ok(job)
    }
}
pub struct Service {
    input: ChildStdin,
    _job: OwnedHandle,
}
impl Service {
    pub fn spawn(
        content: &Path,
        profile: &Path,
        port: u16,
        api_port: u16,
        version: &str,
        tx: Sender<Event>,
    ) -> std::io::Result<Self> {
        let mut child = Command::new(content.join("service/TavernService.exe"))
            .current_dir(content)
            .arg("--port")
            .arg(port.to_string())
            .arg("--api-port")
            .arg(api_port.to_string())
            .arg("--web")
            .arg(content.join("web"))
            .arg("--version")
            .arg(version)
            .env("SIMPLETAVERN_DATA_DIR", profile.join("data"))
            .env("PYTHONIOENCODING", "utf-8")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .creation_flags(0x08000000)
            .spawn()?;
        let job = process_job(&child).inspect_err(|_| {
            let _ = child.kill();
            let _ = child.wait();
        })?;
        let input = child.stdin.take().unwrap();
        let output = child.stdout.take().unwrap();
        thread::spawn(move || {
            for line in BufReader::new(output).lines().map_while(Result::ok) {
                if let Ok(value) = serde_json::from_str::<Value>(&line) {
                    let _ = tx.send(Event::Service(value));
                }
            }
            let success = child.wait().map(|s| s.success()).unwrap_or(false);
            let _ = tx.send(Event::Exited(success));
        });
        Ok(Self { input, _job: job })
    }
    pub fn send(&mut self, msg: Value) -> std::io::Result<()> {
        serde_json::to_writer(&mut self.input, &msg)?;
        self.input.write_all(b"\n")?;
        self.input.flush()
    }
}
