fn main() {
    tauri_build::build();
    println!("cargo:rustc-check-cfg=cfg(embedded_setup)");
    if std::env::var_os("CARGO_FEATURE_SETUP").is_some() {
        println!("cargo:rerun-if-env-changed=SIMPLETAVERN_SETUP_PAYLOAD");
        if std::env::var_os("SIMPLETAVERN_SETUP_PAYLOAD").is_some() {
            println!("cargo:rustc-cfg=embedded_setup");
        }
    }
}
