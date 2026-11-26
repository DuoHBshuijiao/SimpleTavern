use serde::Serialize;
use serde_json::Value;
use std::{fs, io, path::Path};

#[derive(Clone, Copy, Default, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Mode {
    System,
    Background,
    Light,
    #[default]
    Dark,
}

#[derive(Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Appearance {
    pub theme_id: &'static str,
    pub mode: Mode,
    pub wallpaper: Option<String>,
}

impl Default for Appearance {
    fn default() -> Self {
        Self::from_settings(&Value::Null)
    }
}

impl Appearance {
    pub fn read(profile: &Path) -> io::Result<Self> {
        let bytes = fs::read(profile.join("data/settings.json"))?;
        Ok(Self::from_settings(&serde_json::from_slice(&bytes)?))
    }

    fn from_settings(settings: &Value) -> Self {
        let theme_id = match settings["themeId"].as_str() {
            Some("blue" | "dark") => "blue",
            Some("green" | "light") => "green",
            Some("teal") => "teal",
            Some("violet") => "violet",
            Some("amber") => "amber",
            Some("sunset") => "sunset",
            _ => "rose",
        };
        let mode = match settings["themeMode"].as_str() {
            Some("light") => Mode::Light,
            Some("system") => Mode::System,
            Some("background") => Mode::Background,
            _ => Mode::Dark,
        };
        let wallpaper = settings["pageBackgroundImage"]
            .as_str()
            .map(str::trim)
            .filter(|name| {
                mode == Mode::Background
                    && settings["pageBackgroundOpacity"].as_f64().unwrap_or(1.0) > 0.0
                    && valid_image_name(name)
            })
            .map(str::to_owned);
        Self {
            theme_id,
            mode,
            wallpaper,
        }
    }
}

fn valid_image_name(name: &str) -> bool {
    name.bytes()
        .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
        && name.rsplit_once('.').is_some_and(|(stem, ext)| {
            !stem.is_empty()
                && matches!(
                    ext.to_ascii_lowercase().as_str(),
                    "png" | "jpg" | "jpeg" | "webp" | "gif"
                )
        })
}

pub fn read_wallpaper(profile: &Path, name: &str) -> io::Result<Vec<u8>> {
    let directory = profile.join("data/page_backgrounds").canonicalize()?;
    let image = directory.join(name).canonicalize()?;
    if image.parent() != Some(directory.as_path()) || !image.is_file() {
        return Err(io::Error::other("无效的背景图片"));
    }
    fs::read(image)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn reads_legacy_theme_and_defaults_fields_independently() {
        assert_eq!(Appearance::default().theme_id, "rose");
        let old = Appearance::from_settings(&json!({"themeId": "light", "themeMode": null}));
        assert_eq!(old.theme_id, "green");
        assert!(old.mode == Mode::Dark);
        let partial = Appearance::from_settings(&json!({"themeId": false, "themeMode": "light"}));
        assert_eq!(partial.theme_id, "rose");
        assert!(partial.mode == Mode::Light);
    }

    #[test]
    fn only_uses_visible_profile_images_in_background_mode() {
        let settings = |mode, name, opacity| {
            Appearance::from_settings(&json!({
                "themeMode": mode, "pageBackgroundImage": name, "pageBackgroundOpacity": opacity,
                "webgpuBackgroundEnabled": true
            }))
        };
        assert_eq!(
            settings("background", " snow.WEBP ", 0.5)
                .wallpaper
                .as_deref(),
            Some("snow.WEBP")
        );
        assert!(settings("background", "snow.webp", 0.0).wallpaper.is_none());
        assert!(settings("background", "../snow.webp", 1.0)
            .wallpaper
            .is_none());
        assert!(settings("light", "snow.webp", 1.0).wallpaper.is_none());
    }
}
