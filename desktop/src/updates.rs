use crate::Event;
use std::{
    sync::mpsc::{self, Sender},
    thread,
};
use velopack::{
    sources::{FileSource, GithubSource},
    UpdateCheck, UpdateInfo, UpdateManager,
};

pub fn manager() -> Result<UpdateManager, velopack::Error> {
    if let Some(dir) = option_env!("SIMPLETAVERN_LOCAL_TEST_FEED") {
        return UpdateManager::new(FileSource::new(dir), None, None);
    }
    UpdateManager::new(
        GithubSource::new("https://github.com/DuoHBshuijiao/SimpleTavern", None, false),
        None,
        None,
    )
}
pub fn check(tx: Sender<Event>) {
    thread::spawn(move || {
        let result = manager()
            .and_then(|m| m.check_for_updates())
            .map(|check| match check {
                UpdateCheck::UpdateAvailable(info) => Some(*info),
                _ => None,
            })
            .map_err(|_| "检查失败，请检查网络后重试".to_string());
        let _ = tx.send(Event::Checked(result));
    });
}
pub fn download(info: UpdateInfo, tx: Sender<Event>) {
    thread::spawn(move || {
        let (progress, rx) = mpsc::channel();
        let out = tx.clone();
        let relay = thread::spawn(move || {
            for value in rx {
                let _ = out.send(Event::Progress(value));
            }
        });
        let result = manager()
            .and_then(|m| m.download_updates(&info, Some(progress)))
            .map_err(|_| "下载或校验失败，请检查网络、磁盘空间及写入权限后重试".to_string());
        let _ = relay.join();
        let _ = tx.send(Event::Downloaded(result));
    });
}
