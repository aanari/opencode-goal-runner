use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::Command;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use rusqlite::{Connection, params};

#[test]
fn cli_uses_env_over_config_against_local_server() {
    let server = Server::start();
    let config = unique_path("config", "toml");
    std::fs::write(&config, "base_url = 'http://127.0.0.1:1'\n").unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_opencode-goal-runner"))
        .arg("--config")
        .arg(&config)
        .arg("doctor")
        .arg("--skip-model-check")
        .arg("--target-dir")
        .arg(std::env::temp_dir())
        .env("OPENCODE_GOAL_BASE_URL", &server.base_url)
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("ok /session/status"));
    std::fs::remove_file(config).unwrap();
}

#[test]
fn cli_version_smoke_covers_binary_entrypoint() {
    let output = Command::new(env!("CARGO_BIN_EXE_opencode-goal-runner"))
        .arg("--version")
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout).contains("opencode-goal-runner"));
}

#[test]
fn cli_logs_show_injection_details() {
    let db = std::env::temp_dir().join(format!(
        "opencode-goal-runner-cli-logs-{}.sqlite3",
        unique_id()
    ));
    let create = Command::new(env!("CARGO_BIN_EXE_opencode-goal-runner"))
        .arg("--db")
        .arg(&db)
        .arg("--config")
        .arg(std::env::temp_dir().join("missing-opencode-goal-runner-config.toml"))
        .arg("create")
        .arg("--session")
        .arg("ses_logs")
        .arg("--objective")
        .arg("log check")
        .output()
        .unwrap();
    assert!(
        create.status.success(),
        "{}",
        String::from_utf8_lossy(&create.stderr)
    );
    let stdout = String::from_utf8_lossy(&create.stdout);
    let goal_id = stdout
        .lines()
        .find_map(|line| line.strip_prefix("created goal "))
        .unwrap()
        .to_string();

    Connection::open(&db)
        .unwrap()
        .execute(
            "INSERT INTO injections (
                injection_id,
                goal_id,
                session_id,
                status,
                created_at_ms,
                updated_at_ms,
                pre_message_id,
                pre_assistant_message_id,
                pre_assistant_count,
                submitted_at_ms,
                completed_at_ms,
                post_message_id,
                post_assistant_message_id,
                error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            params![
                "inj_cli",
                goal_id,
                "ses_logs",
                "completed",
                1_i64,
                2_i64,
                "pre",
                "pre_a",
                0_i64,
                3_i64,
                4_i64,
                "post",
                "post_a",
                "none",
            ],
        )
        .unwrap();

    let logs = Command::new(env!("CARGO_BIN_EXE_opencode-goal-runner"))
        .arg("--db")
        .arg(&db)
        .arg("--config")
        .arg(std::env::temp_dir().join("missing-opencode-goal-runner-config.toml"))
        .arg("logs")
        .arg("--goal")
        .arg(&goal_id)
        .arg("--limit")
        .arg("1")
        .output()
        .unwrap();
    assert!(
        logs.status.success(),
        "{}",
        String::from_utf8_lossy(&logs.stderr)
    );
    let stdout = String::from_utf8_lossy(&logs.stdout);
    assert!(stdout.contains("inj_cli"));
    assert!(stdout.contains("completed"));
    assert!(stdout.contains("created:"));
    assert!(stdout.contains("(1)"));
    assert!(stdout.contains("submitted:"));
    assert!(stdout.contains("(3)"));
    assert!(stdout.contains("completed:"));
    assert!(stdout.contains("(4)"));
    assert!(stdout.contains("pre_message_id: pre"));
    assert!(stdout.contains("post_message_id: post"));
    assert!(stdout.contains("error: none"));

    let logs_json = Command::new(env!("CARGO_BIN_EXE_opencode-goal-runner"))
        .arg("--db")
        .arg(&db)
        .arg("--config")
        .arg(std::env::temp_dir().join("missing-opencode-goal-runner-config.toml"))
        .arg("logs")
        .arg("--goal")
        .arg(&goal_id)
        .arg("--limit")
        .arg("1")
        .arg("--json")
        .output()
        .unwrap();
    assert!(
        logs_json.status.success(),
        "{}",
        String::from_utf8_lossy(&logs_json.stderr)
    );
    let logs_json: serde_json::Value = serde_json::from_slice(&logs_json.stdout).unwrap();
    assert_eq!(logs_json[0]["injection_id"], "inj_cli");
    assert_eq!(logs_json[0]["status"], "completed");
    assert_eq!(logs_json[0]["pre_message_id"], "pre");
    assert_eq!(logs_json[0]["post_message_id"], "post");

    let inspect_json = Command::new(env!("CARGO_BIN_EXE_opencode-goal-runner"))
        .arg("--db")
        .arg(&db)
        .arg("--config")
        .arg(std::env::temp_dir().join("missing-opencode-goal-runner-config.toml"))
        .arg("inspect")
        .arg("--goal")
        .arg(&goal_id)
        .arg("--json")
        .output()
        .unwrap();
    assert!(
        inspect_json.status.success(),
        "{}",
        String::from_utf8_lossy(&inspect_json.stderr)
    );
    let inspect_json: serde_json::Value = serde_json::from_slice(&inspect_json.stdout).unwrap();
    assert_eq!(inspect_json["goal"]["goal_id"], goal_id);
    assert_eq!(inspect_json["injections"][0]["injection_id"], "inj_cli");

    std::fs::remove_file(db).unwrap();
}

fn unique_path(label: &str, extension: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "opencode-goal-runner-cli-{label}-{}.{}",
        unique_id(),
        extension
    ))
}

fn unique_id() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos()
}

struct Server {
    base_url: String,
    stop: Arc<AtomicBool>,
    handle: Option<thread::JoinHandle<()>>,
}

impl Server {
    fn start() -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let base_url = format!("http://{}", listener.local_addr().unwrap());
        let stop = Arc::new(AtomicBool::new(false));
        let stop_thread = stop.clone();
        let handle = thread::spawn(move || {
            while !stop_thread.load(Ordering::SeqCst) {
                match listener.accept() {
                    Ok((stream, _)) => {
                        thread::spawn(move || handle(stream));
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(5));
                    }
                    Err(_) => break,
                }
            }
        });
        Self {
            base_url,
            stop,
            handle: Some(handle),
        }
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

fn handle(mut stream: TcpStream) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
    let mut bytes = Vec::new();
    let mut buffer = [0; 1024];
    loop {
        let Ok(read) = stream.read(&mut buffer) else {
            return;
        };
        if read == 0 {
            return;
        }
        bytes.extend_from_slice(&buffer[..read]);
        if bytes.windows(4).any(|window| window == b"\r\n\r\n") {
            break;
        }
    }
    let first_line = String::from_utf8_lossy(&bytes)
        .lines()
        .next()
        .unwrap_or_default()
        .to_string();
    let path = first_line.split_whitespace().nth(1).unwrap_or_default();
    let body = match path {
        "/session" => "[]",
        "/session/status" => "{}",
        "/permission" | "/question" => "[]",
        _ => "{}",
    };
    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(),
        body
    );
    let _ = stream.write_all(response.as_bytes());
}
