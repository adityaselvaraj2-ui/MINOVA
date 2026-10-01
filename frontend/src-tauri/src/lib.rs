// MineTrace desktop shell: spawns the packaged FastAPI backend sidecar
// (PyInstaller single-file exe) on launch, waits for /api/v1/health, then
// shows the window; kills the backend's whole process tree on exit.
use std::sync::Mutex;

use tauri::{Manager, RunEvent, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

// Must match the frontend's API_BASE (src/api/client.ts hardcodes 19823).
const BACKEND_PORT: u16 = 19823;
const SIDECAR_NAME: &str = "minetrace-backend";
const SIDECAR_IMAGE: &str = "minetrace-backend-x86_64-pc-windows-msvc.exe";

#[derive(Default)]
struct BackendChild(Mutex<Option<CommandChild>>);

fn spawn_backend(app: &tauri::AppHandle) -> Result<(), String> {
    let sidecar = app
        .shell()
        .sidecar(SIDECAR_NAME)
        .map_err(|e| format!("sidecar resolution failed: {e}"))?;

    let (mut rx, child) = sidecar
        .args(["--port", &BACKEND_PORT.to_string()])
        .spawn()
        .map_err(|e| format!("sidecar spawn failed: {e}"))?;

    // Log sidecar output while it runs; exit the pump when it terminates.
    std::thread::spawn(move || {
        while let Some(event) = rx.blocking_recv() {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[backend] {}", String::from_utf8_lossy(&line))
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[backend] {}", String::from_utf8_lossy(&line))
                }
                CommandEvent::Terminated(status) => {
                    eprintln!("[backend] terminated: {:?}", status.code);
                    break;
                }
                _ => {}
            }
        }
    });

    // Stash the child handle so RunEvent::Exit can kill it (and its tree).
    let state: State<BackendChild> = app.state();
    *state.0.lock().unwrap() = Some(child);

    // Health-wait: PyInstaller onefile extracts + seeds on first boot, so
    // allow up to 120s before surfacing the window anyway.
    wait_for_health(BACKEND_PORT, 120);
    Ok(())
}

fn wait_for_health(port: u16, timeout_secs: u64) {
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(timeout_secs);
    let url = format!("http://127.0.0.1:{port}/api/v1/health");
    loop {
        if std::time::Instant::now() > deadline {
            eprintln!("[backend] health-wait timed out on port {port}");
            return;
        }
        // Minimal HTTP/1.0 GET via std::net — no extra crates needed.
        use std::io::{Read, Write};
        use std::net::TcpStream;
        if let Ok(mut stream) = TcpStream::connect(("127.0.0.1", port)) {
            let req = format!("GET /api/v1/health HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n");
            if stream.write_all(req.as_bytes()).is_ok() && stream.read(&mut [0u8; 16]).is_ok() {
                println!("[backend] healthy on port {port}");
                return;
            }
        }
        std::thread::sleep(std::time::Duration::from_millis(700));
    }
}

fn kill_backend_tree() {
    // taskkill /T covers the onefile bootloader's child process; /F forces.
    // The bundle renames the sidecar (triple suffix stripped), so try both
    // image names — dev keeps the triple, installed uses the short one.
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    use std::os::windows::process::CommandExt;
    for image in ["minetrace-backend.exe", SIDECAR_IMAGE] {
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/IM", image])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BackendChild::default())
        .setup(|app| {
            // Keep the window hidden until the backend is ready to serve.
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.hide();
            }
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                if let Err(e) = spawn_backend(&handle) {
                    eprintln!("[backend] {e}");
                }
                // Show the window regardless, so a failed boot is still visible.
                if let Some(win) = handle.get_webview_window("main") {
                    let _ = win.show();
                    let _ = win.set_focus();
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|_app_handle, event| {
        if let RunEvent::Exit = event {
            kill_backend_tree();
        }
    });
}
