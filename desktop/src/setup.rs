#![cfg_attr(not(test), windows_subsystem = "windows")]

use rfd::{FileDialog, MessageButtons, MessageDialog, MessageDialogResult, MessageLevel};
use std::{
    env,
    ffi::OsString,
    fs, io,
    os::windows::fs::MetadataExt,
    path::{self, Component, Path, PathBuf, Prefix},
    process::{Command, ExitCode},
    thread,
    time::{Duration, Instant},
};
use velopack::locator::create_config_from_root_dir;
use windows_sys::Win32::{
    Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS, HANDLE},
    System::Threading::CreateMutexW,
};
use winreg::{enums::HKEY_CURRENT_USER, RegKey};

const TITLE: &str = "安装 SimpleTavern";
const INSTALL: &str = "安装";
const BROWSE: &str = "更改目录";
const CANCEL: &str = "取消";
const PACKAGE_ID: &str = match option_env!("SIMPLETAVERN_SETUP_PACK_ID") {
    Some(id) => id,
    None => "SimpleTavern",
};
const REPARSE_POINT: u32 = 0x400;

#[cfg(embedded_setup)]
static PAYLOAD: &[u8] = include_bytes!(env!("SIMPLETAVERN_SETUP_PAYLOAD"));
#[cfg(not(embedded_setup))]
static PAYLOAD: &[u8] = &[];

type SetupResult<T> = Result<T, String>;

#[derive(Default)]
struct Options {
    destination: Option<PathBuf>,
    silent: bool,
    help: bool,
    forwarded: Vec<OsString>,
}

impl Options {
    fn parse(args: Vec<OsString>) -> SetupResult<Self> {
        let mut options = Self::default();
        let mut args = args.into_iter();
        while let Some(arg) = args.next() {
            let flag = arg.to_str().unwrap_or_default();
            match flag {
                "--" => {
                    options.forwarded.push(arg);
                    options.forwarded.extend(args);
                    break;
                }
                "-s" | "--silent" => options.silent = true,
                "-h" | "--help" => options.help = true,
                "-v" | "--verbose" => options.forwarded.push("--verbose".into()),
                "-l" | "--log" => options
                    .forwarded
                    .extend([arg, option_value(&mut args, "--log")?]),
                "-t" | "--installto" => {
                    options.set_destination(option_value(&mut args, "--installto")?.into())?
                }
                _ => {
                    if let Some(value) = flag.strip_prefix("--installto=") {
                        options.set_destination(value.into())?;
                    } else if flag.starts_with("--log=") {
                        options.forwarded.push(arg);
                    } else {
                        return Err(format!("无法识别安装选项 {}。", arg.to_string_lossy()));
                    }
                }
            }
        }
        Ok(options)
    }

    fn set_destination(&mut self, value: PathBuf) -> SetupResult<()> {
        if value.as_os_str().is_empty() || self.destination.is_some() {
            return Err("请为 --installto 指定一个安装目录。".into());
        }
        self.destination = Some(value);
        Ok(())
    }
}

fn option_value(args: &mut impl Iterator<Item = OsString>, name: &str) -> SetupResult<OsString> {
    args.next()
        .filter(|value| !value.is_empty() && !value.as_encoded_bytes().starts_with(b"-"))
        .ok_or_else(|| format!("安装选项 {name} 缺少参数。"))
}

fn absolute_path(input: &Path) -> SetupResult<PathBuf> {
    if !is_supported_path(input) {
        return Err("请选择完整的 Windows 文件夹路径，例如 D:\\应用\\酒馆。".into());
    }
    let absolute = path::absolute(input).map_err(|e| path_error(input, e))?;
    if !is_supported_path(&absolute) {
        return Err(format!("无效的安装目录 {}。", input.display()));
    }
    Ok(absolute)
}

fn is_supported_path(path: &Path) -> bool {
    let prefix = path.components().next();
    path.is_absolute()
        && match prefix {
            Some(Component::Prefix(p)) => match p.kind() {
                Prefix::Disk(_) | Prefix::UNC(..) => true,
                Prefix::VerbatimDisk(_) | Prefix::VerbatimUNC(..) => !path
                    .components()
                    .any(|c| matches!(c, Component::ParentDir | Component::CurDir)),
                _ => false,
            },
            _ => false,
        }
}

fn destination_path(input: &Path) -> SetupResult<PathBuf> {
    let mut path = absolute_path(input)?;
    if path.parent().is_none() {
        path.push(PACKAGE_ID);
    }
    Ok(path)
}

fn path_error(path: &Path, error: io::Error) -> String {
    format!("无法访问目录 {}。\n{error}", path.display())
}

fn registered_install() -> SetupResult<Option<PathBuf>> {
    let key = format!(r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{PACKAGE_ID}");
    let location: io::Result<OsString> = RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey(key)
        .and_then(|key| key.get_value("InstallLocation"));
    let location = match location {
        Ok(location) => location,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(format!("无法读取已有安装的位置。\n{e}")),
    };
    let Ok(path) = absolute_path(Path::new(&location)) else {
        return Ok(None);
    };
    let config = create_config_from_root_dir(&path);
    let valid = !config.IsPortable
        && config.UpdateExePath.is_file()
        && config.load_manifest().is_ok_and(|app| app.id == PACKAGE_ID);
    Ok(valid.then_some(path))
}

fn existing_ancestor(path: &Path) -> SetupResult<(&Path, fs::Metadata)> {
    for ancestor in path.ancestors() {
        match fs::symlink_metadata(ancestor) {
            Ok(metadata) => return Ok((ancestor, metadata)),
            Err(e) if e.kind() == io::ErrorKind::NotFound => continue,
            Err(e) => return Err(path_error(ancestor, e)),
        }
    }
    Err(format!(
        "找不到安装目录所在的磁盘或共享文件夹 {}。",
        path.display()
    ))
}

fn resolve_from(path: &Path, ancestor: &Path) -> SetupResult<PathBuf> {
    let parent = fs::canonicalize(ancestor).map_err(|e| path_error(ancestor, e))?;
    let suffix = path.strip_prefix(ancestor).expect("ancestor of path");
    Ok(if suffix.as_os_str().is_empty() {
        parent
    } else {
        parent.join(suffix)
    })
}

fn same_path(first: &Path, second: &Path) -> bool {
    first == second || first.as_os_str().eq_ignore_ascii_case(second.as_os_str())
}

fn paths_overlap(first: &Path, second: &Path) -> bool {
    first.ancestors().any(|p| same_path(p, second))
        || second.ancestors().any(|p| same_path(p, first))
}

fn check_destination(path: &Path, installed: Option<&Path>, profile: &Path) -> SetupResult<()> {
    check_destination_with_mode(path, installed, profile, false)
}

fn check_destination_with_mode(
    path: &Path,
    installed: Option<&Path>,
    profile: &Path,
    allow_relocate: bool,
) -> SetupResult<()> {
    let (ancestor, metadata) = existing_ancestor(path)?;
    let resolved = resolve_from(path, ancestor)?;
    let exists = ancestor == path;
    if resolved.parent().is_none() || (exists && metadata.file_attributes() & REPARSE_POINT != 0) {
        return Err("请选择普通文件夹作为安装目录。".into());
    }
    if !fs::metadata(ancestor)
        .map_err(|e| path_error(ancestor, e))?
        .is_dir()
    {
        return Err(format!(
            "安装路径 {} 指向文件，请选择文件夹。",
            path.display()
        ));
    }
    let profile = resolve_from(profile, existing_ancestor(profile)?.0)?;
    if paths_overlap(&resolved, &profile) {
        return Err("安装目录与用户数据目录重叠，请选择其他文件夹。".into());
    }
    let mut requires_empty = true;
    if let Some(installed) = installed {
        let installed = resolve_from(installed, installed)?;
        if same_path(&installed, &resolved) {
            requires_empty = false;
        } else if !allow_relocate {
            return Err(
                "SimpleTavern 已安装。若要更改安装目录，请直接运行安装程序点击「更改目录」，或先卸载后再安装（用户数据会保留）。"
                    .into(),
            );
        } else if paths_overlap(&resolved, &installed) {
            return Err("新安装目录不能与原安装目录重叠，请选择其他空文件夹。".into());
        }
    }
    if requires_empty && exists {
        let mut entries = fs::read_dir(path).map_err(|e| path_error(path, e))?;
        if entries.next().is_some() {
            return Err(format!(
                "安装目录 {} 已有内容，请选择空文件夹。",
                path.display()
            ));
        }
    }
    // Probe directory creation for new paths and writes for existing ones.
    // Windows can allow creating folders at a drive root while denying new files there.
    if exists {
        tempfile::NamedTempFile::new_in(path).map_err(|e| path_error(path, e))?;
    } else {
        tempfile::Builder::new()
            .prefix("SimpleTavern-setup-")
            .tempdir_in(ancestor)
            .map_err(|e| path_error(ancestor, e))?;
    }
    Ok(())
}

fn show_error(message: &str) {
    MessageDialog::new()
        .set_title(TITLE)
        .set_level(MessageLevel::Error)
        .set_description(message)
        .show();
}

fn choose_destination(
    mut destination: PathBuf,
    installed: Option<&Path>,
    profile: &Path,
) -> Option<PathBuf> {
    let data_dir = profile.join("data");
    loop {
        let is_relocating = installed.is_some_and(|old| {
            let old_res = resolve_from(old, old).ok();
            let dst_res = existing_ancestor(&destination)
                .ok()
                .and_then(|(anc, _)| resolve_from(&destination, anc).ok());
            match (old_res, dst_res) {
                (Some(a), Some(b)) => !same_path(&a, &b),
                _ => !same_path(old, &destination),
            }
        });
        let description = match (installed, is_relocating) {
            (Some(old), true) => format!(
                "将安装到新目录，并自动移除原程序目录（用户数据保留不变，不会丢失）。\n\n新安装目录\n{}\n\n原安装目录（将被移除）\n{}\n\n用户数据目录（保留不变）\n{}",
                destination.display(),
                old.display(),
                data_dir.display()
            ),
            (Some(_), false) => format!(
                "将重新安装到现有目录（用户数据保留在单独目录，不会丢失）。\n如需换盘或换目录，请点击「更改目录」。\n\n安装目录\n{}\n\n用户数据目录\n{}",
                destination.display(),
                data_dir.display()
            ),
            (None, _) => format!(
                "安装目录\n{}\n\n用户数据目录（卸载、重装或更改目录时均会保留）\n{}",
                destination.display(),
                data_dir.display()
            ),
        };
        let buttons =
            MessageButtons::YesNoCancelCustom(INSTALL.into(), BROWSE.into(), CANCEL.into());
        let choice = MessageDialog::new()
            .set_title(TITLE)
            .set_description(description)
            .set_buttons(buttons)
            .show();
        match choice {
            MessageDialogResult::Custom(button) if button == INSTALL => {
                match check_destination_with_mode(&destination, installed, profile, true) {
                    Ok(()) => return Some(destination),
                    Err(e) => show_error(&e),
                }
            }
            MessageDialogResult::Custom(button) if button == BROWSE => {
                let picker = FileDialog::new().set_title("选择 SimpleTavern 安装目录");
                let picker = match destination.ancestors().find(|path| path.is_dir()) {
                    Some(directory) => picker.set_directory(directory),
                    None => picker,
                };
                if let Some(picked) = picker.pick_folder() {
                    match destination_path(&picked) {
                        Ok(path) => destination = path,
                        Err(e) => show_error(&e),
                    }
                }
            }
            _ => return None,
        }
    }
}

struct SetupLock(HANDLE);

impl SetupLock {
    fn acquire() -> SetupResult<Self> {
        let name: Vec<_> = format!(r"Local\{PACKAGE_ID}-Setup")
            .encode_utf16()
            .chain([0])
            .collect();
        // The handle keeps the named mutex alive for the lifetime of this setup.
        let handle = unsafe { CreateMutexW(std::ptr::null(), 0, name.as_ptr()) };
        if handle.is_null() {
            return Err(format!("无法启动安装。\n{}", io::Error::last_os_error()));
        }
        let already_running = unsafe { GetLastError() } == ERROR_ALREADY_EXISTS;
        let lock = Self(handle);
        if already_running {
            return Err("已有一个 SimpleTavern 安装程序正在运行。".into());
        }
        Ok(lock)
    }
}

impl Drop for SetupLock {
    fn drop(&mut self) {
        unsafe { CloseHandle(self.0) };
    }
}

fn run_velo_setup(destination: Option<&Path>, options: Options) -> SetupResult<ExitCode> {
    if PAYLOAD.is_empty() {
        return Err("安装包缺少程序文件，请重新下载安装包。".into());
    }
    let temp = tempfile::Builder::new()
        .prefix("SimpleTavernSetup-")
        .tempdir()
        .map_err(|e| format!("无法创建安装所需的临时目录。\n{e}"))?;
    let setup = temp.path().join("VelopackSetup.exe");
    fs::write(&setup, PAYLOAD).map_err(|e| format!("无法解包安装程序。\n{e}"))?;
    let mut command = Command::new(setup);
    if let Some(path) = destination {
        command.arg("--installto").arg(path);
    }
    if options.help {
        command.arg("--help");
    }
    if options.silent {
        command.arg("--silent");
    }
    let status = command
        .args(options.forwarded)
        .status()
        .map_err(|e| format!("无法运行安装程序。\n{e}"))?;
    Ok(status
        .code()
        .and_then(|code| u8::try_from(code).ok())
        .map_or(ExitCode::FAILURE, ExitCode::from))
}

fn uninstall_existing(old_dir: &Path) -> SetupResult<()> {
    let updater = old_dir.join("Update.exe");
    if !updater.is_file() {
        return Err(format!("找不到原安装目录的卸载程序 {}。", updater.display()));
    }
    let status = Command::new(&updater)
        .args(["uninstall", "--silent"])
        .status()
        .map_err(|e| format!("无法卸载原安装目录。\n{e}"))?;
    if !status.success() {
        return Err("移除原安装目录失败，请先退出正在运行的 SimpleTavern 后重试。".into());
    }
    let uninstall_key = format!(r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{PACKAGE_ID}");
    let deadline = Instant::now() + Duration::from_secs(15);
    while Instant::now() < deadline {
        let reg_gone = matches!(
            RegKey::predef(HKEY_CURRENT_USER).open_subkey(&uninstall_key),
            Err(e) if e.kind() == io::ErrorKind::NotFound
        );
        if reg_gone && registered_install()?.is_none() {
            break;
        }
        thread::sleep(Duration::from_millis(200));
    }
    Ok(())
}

fn run(args: Vec<OsString>) -> SetupResult<ExitCode> {
    let options = Options::parse(args)?;
    if options.help {
        return run_velo_setup(None, options);
    }
    let _lock = SetupLock::acquire()?;
    let local = env::var_os("LOCALAPPDATA").ok_or_else(|| "找不到本地用户目录。".to_owned())?;
    let local = absolute_path(Path::new(&local))?;
    let profile = local.join(format!("{PACKAGE_ID}.User"));
    let installed = registered_install()?;
    let default = installed.clone().unwrap_or_else(|| local.join(PACKAGE_ID));
    let destination = if options.silent || options.destination.is_some() {
        let path = match &options.destination {
            Some(input) => destination_path(input)?,
            None => default,
        };
        check_destination(&path, installed.as_deref(), &profile)?;
        installed.unwrap_or(path)
    } else if let Some(path) = choose_destination(default, installed.as_deref(), &profile) {
        if let Some(old_dir) = installed.as_deref() {
            let old_resolved = resolve_from(old_dir, old_dir)?;
            let dest_resolved = resolve_from(&path, existing_ancestor(&path)?.0)?;
            if !same_path(&old_resolved, &dest_resolved) {
                uninstall_existing(old_dir)?;
            }
        }
        path
    } else {
        return Ok(ExitCode::SUCCESS);
    };
    run_velo_setup(Some(&destination), options)
}

fn main() -> ExitCode {
    let args: Vec<_> = env::args_os().skip(1).collect();
    let silent = args
        .iter()
        .take_while(|arg| *arg != "--")
        .any(|arg| arg == "--silent" || arg == "-s");
    match run(args) {
        Ok(code) => code,
        Err(message) => {
            if silent {
                eprintln!("{message}");
            } else {
                show_error(&message);
            }
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_roots_get_a_subdirectory() {
        let expected = Path::new(r"D:\").join(PACKAGE_ID);
        for root in [r"D:\", "D:/", r"D:\Apps\.."] {
            assert_eq!(destination_path(Path::new(root)).unwrap(), expected);
        }
        let custom = Path::new(r"D:\自选 安装目录");
        assert_eq!(destination_path(custom).unwrap(), custom);
        let share = Path::new(r"\\server\share\");
        assert_eq!(destination_path(share).unwrap(), share.join(PACKAGE_ID));
        assert!(destination_path(Path::new(r"D:relative")).is_err());
        assert!(destination_path(Path::new(r"\\.\NUL")).is_err());
    }

    #[test]
    fn preserves_unrelated_files_and_rejects_profile_overlap() {
        let temp = tempfile::tempdir().unwrap();
        let destination = temp.path().join("program");
        let profile = temp.path().join("profile");
        assert!(check_destination(&destination, None, &profile).is_ok());
        assert!(!destination.exists());
        fs::create_dir(&destination).unwrap();
        assert!(check_destination(&destination, None, &profile).is_ok());
        let marker = destination.join("keep.txt");
        fs::write(&marker, b"keep").unwrap();
        assert!(check_destination(&destination, None, &profile).is_err());
        assert_eq!(fs::read(marker).unwrap(), b"keep");
        assert!(check_destination(&profile, None, &profile).is_err());
        assert!(check_destination(&profile.join("nested"), None, &profile).is_err());
    }
}
