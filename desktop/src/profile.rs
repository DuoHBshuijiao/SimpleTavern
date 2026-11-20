use serde::{Deserialize, Serialize};
use std::{
    fs, io,
    path::{Path, PathBuf},
};

#[derive(Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    pub port: u16,
    pub api_port: u16,
    pub tray_tip_seen: bool,
}
impl Default for Settings {
    fn default() -> Self {
        Self {
            port: 9081,
            api_port: 9091,
            tray_tip_seen: false,
        }
    }
}

pub fn profile_dir(content: &Path) -> io::Result<PathBuf> {
    let root = content.parent().unwrap_or(content);
    if root.join(".portable").is_file() {
        return Ok(root.to_path_buf());
    }
    let local =
        std::env::var_os("LOCALAPPDATA").ok_or_else(|| io::Error::other("找不到本地用户目录"))?;
    let name = if option_env!("SIMPLETAVERN_LOCAL_TEST_FEED").is_some() {
        "SimpleTavernDesktopQA.User"
    } else {
        "SimpleTavern.User"
    };
    Ok(PathBuf::from(local).join(name))
}
pub fn read(dir: &Path) -> io::Result<Settings> {
    match fs::read(dir.join("manager.json")) {
        Ok(bytes) => Ok(serde_json::from_slice(&bytes)?),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(Settings::default()),
        Err(e) => Err(e),
    }
}
pub fn write(dir: &Path, settings: &Settings) -> io::Result<()> {
    use io::Write;
    fs::create_dir_all(dir)?;
    let mut tmp = tempfile::NamedTempFile::new_in(dir)?;
    tmp.write_all(&serde_json::to_vec(settings)?)?;
    tmp.as_file().sync_all()?;
    tmp.persist(dir.join("manager.json"))?;
    Ok(())
}

fn copy_tree(src: &Path, dest: &Path) -> io::Result<()> {
    use std::os::windows::fs::MetadataExt;
    fs::create_dir_all(dest)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let meta = fs::symlink_metadata(entry.path())?;
        if meta.file_attributes() & 0x400 != 0 {
            return Err(io::Error::other("目录含有链接，请先导出为普通数据目录"));
        }
        let target = dest.join(entry.file_name());
        if meta.is_dir() {
            copy_tree(&entry.path(), &target)?;
        } else {
            fs::copy(entry.path(), target)?;
        }
    }
    Ok(())
}
pub fn import(src: &Path, profile: &Path) -> io::Result<()> {
    let src = src.canonicalize()?;
    if !src.join("settings.json").is_file() && !src.join("characters").is_dir() {
        return Err(io::Error::other("请选择旧版 data 文件夹"));
    }
    // The install profile can be new. Check its existing parent before
    // creating anything, including when the chosen source contains it.
    let ancestor = profile
        .ancestors()
        .find(|p| p.exists())
        .ok_or_else(|| io::Error::other("找不到目标目录"))?;
    if ancestor.canonicalize()?.starts_with(&src) {
        return Err(io::Error::other("源目录与目标重叠"));
    }
    fs::create_dir_all(profile)?;
    let target = profile.join("data");
    if target.exists() && fs::read_dir(&target)?.next().is_some() {
        return Err(io::Error::other("目标数据目录已有内容"));
    }
    let staging = tempfile::Builder::new()
        .prefix("import-")
        .tempdir_in(profile)?;
    let data = staging.path().join("data");
    copy_tree(&src, &data)?;
    if target.exists() {
        fs::remove_dir(&target)?;
    }
    fs::rename(data, target)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn import_copies_nested_files_and_preserves_existing_data() -> io::Result<()> {
        let tmp = tempfile::tempdir()?;
        let old = tmp.path().join("旧版/data");
        let profile = tmp.path().join("免安装");
        fs::create_dir_all(old.join("characters"))?;
        fs::write(old.join("characters/test.json"), b"first")?;
        import(&old, &profile)?;
        fs::write(old.join("characters/test.json"), b"second")?;
        assert!(import(&old, &profile).is_err());
        assert_eq!(
            fs::read(profile.join("data/characters/test.json"))?,
            b"first"
        );
        assert_eq!(fs::read(old.join("characters/test.json"))?, b"second");
        assert!(import(&old, &old.join("nested")).is_err());
        assert!(!old.join("nested").exists());
        Ok(())
    }
}
